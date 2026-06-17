"""模型目标函数定义模块。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Objective, minimize


def add_total_cost_objective(model: ConcreteModel) -> None:
    """加入总运行成本目标函数。"""

    def objective_rule(m):
        # 目标函数：购电、天然气、弃风弃光、碳排放和各设备运行维护成本之和。
        return sum(
            m.grid_buy[t] * m.grid_price[t]
            + m.gas_consumption[t] * m.gas_price[t]
            + (m.pv_curtail[t] + m.wind_curtail[t]) * m.curtail_penalty
            + m.carbon_emission[t] * m.carbon_price[t]
            + (m.battery_charge[t] + m.battery_discharge[t]) * m.battery_om
            + m.h2_production[t] * m.electrolyzer_om
            + m.h2_external_supply[t] * m.h2_external_supply_cost
            + m.fuel_cell_power[t] * m.fuel_cell_om
            - m.h2_sale[t] * m.h2_sale_price
            for t in m.T
        ) + m.carbon_cap_excess * m.carbon_cap_excess_penalty

    model.total_cost = Objective(rule=objective_rule, sense=minimize)
