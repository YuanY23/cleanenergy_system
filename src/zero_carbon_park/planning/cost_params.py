"""Traceable capacity-planning, tariff and carbon parameters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


IRENA_COST_SOURCE_ID = "IRENA_COSTS_2024"
IEA_ELECTROLYZER_SOURCE_ID = "IEA_HYDROGEN_REVIEW_2025"
MENGXI_TOU_SOURCE_ID = "MENGXI_TOU_2021"
TRANSMISSION_SOURCE_ID = "NDRC_TRANSMISSION_4TH_2026"
ORDOS_GAS_SOURCE_ID = "ORDOS_GAS_2026"


@dataclass(frozen=True)
class TechnologyParameter:
    """One base/low/high engineering parameter with explicit provenance."""

    technology: str
    parameter: str
    base: float
    low: float
    high: float
    unit: str
    source_id: str
    lifetime_years: int
    fixed_om_fraction: float
    efficiency: float
    evidence_boundary: str

    def __post_init__(self) -> None:
        if not self.source_id or not self.unit:
            raise ValueError("technology parameters require source_id and unit")
        if not self.low <= self.base <= self.high:
            raise ValueError("technology parameter must satisfy low <= base <= high")
        if self.lifetime_years <= 0 or self.fixed_om_fraction < 0:
            raise ValueError("lifetime and fixed O&M must be physically valid")
        if self.efficiency <= 0:
            raise ValueError("efficiency/performance indicator must be positive")


@dataclass(frozen=True)
class CarbonFactors:
    """Two intentionally separate electricity-carbon accounting factors."""

    location_based_kg_per_kwh: float = 0.6479
    zero_carbon_method_kg_per_kwh: float = 0.8325
    location_source_id: str = "MEE_GRID_FACTOR_2023"
    zero_carbon_source_id: str = "NDRC_ZERO_CARBON_METHOD_2025"


@dataclass(frozen=True)
class NaturalGasTariff:
    """Published Ordos non-residential gas price and its validity window."""

    price_cny_per_m3: float = 2.952
    applicable_from: date = date(2026, 4, 1)
    applicable_to: date = date(2026, 10, 31)
    source_id: str = ORDOS_GAS_SOURCE_ID

    def price_for(self, when: date) -> float:
        if not self.applicable_from <= when <= self.applicable_to:
            raise ValueError(
                "date is outside the published applicability interval; "
                "select and document a separate gas-price scenario"
            )
        return self.price_cny_per_m3


@dataclass(frozen=True)
class GridTariff:
    """Assumed 110 kV two-part Mongxi grid tariff configuration."""

    voltage_level_kv: int = 110
    billing_method: str = "demand"
    base_energy_price_cny_per_kwh: float = 0.35
    transmission_cny_per_kwh: float = 0.0520
    demand_charge_cny_per_kw_month: float = 31.2
    capacity_charge_cny_per_kva_month: float = 19.5
    line_loss_rate: float = 0.0281
    tou_source_id: str = MENGXI_TOU_SOURCE_ID
    transmission_source_id: str = TRANSMISSION_SOURCE_ID

    def __post_init__(self) -> None:
        if self.billing_method not in {"demand", "capacity"}:
            raise ValueError("billing_method must be demand or capacity")
        if not 0 <= self.line_loss_rate < 1:
            raise ValueError("line_loss_rate must be within [0, 1)")

    @property
    def selected_monthly_charge(self) -> float:
        if self.billing_method == "demand":
            return self.demand_charge_cny_per_kw_month
        return self.capacity_charge_cny_per_kva_month

    def hourly_energy_price(self, timestamp_local: pd.Timestamp) -> float:
        """Return the metered-boundary energy charge, applying network loss once."""

        energy = (
            self.base_energy_price_cny_per_kwh
            * mengxi_tou_multiplier(timestamp_local)
            + self.transmission_cny_per_kwh
        )
        return energy / (1.0 - self.line_loss_rate)


@dataclass(frozen=True)
class PlanningCostParams:
    """Planning costs with source IDs and backwards-compatible flat fields."""

    discount_rate: float = 0.08
    wind_capex_cny_per_kw: float = 7_495.2
    wind_life_years: int = 20
    pv_capex_cny_per_kw: float = 4_975.2
    pv_life_years: int = 25
    battery_power_capex_cny_per_kw: float = 800.0
    battery_energy_capex_cny_per_kwh: float = 1_382.4
    battery_life_years: int = 12
    electrolyzer_capex_cny_per_kw: float = 6_480.0
    electrolyzer_life_years: int = 15
    h2_storage_capex_cny_per_kg: float = 2_500.0
    h2_storage_life_years: int = 20
    fuel_cell_capex_cny_per_kw: float = 6_000.0
    fuel_cell_life_years: int = 10
    heat_pump_capex_cny_per_kw: float = 1_000.0
    heat_pump_life_years: int = 15
    battery_degradation_cost_cny_per_kwh: float = 0.0
    fuel_cell_backup_value_cny_per_kw_year: float = 0.0
    fuel_cell_backup_reserve_kw: float = 0.0
    fuel_cell_backup_required_kw: float = 0.0
    grid_export_limit_kw: float = 0.0
    # Legacy planning adapters keep the historic objective decomposition until
    # U5 routes them through GridTariff; the formal model uses the monthly field.
    demand_charge_cny_per_kw_year: float = 0.0
    grid_transmission_cny_per_kwh: float = 0.0520
    grid_demand_charge_cny_per_kw_month: float = 31.2
    grid_capacity_charge_cny_per_kva_month: float = 19.5
    grid_line_loss_rate: float = 0.0281
    natural_gas_price_cny_per_m3: float = 2.952
    location_grid_factor_kgco2_per_kwh: float = 0.6479
    zero_carbon_grid_factor_kgco2_per_kwh: float = 0.8325


def mengxi_tou_band(timestamp_local: pd.Timestamp) -> str:
    """Classify a local hour using the published Mongxi large-industry bands."""

    timestamp = pd.Timestamp(timestamp_local)
    if timestamp.tzinfo is None:
        raise ValueError("Mongxi TOU classification requires a timezone-aware timestamp")
    local = timestamp.tz_convert("Asia/Shanghai")
    month, hour = local.month, local.hour
    if month in {6, 7, 8}:
        if 5 <= hour < 7 or 17 <= hour < 21:
            return "peak"
        if 10 <= hour < 15:
            return "valley"
        return "flat"
    if 17 <= hour < 21:
        return "peak"
    if 0 <= hour < 4 or 10 <= hour < 15:
        return "valley"
    return "flat"


def mengxi_tou_multiplier(timestamp_local: pd.Timestamp) -> float:
    """Return the seasonal TOU ratio, including the 18:00-20:00 summer uplift."""

    timestamp = pd.Timestamp(timestamp_local)
    band = mengxi_tou_band(timestamp)
    local = timestamp.tz_convert("Asia/Shanghai")
    if local.month in {6, 7, 8}:
        ratio = {"peak": 1.48, "flat": 1.0, "valley": 0.47}[band]
        if band == "peak" and 18 <= local.hour < 20:
            ratio *= 1.20
        return ratio
    return {"peak": 1.48, "flat": 1.0, "valley": 0.79}[band]


def get_technology_parameter_table() -> tuple[TechnologyParameter, ...]:
    """Return source-bound base/low/high assumptions for planning sensitivity."""

    international_boundary = (
        "International installed-cost benchmark converted at 7.20 CNY/USD and "
        "an explicit localisation factor; not a domestic EPC quotation."
    )
    engineering_boundary = "Transparent engineering assumption pending a domestic quote."
    return (
        TechnologyParameter(
            "pv", "capex", 4975.2, 3482.6, 6467.8, "CNY/kW",
            IRENA_COST_SOURCE_ID, 25, 0.015, 0.86, international_boundary,
        ),
        TechnologyParameter(
            "onshore_wind", "capex", 7495.2, 5246.6, 9743.8, "CNY/kW",
            IRENA_COST_SOURCE_ID, 20, 0.025, 0.97, international_boundary,
        ),
        TechnologyParameter(
            "battery_energy", "capex", 1382.4, 967.7, 1797.1, "CNY/kWh",
            IRENA_COST_SOURCE_ID, 12, 0.020, 0.95, international_boundary,
        ),
        TechnologyParameter(
            "electrolyzer", "capex", 6480.0, 4320.0, 8640.0, "CNY/kW",
            IEA_ELECTROLYZER_SOURCE_ID, 15, 0.030, 55.0,
            "IEA China installed-cost interval; 55 kWh/kg is a current engineering baseline.",
        ),
        TechnologyParameter(
            "hydrogen_storage", "capex", 2500.0, 1800.0, 3300.0, "CNY/kgH2",
            "data/metadata/assumptions.yaml", 20, 0.020, 0.999, engineering_boundary,
        ),
        TechnologyParameter(
            "fuel_cell", "capex", 6000.0, 4500.0, 8000.0, "CNY/kW",
            "data/metadata/assumptions.yaml", 10, 0.040, 18.0, engineering_boundary,
        ),
        TechnologyParameter(
            "heat_pump", "capex", 1000.0, 750.0, 1350.0, "CNY/kW",
            "data/metadata/assumptions.yaml", 15, 0.020, 3.0, engineering_boundary,
        ),
    )


def capital_recovery_factor(rate: float, years: int) -> float:
    """Calculate the capital recovery factor."""

    if years <= 0:
        raise ValueError("equipment lifetime must be positive")
    if rate == 0:
        return 1.0 / years
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def get_default_planning_cost_params() -> PlanningCostParams:
    """Return the source-bound base case used by capacity planning."""

    return PlanningCostParams()
