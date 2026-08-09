from __future__ import annotations

import pandas as pd
import pytest

from zero_carbon_park.planning.cost_params import CarbonFactors
from zero_carbon_park.reporting.metrics import (
    MetricConsistencyError,
    build_engineering_comparison,
)


def _planning() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "portfolio_id": "economic",
                "annual_operation_cost_cny": 60.0,
                "annualized_investment_cost_cny": 40.0,
                "annual_demand_charge_cost_cny": 5.0,
                "annual_fuel_cell_backup_value_cny": 2.0,
                "annual_total_cost_cny": 103.0,
            }
        ]
    )


def _replay() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "portfolio_id": ["economic", "economic"],
            "grid_buy_kw": [10.0, 5.0],
            "grid_sell_kw": [4.0, 0.0],
            "gas_consumption_m3": [1.0, 1.0],
            "pv_used_kw": [3.0, 0.0],
            "wind_used_kw": [2.0, 0.0],
            "pv_sold_kw": [4.0, 0.0],
            "wind_sold_kw": [0.0, 0.0],
            "pv_curtail_kw": [1.0, 0.0],
            "wind_curtail_kw": [0.0, 0.0],
            "electric_load_kw": [10.0, 5.0],
            "heat_pump_power_kw": [0.0, 0.0],
            "battery_charge_kw": [0.0, 0.0],
            "electrolyzer_power_kw": [0.0, 0.0],
            "eligible_green_grid_kwh": [2.0, 0.0],
            "verified_offset_kgco2": [0.5, 0.0],
            "load_shed_critical_kwh": [0.0, 0.0],
            "load_shed_important_kwh": [0.0, 0.0],
            "load_shed_interruptible_kwh": [0.0, 0.0],
            "battery_soc_kwh": [4.0, 2.0],
            "h2_storage_kg": [3.0, 1.0],
        }
    )


def test_comparison_uses_separate_cost_carbon_and_reliability_boundaries() -> None:
    reliability = pd.DataFrame(
        [
            {
                "portfolio_id": "economic",
                "event_id": "OUTAGE_24H",
                "ens_total_kwh": 8.0,
                "ens_critical_kwh": 2.0,
                "critical_load_supply_ratio": 0.95,
                "loss_of_load_hours": 3,
                "max_consecutive_loss_hours": 2,
                "island_survival_hours": 8,
                "unserved_hydrogen_kg": 3.0,
                "hydrogen_supply_ratio": 0.88,
            }
        ]
    )
    result = build_engineering_comparison(
        _planning(),
        _replay(),
        reliability,
        carbon_factors=CarbonFactors(0.6479, 0.8325),
        natural_gas_factor_kgco2_per_m3=2.0,
    )
    row = result["comparison"].iloc[0]
    hourly = result["replay_with_carbon"]

    assert row["annual_total_cost_cny"] == pytest.approx(103.0)
    assert row["scope1_natural_gas_kgco2"] == pytest.approx(4.0)
    assert row["scope2_location_grid_kgco2"] == pytest.approx(15.0 * 0.6479)
    assert row["location_total_kgco2"] == pytest.approx(4.0 + 15.0 * 0.6479)
    assert row["zero_carbon_fossil_grid_kgco2"] == pytest.approx(13.0 * 0.8325)
    assert row["zero_carbon_total_kgco2"] == pytest.approx(
        4.0 + 13.0 * 0.8325 - 0.5
    )
    assert row["annual_grid_sell_kwh"] == 4.0
    assert row["normal_year_ens_kwh"] == 0.0
    assert row["design_event_ens_kwh"] == 8.0
    assert row["critical_load_supply_ratio"] == 0.95
    assert row["design_event_unserved_hydrogen_kg"] == 3.0
    assert row["hydrogen_supply_ratio"] == 0.88
    assert row["minimum_battery_soc_kwh"] == 2.0
    assert hourly["location_carbon_kgco2"].sum() == pytest.approx(
        row["location_total_kgco2"]
    )
    assert hourly["zero_carbon_kgco2"].sum() == pytest.approx(
        row["zero_carbon_total_kgco2"]
    )
    definitions = result["definitions"].set_index("metric")
    assert definitions.loc["location_total_kgco2", "formula_version"]
    assert "grid_buy_kw" in definitions.loc[
        "scope2_location_grid_kgco2", "input_columns"
    ]


def test_cost_components_must_reconcile_before_comparison() -> None:
    broken = _planning()
    broken.loc[0, "annual_total_cost_cny"] = 999.0
    with pytest.raises(MetricConsistencyError, match="cost identity"):
        build_engineering_comparison(
            broken,
            _replay(),
            pd.DataFrame(),
            carbon_factors=CarbonFactors(),
            natural_gas_factor_kgco2_per_m3=2.0,
        )


def test_missing_reliability_results_cannot_be_reported_as_perfect_supply() -> None:
    with pytest.raises(MetricConsistencyError, match="reliability"):
        build_engineering_comparison(
            _planning(),
            _replay(),
            pd.DataFrame(),
            carbon_factors=CarbonFactors(),
            natural_gas_factor_kgco2_per_m3=2.0,
        )
