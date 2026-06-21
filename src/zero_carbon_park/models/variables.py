"""模型决策变量定义模块。"""

from __future__ import annotations

from pyomo.environ import Binary, ConcreteModel, NonNegativeReals, Var


def add_decision_variables(model: ConcreteModel) -> None:
    """定义优化模型的全部决策变量。"""

    # 电力侧变量：电网购电、新能源利用量和弃电量。
    model.grid_buy = Var(model.T, domain=NonNegativeReals)
    model.pv_used = Var(model.T, domain=NonNegativeReals)
    model.pv_curtail = Var(model.T, domain=NonNegativeReals)
    model.wind_used = Var(model.T, domain=NonNegativeReals)
    model.wind_curtail = Var(model.T, domain=NonNegativeReals)

    # 热力侧变量：热泵、燃气锅炉和天然气消耗。
    model.heat_pump_power = Var(model.T, domain=NonNegativeReals)
    model.heat_pump_heat = Var(model.T, domain=NonNegativeReals)
    model.gas_boiler_heat = Var(model.T, domain=NonNegativeReals)
    model.gas_consumption = Var(model.T, domain=NonNegativeReals)
    model.is_heat_pump_on = Var(model.T, domain=Binary)

    # 电池变量：充电、放电、SOC，以及充放电状态二进制变量。
    model.battery_charge = Var(model.T, domain=NonNegativeReals)
    model.battery_discharge = Var(model.T, domain=NonNegativeReals)
    model.battery_soc = Var(model.T, domain=NonNegativeReals)
    model.is_battery_charging = Var(model.T, domain=Binary)
    model.is_battery_discharging = Var(model.T, domain=Binary)

    # 氢能变量：电解槽、储氢罐、氢负荷释放和燃料电池。
    model.electrolyzer_power = Var(model.T, domain=NonNegativeReals)
    model.electrolyzer_power_segment = Var(
        model.T, model.ELECTROLYZER_SEGMENTS, domain=NonNegativeReals
    )
    model.h2_production_segment = Var(
        model.T, model.ELECTROLYZER_SEGMENTS, domain=NonNegativeReals
    )
    model.h2_production = Var(model.T, domain=NonNegativeReals)
    model.h2_charge = Var(model.T, domain=NonNegativeReals)
    model.h2_discharge = Var(model.T, domain=NonNegativeReals)
    model.h2_storage = Var(model.T, domain=NonNegativeReals)
    model.is_electrolyzer_on = Var(model.T, domain=Binary)
    # 外部补氢变量只作为高氢负荷压力场景的可行性兜底，成本设置较高。
    model.h2_external_supply = Var(model.T, domain=NonNegativeReals)
    # 售氢量用于 v1.4 售氢收益场景；未启用售氢时价格为 0。
    model.h2_sale = Var(model.T, domain=NonNegativeReals)
    model.h2_fuel_cell = Var(model.T, domain=NonNegativeReals)
    model.h2_fuel_cell_segment = Var(
        model.T, model.FUEL_CELL_SEGMENTS, domain=NonNegativeReals
    )
    model.fuel_cell_power_segment = Var(
        model.T, model.FUEL_CELL_SEGMENTS, domain=NonNegativeReals
    )
    model.fuel_cell_power = Var(model.T, domain=NonNegativeReals)
    model.is_fuel_cell_on = Var(model.T, domain=Binary)

    model.battery_degradation_throughput_segment = Var(
        model.T, model.BATTERY_DEGRADATION_SEGMENTS, domain=NonNegativeReals
    )

    # 碳排放变量，单位 kgCO2。
    model.carbon_emission = Var(model.T, domain=NonNegativeReals)
    # 碳上限超额量用于避免过紧碳约束直接不可行，并在结果中暴露缺口。
    model.carbon_cap_excess = Var(domain=NonNegativeReals)
