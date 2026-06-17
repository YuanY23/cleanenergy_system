"""电力平衡与电力设备约束模块。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def add_renewable_constraints(model: ConcreteModel) -> None:
    """加入风电、光伏利用和弃电约束。"""

    def pv_available_rule(m, t):
        # 光伏利用和弃光之和等于该时刻可发功率。
        return m.pv_used[t] + m.pv_curtail[t] == m.pv_available[t]

    model.pv_available_constraint = Constraint(model.T, rule=pv_available_rule)

    def wind_available_rule(m, t):
        # 风电利用和弃风之和等于该时刻可发功率。
        return m.wind_used[t] + m.wind_curtail[t] == m.wind_available[t]

    model.wind_available_constraint = Constraint(model.T, rule=wind_available_rule)

    def renewable_consumption_rate_rule(m):
        # 新能源消纳率约束：总利用量 >= 最低消纳率 * 总可发量。
        renewable_used = sum(m.pv_used[t] + m.wind_used[t] for t in m.T)
        renewable_available = sum(m.pv_available[t] + m.wind_available[t] for t in m.T)
        return renewable_used >= m.renewable_min_consumption_rate * renewable_available

    model.renewable_consumption_rate_constraint = Constraint(
        rule=renewable_consumption_rate_rule
    )


def add_power_balance_constraints(model: ConcreteModel) -> None:
    """加入电力平衡约束。"""

    def power_balance_rule(m, t):
        # 电力平衡：电源侧等于电负荷、热泵耗电、充电和电解槽耗电。
        return (
            m.grid_buy[t]
            + m.pv_used[t]
            + m.wind_used[t]
            + m.battery_discharge[t]
            + m.fuel_cell_power[t]
            == m.electric_load[t]
            + m.heat_pump_power[t]
            + m.battery_charge[t]
            + m.electrolyzer_power[t]
        )

    model.power_balance_constraint = Constraint(model.T, rule=power_balance_rule)
