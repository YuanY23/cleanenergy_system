"""Single-source engineering metrics for tables, figures and reports."""

from __future__ import annotations

import json

import pandas as pd

from zero_carbon_park.planning.cost_params import CarbonFactors


FORMULA_VERSION = "engineering_metrics_v1.0"


class MetricConsistencyError(ValueError):
    """Raised when source tables cannot support a defensible comparison."""


def build_engineering_comparison(
    planning_summary: pd.DataFrame,
    replay_hourly: pd.DataFrame,
    reliability_summary: pd.DataFrame,
    *,
    carbon_factors: CarbonFactors,
    natural_gas_factor_kgco2_per_m3: float,
    cost_tolerance_cny: float = 1e-6,
) -> dict[str, pd.DataFrame]:
    """Calculate economic, carbon and deterministic reliability indicators.

    Location-based Scope 2 and the national zero-carbon-park method remain
    separate columns.  Grid exports never reduce location-based emissions;
    only explicitly supplied eligible-green and verified-offset columns affect
    the zero-carbon-park boundary.
    """

    if natural_gas_factor_kgco2_per_m3 < 0:
        raise ValueError("natural gas emission factor cannot be negative")
    _require_columns(
        planning_summary,
        {
            "portfolio_id",
            "annual_operation_cost_cny",
            "annualized_investment_cost_cny",
            "annual_demand_charge_cost_cny",
            "annual_fuel_cell_backup_value_cny",
            "annual_total_cost_cny",
        },
        "planning summary",
    )
    _require_columns(replay_hourly, {"portfolio_id", "grid_buy_kw"}, "replay")
    replay_with_carbon = add_hourly_carbon_metrics(
        replay_hourly,
        carbon_factors=carbon_factors,
        natural_gas_factor_kgco2_per_m3=natural_gas_factor_kgco2_per_m3,
    )
    rows: list[dict[str, object]] = []
    for _, planning in planning_summary.iterrows():
        portfolio_id = str(planning["portfolio_id"])
        replay = replay_with_carbon.loc[
            replay_with_carbon["portfolio_id"] == portfolio_id
        ]
        if replay.empty:
            raise MetricConsistencyError(f"missing replay for {portfolio_id}")
        expected_cost = (
            float(planning["annual_operation_cost_cny"])
            + float(planning["annualized_investment_cost_cny"])
            + float(planning["annual_demand_charge_cost_cny"])
            - float(planning["annual_fuel_cell_backup_value_cny"])
        )
        if abs(expected_cost - float(planning["annual_total_cost_cny"])) > cost_tolerance_cny:
            raise MetricConsistencyError(
                f"cost identity failed for {portfolio_id}: {expected_cost} != "
                f"{planning['annual_total_cost_cny']}"
            )

        grid_buy = _sum(replay, "grid_buy_kw")
        grid_sell = _sum(replay, "grid_sell_kw")
        gas = _sum(replay, "gas_consumption_m3")
        onsite_renewable = _sum(replay, "pv_used_kw") + _sum(replay, "wind_used_kw")
        renewable_available = (
            onsite_renewable
            + _sum(replay, "pv_sold_kw")
            + _sum(replay, "wind_sold_kw")
            + _sum(replay, "pv_curtail_kw")
            + _sum(replay, "wind_curtail_kw")
        )
        electric_consumption = (
            _sum(replay, "electric_load_kw")
            + _sum(replay, "heat_pump_power_kw")
            + _sum(replay, "battery_charge_kw")
            + _sum(replay, "electrolyzer_power_kw")
        )
        eligible_green = min(_sum(replay, "eligible_green_grid_kwh"), grid_buy)
        offsets = _sum(replay, "verified_offset_kgco2")
        scope1 = gas * natural_gas_factor_kgco2_per_m3
        scope2_location = grid_buy * carbon_factors.location_based_kg_per_kwh
        fossil_grid = max(grid_buy - eligible_green, 0.0)
        zero_grid = fossil_grid * carbon_factors.zero_carbon_method_kg_per_kwh
        zero_total = max(scope1 + zero_grid - offsets, 0.0)
        normal_ens = sum(
            _sum(replay, column)
            for column in (
                "load_shed_critical_kwh",
                "load_shed_important_kwh",
                "load_shed_interruptible_kwh",
            )
        )
        reliability = _reliability_metrics(reliability_summary, portfolio_id)
        rows.append(
            {
                "portfolio_id": portfolio_id,
                "annual_operation_cost_cny": float(planning["annual_operation_cost_cny"]),
                "annualized_investment_cost_cny": float(
                    planning["annualized_investment_cost_cny"]
                ),
                "annual_demand_charge_cost_cny": float(
                    planning["annual_demand_charge_cost_cny"]
                ),
                "annual_fuel_cell_backup_value_cny": float(
                    planning["annual_fuel_cell_backup_value_cny"]
                ),
                "annual_total_cost_cny": float(planning["annual_total_cost_cny"]),
                "annual_grid_purchase_kwh": grid_buy,
                "annual_grid_sell_kwh": grid_sell,
                "renewable_consumption_rate": (
                    onsite_renewable / renewable_available
                    if renewable_available > 0
                    else 0.0
                ),
                "green_power_self_supply_rate": (
                    onsite_renewable / electric_consumption
                    if electric_consumption > 0
                    else 0.0
                ),
                "scope1_natural_gas_kgco2": scope1,
                "scope2_location_grid_kgco2": scope2_location,
                "location_total_kgco2": scope1 + scope2_location,
                "zero_carbon_eligible_green_kwh": eligible_green,
                "zero_carbon_fossil_grid_kgco2": zero_grid,
                "zero_carbon_direct_emission_kgco2": scope1,
                "zero_carbon_verified_offset_kgco2": offsets,
                "zero_carbon_total_kgco2": zero_total,
                "normal_year_ens_kwh": normal_ens,
                "minimum_battery_soc_kwh": _minimum(replay, "battery_soc_kwh"),
                "minimum_h2_inventory_kg": _minimum(replay, "h2_storage_kg"),
                **reliability,
            }
        )
    comparison = pd.DataFrame(rows)
    return {
        "comparison": comparison,
        "definitions": _metric_definitions(),
        "replay_with_carbon": replay_with_carbon,
    }


def add_hourly_carbon_metrics(
    replay_hourly: pd.DataFrame,
    *,
    carbon_factors: CarbonFactors,
    natural_gas_factor_kgco2_per_m3: float,
) -> pd.DataFrame:
    """Attach the two non-interchangeable hourly carbon-accounting columns."""

    if natural_gas_factor_kgco2_per_m3 < 0:
        raise ValueError("natural gas emission factor cannot be negative")
    _require_columns(replay_hourly, {"portfolio_id", "grid_buy_kw"}, "replay")
    result = replay_hourly.copy()
    grid_buy = pd.to_numeric(result["grid_buy_kw"], errors="raise").clip(lower=0.0)
    gas = (
        pd.to_numeric(result["gas_consumption_m3"], errors="raise").clip(lower=0.0)
        if "gas_consumption_m3" in result
        else pd.Series(0.0, index=result.index)
    )
    eligible = (
        pd.to_numeric(result["eligible_green_grid_kwh"], errors="raise")
        .clip(lower=0.0)
        .where(lambda values: values <= grid_buy, grid_buy)
        if "eligible_green_grid_kwh" in result
        else pd.Series(0.0, index=result.index)
    )
    offsets = (
        pd.to_numeric(result["verified_offset_kgco2"], errors="raise").clip(lower=0.0)
        if "verified_offset_kgco2" in result
        else pd.Series(0.0, index=result.index)
    )
    direct = gas * natural_gas_factor_kgco2_per_m3
    result["location_carbon_kgco2"] = (
        direct + grid_buy * carbon_factors.location_based_kg_per_kwh
    )
    result["zero_carbon_kgco2"] = (
        direct
        + (grid_buy - eligible).clip(lower=0.0)
        * carbon_factors.zero_carbon_method_kg_per_kwh
        - offsets
    )
    return result


def _reliability_metrics(
    reliability_summary: pd.DataFrame, portfolio_id: str
) -> dict[str, float | int]:
    _require_columns(
        reliability_summary,
        {
            "portfolio_id",
            "ens_total_kwh",
            "ens_critical_kwh",
            "critical_load_supply_ratio",
            "loss_of_load_hours",
            "max_consecutive_loss_hours",
            "island_survival_hours",
        },
        "reliability summary",
    )
    selected = reliability_summary.loc[
        reliability_summary["portfolio_id"] == portfolio_id
    ]
    if selected.empty:
        raise MetricConsistencyError(
            f"missing reliability results for {portfolio_id}"
        )
    return {
        "design_event_ens_kwh": float(selected["ens_total_kwh"].max()),
        "design_event_critical_ens_kwh": float(selected["ens_critical_kwh"].max()),
        "critical_load_supply_ratio": float(
            selected["critical_load_supply_ratio"].min()
        ),
        "design_event_loss_of_load_hours": int(selected["loss_of_load_hours"].max()),
        "maximum_consecutive_loss_hours": int(
            selected["max_consecutive_loss_hours"].max()
        ),
        "minimum_island_survival_hours": int(selected["island_survival_hours"].min()),
    }


def _metric_definitions() -> pd.DataFrame:
    definitions = {
        "annual_total_cost_cny": (
            "operation + annualized CAPEX + demand charge - declared backup value",
            [
                "annual_operation_cost_cny",
                "annualized_investment_cost_cny",
                "annual_demand_charge_cost_cny",
                "annual_fuel_cell_backup_value_cny",
            ],
        ),
        "scope1_natural_gas_kgco2": (
            "gas_consumption_m3 * natural_gas_factor_kgco2_per_m3",
            ["gas_consumption_m3"],
        ),
        "scope2_location_grid_kgco2": (
            "gross grid_buy_kw * location_based_kg_per_kwh; exports do not offset",
            ["grid_buy_kw", "grid_sell_kw"],
        ),
        "location_total_kgco2": (
            "scope1_natural_gas_kgco2 + scope2_location_grid_kgco2",
            ["gas_consumption_m3", "grid_buy_kw"],
        ),
        "zero_carbon_total_kgco2": (
            "direct gas + non-eligible grid * 0.8325 - verified offsets",
            [
                "gas_consumption_m3",
                "grid_buy_kw",
                "eligible_green_grid_kwh",
                "verified_offset_kgco2",
            ],
        ),
        "normal_year_ens_kwh": (
            "sum of critical, important and interruptible load shedding",
            [
                "load_shed_critical_kwh",
                "load_shed_important_kwh",
                "load_shed_interruptible_kwh",
            ],
        ),
        "critical_load_supply_ratio": (
            "1 - critical ENS / critical demand for deterministic design events",
            ["ens_critical_kwh", "critical_load_supply_ratio"],
        ),
    }
    return pd.DataFrame(
        [
            {
                "metric": metric,
                "formula": formula,
                "formula_version": FORMULA_VERSION,
                "input_columns": json.dumps(columns, ensure_ascii=False),
            }
            for metric, (formula, columns) in definitions.items()
        ]
    )


def _sum(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].sum()) if column in frame else 0.0


def _minimum(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].min()) if column in frame and not frame.empty else 0.0


def _require_columns(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise MetricConsistencyError(f"{label} missing columns: {sorted(missing)}")


__all__ = [
    "FORMULA_VERSION",
    "MetricConsistencyError",
    "add_hourly_carbon_metrics",
    "build_engineering_comparison",
]
