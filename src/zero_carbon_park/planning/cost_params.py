"""容量规划投资成本参数。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanningCostParams:
    """容量规划使用的投资成本和寿命参数。"""

    discount_rate: float = 0.08
    wind_capex_cny_per_kw: float = 6000.0
    wind_life_years: int = 20
    pv_capex_cny_per_kw: float = 3500.0
    pv_life_years: int = 25
    battery_power_capex_cny_per_kw: float = 800.0
    battery_energy_capex_cny_per_kwh: float = 1200.0
    battery_life_years: int = 12
    electrolyzer_capex_cny_per_kw: float = 3000.0
    electrolyzer_life_years: int = 15
    h2_storage_capex_cny_per_kg: float = 2500.0
    h2_storage_life_years: int = 20
    fuel_cell_capex_cny_per_kw: float = 6000.0
    fuel_cell_life_years: int = 10
    heat_pump_capex_cny_per_kw: float = 1000.0
    heat_pump_life_years: int = 15
    battery_degradation_cost_cny_per_kwh: float = 0.0
    fuel_cell_backup_value_cny_per_kw_year: float = 0.0
    fuel_cell_backup_reserve_kw: float = 0.0
    fuel_cell_backup_required_kw: float = 0.0
    grid_export_limit_kw: float = 0.0
    demand_charge_cny_per_kw_year: float = 0.0


def capital_recovery_factor(rate: float, years: int) -> float:
    """计算资本回收系数 CRF。"""

    if years <= 0:
        raise ValueError("设备寿命必须大于 0")
    if rate == 0:
        return 1.0 / years
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def get_default_planning_cost_params() -> PlanningCostParams:
    """返回第一版容量规划默认投资参数。"""

    return PlanningCostParams()
