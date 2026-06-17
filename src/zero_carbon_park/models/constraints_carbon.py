"""碳排放核算与碳成本约束模块。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def add_carbon_constraints(model: ConcreteModel) -> None:
    """加入碳排放核算约束。"""

    def carbon_emission_rule(m, t):
        # 碳排放 = 外购电间接排放 + 天然气燃烧直接排放。
        return (
            m.carbon_emission[t]
            == m.grid_buy[t] * m.grid_emission_factor[t]
            + m.gas_consumption[t] * m.gas_emission_factor
        )

    model.carbon_emission_constraint = Constraint(model.T, rule=carbon_emission_rule)

    def carbon_cap_rule(m):
        # 日总碳排放不能超过上限；若目标过严，则用超额变量记录缺口并施加高惩罚。
        return sum(m.carbon_emission[t] for t in m.T) <= m.carbon_emission_cap + m.carbon_cap_excess

    model.carbon_cap_constraint = Constraint(rule=carbon_cap_rule)
