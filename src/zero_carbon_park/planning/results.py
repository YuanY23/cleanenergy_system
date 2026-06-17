"""容量规划结果提取。"""

from __future__ import annotations

import pandas as pd
from pyomo.environ import value


CAPACITY_VARIABLES = [
    ("wind_capacity_kw", "风电装机", "kW"),
    ("pv_capacity_kw", "光伏装机", "kW"),
    ("battery_power_capacity_kw", "电池功率", "kW"),
    ("battery_energy_capacity_kwh", "电池容量", "kWh"),
    ("electrolyzer_power_capacity_kw", "电解槽功率", "kW"),
    ("h2_storage_capacity_kg", "储氢容量", "kg"),
    ("fuel_cell_power_capacity_kw", "燃料电池功率", "kW"),
    ("heat_pump_power_capacity_kw", "热泵功率", "kW"),
]


def extract_capacity_planning_results(model, status: str) -> dict[str, pd.DataFrame]:
    """从容量规划模型中提取容量、年度汇总、典型日和逐时结果。"""

    capacity = _extract_capacity_result(model)
    hourly = _extract_hourly_results(model)
    typical_day_operation = _extract_typical_day_operation(model, hourly)
    planning_summary = _extract_planning_summary(model, status, typical_day_operation)

    return {
        "capacity": capacity,
        "hourly": hourly,
        "typical_day_operation": typical_day_operation,
        "summary": planning_summary,
    }


def _extract_capacity_result(model) -> pd.DataFrame:
    rows = []
    for variable_name, name_cn, unit in CAPACITY_VARIABLES:
        rows.append(
            {
                "capacity_variable": variable_name,
                "capacity_name": name_cn,
                "unit": unit,
                "capacity_value": value(getattr(model, variable_name)),
            }
        )
    return pd.DataFrame(rows)


def _extract_hourly_results(model) -> pd.DataFrame:
    rows = []
    for d in model.D:
        for t in model.T:
            rows.append(
                {
                    "typical_day_id": str(d),
                    "hour": int(t),
                    "weight_days": value(model.weight_days[d]),
                    "electric_load_kw": value(model.electric_load[d, t]),
                    "heat_load_kw": value(model.heat_load[d, t]),
                    "hydrogen_load_kg": value(model.hydrogen_load[d, t]),
                    "grid_buy_kw": value(model.grid_buy[d, t]),
                    "pv_used_kw": value(model.pv_used[d, t]),
                    "pv_curtail_kw": value(model.pv_curtail[d, t]),
                    "wind_used_kw": value(model.wind_used[d, t]),
                    "wind_curtail_kw": value(model.wind_curtail[d, t]),
                    "heat_pump_power_kw": value(model.heat_pump_power[d, t]),
                    "heat_pump_heat_kw": value(model.heat_pump_heat[d, t]),
                    "gas_boiler_heat_kw": value(model.gas_boiler_heat[d, t]),
                    "gas_consumption_m3": value(model.gas_consumption[d, t]),
                    "battery_charge_kw": value(model.battery_charge[d, t]),
                    "battery_discharge_kw": value(model.battery_discharge[d, t]),
                    "battery_soc_kwh": value(model.battery_soc[d, t]),
                    "electrolyzer_power_kw": value(model.electrolyzer_power[d, t]),
                    "h2_production_kg": value(model.h2_production[d, t]),
                    "h2_charge_kg": value(model.h2_charge[d, t]),
                    "h2_discharge_kg": value(model.h2_discharge[d, t]),
                    "h2_storage_kg": value(model.h2_storage[d, t]),
                    "h2_external_supply_kg": value(model.h2_external_supply[d, t]),
                    "h2_fuel_cell_kg": value(model.h2_fuel_cell[d, t]),
                    "fuel_cell_power_kw": value(model.fuel_cell_power[d, t]),
                    "carbon_emission_kg": value(model.carbon_emission[d, t]),
                }
            )
    return pd.DataFrame(rows)


def _extract_typical_day_operation(model, hourly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d in model.D:
        day = hourly[hourly["typical_day_id"] == str(d)]
        weight_days = float(value(model.weight_days[d]))
        renewable_available = (
            day["pv_used_kw"].sum()
            + day["wind_used_kw"].sum()
            + day["pv_curtail_kw"].sum()
            + day["wind_curtail_kw"].sum()
        )
        renewable_used = day["pv_used_kw"].sum() + day["wind_used_kw"].sum()
        total_cost = _daily_operation_cost(model, d)
        carbon_emission = day["carbon_emission_kg"].sum()
        rows.append(
            {
                "typical_day_id": str(d),
                "weight_days": weight_days,
                "total_cost_cny": total_cost,
                "grid_purchase_kwh": day["grid_buy_kw"].sum(),
                "renewable_available_kwh": renewable_available,
                "renewable_used_kwh": renewable_used,
                "renewable_curtailment_kwh": (
                    day["pv_curtail_kw"].sum() + day["wind_curtail_kw"].sum()
                ),
                "renewable_consumption_rate": (
                    renewable_used / renewable_available if renewable_available > 0 else 0.0
                ),
                "carbon_emission_kg": carbon_emission,
                "heat_pump_heat_kwh": day["heat_pump_heat_kw"].sum(),
                "gas_boiler_heat_kwh": day["gas_boiler_heat_kw"].sum(),
                "h2_production_kg": day["h2_production_kg"].sum(),
                "h2_external_supply_kg": day["h2_external_supply_kg"].sum(),
                "fuel_cell_generation_kwh": day["fuel_cell_power_kw"].sum(),
                "weighted_total_cost_cny": total_cost * weight_days,
                "weighted_grid_purchase_kwh": day["grid_buy_kw"].sum() * weight_days,
                "weighted_carbon_emission_kg": carbon_emission * weight_days,
                "weighted_heat_pump_heat_kwh": day["heat_pump_heat_kw"].sum()
                * weight_days,
                "weighted_h2_production_kg": day["h2_production_kg"].sum()
                * weight_days,
            }
        )
    return pd.DataFrame(rows)


def _extract_planning_summary(model, status: str, typical_day_operation: pd.DataFrame) -> pd.DataFrame:
    annual_operation_cost = value(model.annual_operation_cost)
    annualized_investment_cost = value(model.annualized_investment_cost)
    annual_total_cost = annual_operation_cost + annualized_investment_cost
    annual_renewable_available = (
        typical_day_operation["renewable_available_kwh"]
        * typical_day_operation["weight_days"]
    ).sum()
    annual_renewable_used = (
        typical_day_operation["renewable_used_kwh"] * typical_day_operation["weight_days"]
    ).sum()

    return pd.DataFrame(
        [
            {
                "status": status,
                "annual_operation_cost_cny": annual_operation_cost,
                "annualized_investment_cost_cny": annualized_investment_cost,
                "annual_total_cost_cny": annual_total_cost,
                "annual_grid_cost_cny": _annual_component_cost(model, "grid"),
                "annual_gas_cost_cny": _annual_component_cost(model, "gas"),
                "annual_carbon_cost_cny": _annual_component_cost(model, "carbon"),
                "annual_grid_purchase_kwh": typical_day_operation[
                    "weighted_grid_purchase_kwh"
                ].sum(),
                "annual_carbon_emission_kg": typical_day_operation[
                    "weighted_carbon_emission_kg"
                ].sum(),
                "annual_renewable_available_kwh": annual_renewable_available,
                "annual_renewable_used_kwh": annual_renewable_used,
                "annual_renewable_consumption_rate": (
                    annual_renewable_used / annual_renewable_available
                    if annual_renewable_available > 0
                    else 0.0
                ),
                "annual_h2_external_supply_kg": (
                    typical_day_operation["h2_external_supply_kg"]
                    * typical_day_operation["weight_days"]
                ).sum(),
            }
        ]
    )


def _daily_operation_cost(model, d) -> float:
    return sum(
        value(
            model.grid_buy[d, t] * model.grid_price[d, t]
            + model.gas_consumption[d, t] * model.gas_price[d, t]
            + (model.pv_curtail[d, t] + model.wind_curtail[d, t])
            * model.curtail_penalty
            + model.carbon_emission[d, t] * model.carbon_price[d, t]
            + (model.battery_charge[d, t] + model.battery_discharge[d, t])
            * model.battery_om
            + model.h2_production[d, t] * model.electrolyzer_om
            + model.h2_external_supply[d, t] * model.h2_external_supply_cost
            + model.fuel_cell_power[d, t] * model.fuel_cell_om
        )
        for t in model.T
    )


def _annual_component_cost(model, component: str) -> float:
    total = 0.0
    for d in model.D:
        for t in model.T:
            if component == "grid":
                total += value(model.weight_days[d] * model.grid_buy[d, t] * model.grid_price[d, t])
            elif component == "gas":
                total += value(
                    model.weight_days[d]
                    * model.gas_consumption[d, t]
                    * model.gas_price[d, t]
                )
            elif component == "carbon":
                total += value(
                    model.weight_days[d]
                    * model.carbon_emission[d, t]
                    * model.carbon_price[d, t]
                )
    return total

