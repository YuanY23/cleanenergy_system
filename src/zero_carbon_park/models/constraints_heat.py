"""热力平衡与供热设备约束模块。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def add_heat_constraints(model: ConcreteModel) -> None:
    """加入热泵、燃气锅炉和热力平衡约束。"""

    def heat_pump_capacity_rule(m, t):
        # 热泵耗电功率不能超过额定功率；是否可运行由场景开关控制。
        return (
            m.heat_pump_power[t]
            <= m.is_heat_pump_on[t]
            * m.heat_pump_power_max
            * m.heat_pump_available_ratio[t]
        )

    model.heat_pump_capacity_constraint = Constraint(
        model.T, rule=heat_pump_capacity_rule
    )

    def heat_pump_conversion_rule(m, t):
        # 热泵供热量等于耗电功率乘以 COP。
        return m.heat_pump_heat[t] == m.heat_pump_power[t] * m.heat_pump_cop[t]

    model.heat_pump_conversion_constraint = Constraint(
        model.T, rule=heat_pump_conversion_rule
    )

    def gas_boiler_capacity_rule(m, t):
        # 燃气锅炉供热功率不能超过设备上限。
        return m.gas_boiler_heat[t] <= m.gas_boiler_heat_max

    model.gas_boiler_capacity_constraint = Constraint(
        model.T, rule=gas_boiler_capacity_rule
    )

    def gas_consumption_rule(m, t):
        # 天然气消耗量 = 锅炉供热 / 锅炉效率 / 天然气低位热值。
        return m.gas_consumption[t] == m.gas_boiler_heat[t] / m.gas_boiler_eff / m.gas_lhv

    model.gas_consumption_constraint = Constraint(model.T, rule=gas_consumption_rule)

    def heat_balance_rule(m, t):
        # 热力平衡：热泵供热和锅炉供热共同满足热负荷。
        return m.heat_pump_heat[t] + m.gas_boiler_heat[t] == m.heat_load[t]

    model.heat_balance_constraint = Constraint(model.T, rule=heat_balance_rule)
