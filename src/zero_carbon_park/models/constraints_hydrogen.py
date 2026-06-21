"""氢气平衡与氢能设备约束模块。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def add_hydrogen_constraints(model: ConcreteModel) -> None:
    """加入电解槽、储氢罐、燃料电池和氢负荷平衡约束。"""

    def electrolyzer_capacity_rule(m, t):
        # 电解槽耗电功率受额定功率和运行状态共同限制。
        return m.electrolyzer_power[t] <= m.is_electrolyzer_on[t] * m.electrolyzer_power_max

    model.electrolyzer_capacity_constraint = Constraint(
        model.T, rule=electrolyzer_capacity_rule
    )

    def electrolyzer_min_load_rule(m, t):
        return (
            m.electrolyzer_power[t]
            >= m.is_electrolyzer_on[t]
            * m.electrolyzer_power_max
            * m.electrolyzer_min_load_rate
        )

    model.electrolyzer_min_load_constraint = Constraint(
        model.T, rule=electrolyzer_min_load_rule
    )

    def electrolyzer_power_segment_sum_rule(m, t):
        return (
            m.electrolyzer_power[t]
            == sum(
                m.electrolyzer_power_segment[t, segment]
                for segment in m.ELECTROLYZER_SEGMENTS
            )
        )

    model.electrolyzer_power_segment_sum_constraint = Constraint(
        model.T, rule=electrolyzer_power_segment_sum_rule
    )

    def electrolyzer_power_segment_limit_rule(m, t, segment):
        return (
            m.electrolyzer_power_segment[t, segment]
            <= m.electrolyzer_power_max
            * m.electrolyzer_segment_power_fraction[segment]
        )

    model.electrolyzer_power_segment_limit_constraint = Constraint(
        model.T,
        model.ELECTROLYZER_SEGMENTS,
        rule=electrolyzer_power_segment_limit_rule,
    )

    def electrolyzer_production_segment_rule(m, t, segment):
        return (
            m.h2_production_segment[t, segment]
            == m.electrolyzer_power_segment[t, segment]
            / m.electrolyzer_segment_kwh_per_kg[segment]
        )

    model.electrolyzer_production_segment_constraint = Constraint(
        model.T,
        model.ELECTROLYZER_SEGMENTS,
        rule=electrolyzer_production_segment_rule,
    )

    def hydrogen_production_rule(m, t):
        return (
            m.h2_production[t]
            == sum(
                m.h2_production_segment[t, segment]
                for segment in m.ELECTROLYZER_SEGMENTS
            )
        )

    model.hydrogen_production_constraint = Constraint(
        model.T, rule=hydrogen_production_rule
    )

    def fuel_cell_capacity_rule(m, t):
        # 燃料电池发电功率受额定功率和运行状态共同限制。
        return m.fuel_cell_power[t] <= m.is_fuel_cell_on[t] * m.fuel_cell_power_max

    model.fuel_cell_capacity_constraint = Constraint(
        model.T, rule=fuel_cell_capacity_rule
    )

    def fuel_cell_min_load_rule(m, t):
        return (
            m.fuel_cell_power[t]
            >= m.is_fuel_cell_on[t]
            * m.fuel_cell_power_max
            * m.fuel_cell_min_load_rate
        )

    model.fuel_cell_min_load_constraint = Constraint(
        model.T, rule=fuel_cell_min_load_rule
    )

    def fuel_cell_power_segment_sum_rule(m, t):
        return (
            m.fuel_cell_power[t]
            == sum(
                m.fuel_cell_power_segment[t, segment]
                for segment in m.FUEL_CELL_SEGMENTS
            )
        )

    model.fuel_cell_power_segment_sum_constraint = Constraint(
        model.T, rule=fuel_cell_power_segment_sum_rule
    )

    def fuel_cell_power_segment_limit_rule(m, t, segment):
        return (
            m.fuel_cell_power_segment[t, segment]
            <= m.fuel_cell_power_max * m.fuel_cell_segment_power_fraction[segment]
        )

    model.fuel_cell_power_segment_limit_constraint = Constraint(
        model.T,
        model.FUEL_CELL_SEGMENTS,
        rule=fuel_cell_power_segment_limit_rule,
    )

    def fuel_cell_conversion_segment_rule(m, t, segment):
        return (
            m.fuel_cell_power_segment[t, segment]
            == m.h2_fuel_cell_segment[t, segment]
            * m.fuel_cell_segment_kwh_per_kg[segment]
        )

    model.fuel_cell_conversion_segment_constraint = Constraint(
        model.T,
        model.FUEL_CELL_SEGMENTS,
        rule=fuel_cell_conversion_segment_rule,
    )

    def fuel_cell_conversion_rule(m, t):
        return (
            m.h2_fuel_cell[t]
            == sum(
                m.h2_fuel_cell_segment[t, segment]
                for segment in m.FUEL_CELL_SEGMENTS
            )
        )

    model.fuel_cell_conversion_constraint = Constraint(
        model.T, rule=fuel_cell_conversion_rule
    )

    def hydrogen_balance_rule(m, t):
        # 氢气平衡：制氢、放氢和外部补氢满足氢负荷、充氢、售氢和燃料电池耗氢。
        return (
            m.h2_production[t] + m.h2_discharge[t] + m.h2_external_supply[t]
            == m.hydrogen_load[t] + m.h2_charge[t] + m.h2_sale[t] + m.h2_fuel_cell[t]
        )

    model.hydrogen_balance_constraint = Constraint(model.T, rule=hydrogen_balance_rule)

    def h2_storage_rule(m, t):
        # 储氢量表示每个小时结束后的储氢库存。
        previous_storage = m.h2_storage_initial if t == 0 else m.h2_storage[t - 1]
        return (
            m.h2_storage[t]
            == previous_storage * (1 - m.h2_storage_loss_rate_per_hour)
            + m.h2_charge[t]
            - m.h2_discharge[t]
        )

    model.h2_storage_constraint = Constraint(model.T, rule=h2_storage_rule)

    def h2_storage_capacity_rule(m, t):
        # 储氢量不能超过储氢罐容量。
        return m.h2_storage[t] <= m.h2_storage_capacity

    model.h2_storage_capacity_constraint = Constraint(
        model.T, rule=h2_storage_capacity_rule
    )
