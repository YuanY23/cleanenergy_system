"""电池储能和储氢状态约束模块。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def add_battery_constraints(model: ConcreteModel) -> None:
    """加入电池充放电、SOC 和互斥约束。"""

    def battery_charge_limit_rule(m, t):
        # 充电功率受额定功率和充电状态共同限制。
        return m.battery_charge[t] <= m.is_battery_charging[t] * m.battery_power_max

    model.battery_charge_limit_constraint = Constraint(
        model.T, rule=battery_charge_limit_rule
    )

    def battery_discharge_limit_rule(m, t):
        # 放电功率受额定功率和放电状态共同限制。
        return m.battery_discharge[t] <= m.is_battery_discharging[t] * m.battery_power_max

    model.battery_discharge_limit_constraint = Constraint(
        model.T, rule=battery_discharge_limit_rule
    )

    def battery_exclusive_rule(m, t):
        # 同一小时不能同时充电和放电。
        return m.is_battery_charging[t] + m.is_battery_discharging[t] <= 1

    model.battery_exclusive_constraint = Constraint(model.T, rule=battery_exclusive_rule)

    def battery_soc_rule(m, t):
        # SOC 表示每个小时结束后的电池电量。
        previous_soc = m.battery_initial_soc if t == 0 else m.battery_soc[t - 1]
        return (
            m.battery_soc[t]
            == previous_soc
            + m.battery_charge[t] * m.battery_eta_ch
            - m.battery_discharge[t] / m.battery_eta_dis
        )

    model.battery_soc_constraint = Constraint(model.T, rule=battery_soc_rule)

    def battery_soc_capacity_rule(m, t):
        # SOC 不能超过电池额定容量。
        return m.battery_soc[t] <= m.battery_energy_max

    model.battery_soc_capacity_constraint = Constraint(
        model.T, rule=battery_soc_capacity_rule
    )

    def battery_terminal_rule(m):
        # 末端 SOC 等于初始 SOC，避免模型把电池最后放空。
        return m.battery_soc[m.T.last()] == m.battery_initial_soc

    model.battery_terminal_constraint = Constraint(rule=battery_terminal_rule)

    def battery_degradation_throughput_rule(m, t):
        return (
            sum(
                m.battery_degradation_throughput_segment[t, segment]
                for segment in m.BATTERY_DEGRADATION_SEGMENTS
            )
            == m.battery_charge[t] + m.battery_discharge[t]
        )

    model.battery_degradation_throughput_constraint = Constraint(
        model.T, rule=battery_degradation_throughput_rule
    )

    def battery_degradation_segment_limit_rule(m, t, segment):
        return (
            m.battery_degradation_throughput_segment[t, segment]
            <= m.battery_degradation_segment_width_rate[segment]
            * m.battery_energy_max
        )

    model.battery_degradation_segment_limit_constraint = Constraint(
        model.T,
        model.BATTERY_DEGRADATION_SEGMENTS,
        rule=battery_degradation_segment_limit_rule,
    )
