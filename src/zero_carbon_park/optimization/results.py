"""优化结果提取模块。"""

from dataclasses import dataclass

import pandas as pd
from pyomo.environ import value


@dataclass(frozen=True)
class ScenarioResult:
    """单个场景求解后的结果对象。"""

    scenario_id: str
    status: str
    hourly_results: pd.DataFrame
    summary: dict[str, float | str]


def extract_minimal_results(model, scenario_id: str, status: str) -> ScenarioResult:
    """从当前阶段 MILP 模型中提取逐时结果和汇总指标。"""

    hourly_rows: list[dict[str, float | int | str]] = []

    for t in model.T:
        grid_buy_kw = value(model.grid_buy[t])
        pv_used_kw = value(model.pv_used[t])
        pv_curtail_kw = value(model.pv_curtail[t])
        wind_used_kw = value(model.wind_used[t])
        wind_curtail_kw = value(model.wind_curtail[t])

        heat_pump_power_kw = value(model.heat_pump_power[t])
        heat_pump_heat_kw = value(model.heat_pump_heat[t])
        gas_boiler_heat_kw = value(model.gas_boiler_heat[t])
        gas_consumption_m3 = value(model.gas_consumption[t])

        battery_charge_kw = value(model.battery_charge[t])
        battery_discharge_kw = value(model.battery_discharge[t])
        battery_soc_kwh = value(model.battery_soc[t])

        electrolyzer_power_kw = value(model.electrolyzer_power[t])
        h2_production_kg = value(model.h2_production[t])
        h2_charge_kg = value(model.h2_charge[t])
        h2_discharge_kg = value(model.h2_discharge[t])
        h2_storage_kg = value(model.h2_storage[t])
        h2_external_supply_kg = value(model.h2_external_supply[t])
        h2_sale_kg = value(model.h2_sale[t])
        h2_fuel_cell_kg = value(model.h2_fuel_cell[t])
        fuel_cell_power_kw = value(model.fuel_cell_power[t])

        carbon_emission_kg = value(model.carbon_emission[t])
        electric_load_kw = value(model.electric_load[t])
        heat_load_kw = value(model.heat_load[t])
        hydrogen_load_kg = value(model.hydrogen_load[t])

        # 电力平衡残差，理论上应接近 0。
        power_balance_residual_kw = (
            grid_buy_kw
            + pv_used_kw
            + wind_used_kw
            + battery_discharge_kw
            + fuel_cell_power_kw
            - electric_load_kw
            - heat_pump_power_kw
            - battery_charge_kw
            - electrolyzer_power_kw
        )

        # 热力平衡残差，理论上应接近 0。
        heat_balance_residual_kw = heat_pump_heat_kw + gas_boiler_heat_kw - heat_load_kw

        # 氢气平衡残差，理论上应接近 0。
        hydrogen_balance_residual_kg = (
            h2_production_kg
            + h2_discharge_kg
            + h2_external_supply_kg
            - hydrogen_load_kg
            - h2_charge_kg
            - h2_sale_kg
            - h2_fuel_cell_kg
        )

        # 燃料电池转换残差，理论上应接近 0。
        fuel_cell_conversion_residual_kw = (
            fuel_cell_power_kw - h2_fuel_cell_kg * value(model.fuel_cell_kwh_per_kg)
        )

        hourly_rows.append(
            {
                "scenario_id": scenario_id,
                "hour": int(t),
                "electric_load_kw": electric_load_kw,
                "heat_load_kw": heat_load_kw,
                "hydrogen_load_kg": hydrogen_load_kg,
                "grid_buy_kw": grid_buy_kw,
                "pv_used_kw": pv_used_kw,
                "pv_curtail_kw": pv_curtail_kw,
                "wind_used_kw": wind_used_kw,
                "wind_curtail_kw": wind_curtail_kw,
                "heat_pump_power_kw": heat_pump_power_kw,
                "heat_pump_heat_kw": heat_pump_heat_kw,
                "is_heat_pump_on": value(model.is_heat_pump_on[t]),
                "gas_boiler_heat_kw": gas_boiler_heat_kw,
                "gas_consumption_m3": gas_consumption_m3,
                "battery_charge_kw": battery_charge_kw,
                "battery_discharge_kw": battery_discharge_kw,
                "battery_soc_kwh": battery_soc_kwh,
                "is_battery_charging": value(model.is_battery_charging[t]),
                "is_battery_discharging": value(model.is_battery_discharging[t]),
                "electrolyzer_power_kw": electrolyzer_power_kw,
                "h2_production_kg": h2_production_kg,
                "h2_charge_kg": h2_charge_kg,
                "h2_discharge_kg": h2_discharge_kg,
                "h2_storage_kg": h2_storage_kg,
                "h2_external_supply_kg": h2_external_supply_kg,
                "h2_sale_kg": h2_sale_kg,
                "h2_fuel_cell_kg": h2_fuel_cell_kg,
                "fuel_cell_power_kw": fuel_cell_power_kw,
                "is_fuel_cell_on": value(model.is_fuel_cell_on[t]),
                "is_electrolyzer_on": value(model.is_electrolyzer_on[t]),
                "carbon_emission_kg": carbon_emission_kg,
                "power_balance_residual_kw": power_balance_residual_kw,
                "heat_balance_residual_kw": heat_balance_residual_kw,
                "hydrogen_balance_residual_kg": hydrogen_balance_residual_kg,
                "fuel_cell_conversion_residual_kw": fuel_cell_conversion_residual_kw,
            }
        )

    hourly_results = pd.DataFrame(hourly_rows)

    grid_cost = sum(value(model.grid_buy[t]) * value(model.grid_price[t]) for t in model.T)
    gas_cost = sum(
        value(model.gas_consumption[t]) * value(model.gas_price[t]) for t in model.T
    )
    curtailment_cost = sum(
        (value(model.pv_curtail[t]) + value(model.wind_curtail[t]))
        * value(model.curtail_penalty)
        for t in model.T
    )
    carbon_cost = sum(
        value(model.carbon_emission[t]) * value(model.carbon_price[t]) for t in model.T
    )
    battery_om_cost = sum(
        (value(model.battery_charge[t]) + value(model.battery_discharge[t]))
        * value(model.battery_om)
        for t in model.T
    )
    electrolyzer_om_cost = sum(
        value(model.h2_production[t]) * value(model.electrolyzer_om) for t in model.T
    )
    fuel_cell_om_cost = sum(
        value(model.fuel_cell_power[t]) * value(model.fuel_cell_om) for t in model.T
    )
    h2_external_supply_cost = sum(
        value(model.h2_external_supply[t]) * value(model.h2_external_supply_cost)
        for t in model.T
    )
    h2_sale_revenue = sum(
        value(model.h2_sale[t]) * value(model.h2_sale_price) for t in model.T
    )
    carbon_cap_excess_cost = value(model.carbon_cap_excess) * value(
        model.carbon_cap_excess_penalty
    )
    renewable_available = (
        hourly_results["pv_used_kw"].sum()
        + hourly_results["wind_used_kw"].sum()
        + hourly_results["pv_curtail_kw"].sum()
        + hourly_results["wind_curtail_kw"].sum()
    )
    renewable_used = (
        hourly_results["pv_used_kw"].sum() + hourly_results["wind_used_kw"].sum()
    )
    renewable_consumption_rate = (
        renewable_used / renewable_available if renewable_available > 0 else 0.0
    )

    summary = {
        "scenario_id": scenario_id,
        "status": status,
        "total_cost_cny": value(model.total_cost),
        "grid_cost_cny": grid_cost,
        "gas_cost_cny": gas_cost,
        "curtailment_cost_cny": curtailment_cost,
        "carbon_cost_cny": carbon_cost,
        "battery_om_cost_cny": battery_om_cost,
        "electrolyzer_om_cost_cny": electrolyzer_om_cost,
        "h2_external_supply_cost_cny": h2_external_supply_cost,
        "h2_sale_revenue_cny": h2_sale_revenue,
        "fuel_cell_om_cost_cny": fuel_cell_om_cost,
        "carbon_cap_excess_cost_cny": carbon_cap_excess_cost,
        "grid_purchase_kwh": hourly_results["grid_buy_kw"].sum(),
        "renewable_available_kwh": renewable_available,
        "renewable_used_kwh": renewable_used,
        "renewable_consumption_rate": renewable_consumption_rate,
        "renewable_min_consumption_rate": value(model.renewable_min_consumption_rate),
        "renewable_curtailment_kwh": (
            hourly_results["pv_curtail_kw"].sum()
            + hourly_results["wind_curtail_kw"].sum()
        ),
        "gas_consumption_m3": hourly_results["gas_consumption_m3"].sum(),
        "heat_pump_heat_kwh": hourly_results["heat_pump_heat_kw"].sum(),
        "gas_boiler_heat_kwh": hourly_results["gas_boiler_heat_kw"].sum(),
        "carbon_emission_kg": hourly_results["carbon_emission_kg"].sum(),
        "battery_charge_kwh": hourly_results["battery_charge_kw"].sum(),
        "battery_discharge_kwh": hourly_results["battery_discharge_kw"].sum(),
        "battery_soc_min_kwh": hourly_results["battery_soc_kwh"].min(),
        "battery_soc_max_kwh": hourly_results["battery_soc_kwh"].max(),
        "battery_terminal_delta_kwh": hourly_results["battery_soc_kwh"].iloc[-1]
        - value(model.battery_initial_soc),
        "hydrogen_load_kg": hourly_results["hydrogen_load_kg"].sum(),
        "electrolyzer_power_kwh": hourly_results["electrolyzer_power_kw"].sum(),
        "h2_production_kg": hourly_results["h2_production_kg"].sum(),
        "h2_external_supply_kg": hourly_results["h2_external_supply_kg"].sum(),
        "h2_sale_kg": hourly_results["h2_sale_kg"].sum(),
        "h2_fuel_cell_kg": hourly_results["h2_fuel_cell_kg"].sum(),
        "fuel_cell_generation_kwh": hourly_results["fuel_cell_power_kw"].sum(),
        "h2_storage_min_kg": hourly_results["h2_storage_kg"].min(),
        "h2_storage_max_kg": hourly_results["h2_storage_kg"].max(),
        "max_power_balance_residual_kw": hourly_results[
            "power_balance_residual_kw"
        ].abs().max(),
        "max_heat_balance_residual_kw": hourly_results[
            "heat_balance_residual_kw"
        ].abs().max(),
        "max_hydrogen_balance_residual_kg": hourly_results[
            "hydrogen_balance_residual_kg"
        ].abs().max(),
        "max_fuel_cell_conversion_residual_kw": hourly_results[
            "fuel_cell_conversion_residual_kw"
        ].abs().max(),
        "carbon_emission_cap_kg": value(model.carbon_emission_cap),
        "carbon_cap_excess_kg": value(model.carbon_cap_excess),
    }

    return ScenarioResult(
        scenario_id=scenario_id,
        status=status,
        hourly_results=hourly_results,
        summary=summary,
    )
