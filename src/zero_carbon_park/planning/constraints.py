"""容量规划约束。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def _upper_bound(variable, fallback: float) -> float:
    return float(variable.ub) if variable.ub is not None else fallback


def add_planning_constraints(model: ConcreteModel) -> None:
    """添加容量规划和运行调度耦合约束。"""

    def pv_available_rule(m, d, t):
        return (
            m.pv_used[d, t] + m.pv_sold[d, t] + m.pv_curtail[d, t]
            == m.pv_capacity_kw * m.pv_cf[d, t]
        )

    model.pv_available_constraint = Constraint(model.D, model.T, rule=pv_available_rule)

    def wind_available_rule(m, d, t):
        return (
            m.wind_used[d, t] + m.wind_curtail[d, t]
            + m.wind_sold[d, t]
            == m.wind_capacity_kw * m.wind_cf[d, t]
        )

    model.wind_available_constraint = Constraint(model.D, model.T, rule=wind_available_rule)

    def power_balance_rule(m, d, t):
        return (
            m.grid_buy[d, t]
            + m.pv_used[d, t]
            + m.wind_used[d, t]
            + m.battery_discharge[d, t]
            + m.fuel_cell_power[d, t]
            == m.electric_load[d, t]
            + m.heat_pump_power[d, t]
            + m.battery_charge[d, t]
            + m.electrolyzer_power[d, t]
        )

    model.power_balance_constraint = Constraint(model.D, model.T, rule=power_balance_rule)

    def green_power_share_rule(m):
        renewable_used = sum(
            m.weight_days[d] * (m.pv_used[d, t] + m.wind_used[d, t])
            for d in m.D
            for t in m.T
        )
        electricity_demand = sum(
            m.weight_days[d]
            * (
                m.electric_load[d, t]
                + m.heat_pump_power[d, t]
                + m.battery_charge[d, t]
                + m.electrolyzer_power[d, t]
            )
            for d in m.D
            for t in m.T
        )
        return renewable_used >= m.green_power_min_share * electricity_demand

    model.green_power_share_constraint = Constraint(rule=green_power_share_rule)

    def grid_sell_definition_rule(m, d, t):
        return m.grid_sell[d, t] == m.pv_sold[d, t] + m.wind_sold[d, t]

    model.grid_sell_definition_constraint = Constraint(
        model.D, model.T, rule=grid_sell_definition_rule
    )

    def grid_export_limit_rule(m, d, t):
        return m.grid_sell[d, t] <= m.grid_export_limit_kw

    model.grid_export_limit_constraint = Constraint(
        model.D, model.T, rule=grid_export_limit_rule
    )

    def grid_import_peak_rule(m, d, t):
        return m.grid_buy[d, t] <= m.grid_import_peak_kw

    model.grid_import_peak_constraint = Constraint(
        model.D, model.T, rule=grid_import_peak_rule
    )

    def heat_pump_capacity_rule(m, d, t):
        return (
            m.heat_pump_power[d, t]
            <= m.heat_pump_power_capacity_kw * m.heat_pump_available_ratio[d, t]
        )

    model.heat_pump_capacity_constraint = Constraint(
        model.D, model.T, rule=heat_pump_capacity_rule
    )

    def heat_pump_conversion_rule(m, d, t):
        return m.heat_pump_heat[d, t] == m.heat_pump_power[d, t] * m.heat_pump_cop[d, t]

    model.heat_pump_conversion_constraint = Constraint(
        model.D, model.T, rule=heat_pump_conversion_rule
    )

    def gas_boiler_capacity_rule(m, d, t):
        return m.gas_boiler_heat[d, t] <= m.gas_boiler_heat_max

    model.gas_boiler_capacity_constraint = Constraint(
        model.D, model.T, rule=gas_boiler_capacity_rule
    )

    def gas_consumption_rule(m, d, t):
        return (
            m.gas_consumption[d, t]
            == m.gas_boiler_heat[d, t] / m.gas_boiler_eff / m.gas_lhv
        )

    model.gas_consumption_constraint = Constraint(
        model.D, model.T, rule=gas_consumption_rule
    )

    def heat_balance_rule(m, d, t):
        return m.heat_pump_heat[d, t] + m.gas_boiler_heat[d, t] == m.heat_load[d, t]

    model.heat_balance_constraint = Constraint(model.D, model.T, rule=heat_balance_rule)

    def battery_charge_limit_rule(m, d, t):
        return m.battery_charge[d, t] <= m.battery_power_capacity_kw

    model.battery_charge_limit_constraint = Constraint(
        model.D, model.T, rule=battery_charge_limit_rule
    )

    def battery_discharge_limit_rule(m, d, t):
        return m.battery_discharge[d, t] <= m.battery_power_capacity_kw

    model.battery_discharge_limit_constraint = Constraint(
        model.D, model.T, rule=battery_discharge_limit_rule
    )

    def battery_soc_rule(m, d, t):
        previous_soc = (
            0.5 * m.battery_energy_capacity_kwh
            if t == m.T.first()
            else m.battery_soc[d, t - 1]
        )
        return (
            m.battery_soc[d, t]
            == previous_soc
            + m.battery_charge[d, t] * m.battery_eta_ch
            - m.battery_discharge[d, t] / m.battery_eta_dis
        )

    model.battery_soc_constraint = Constraint(model.D, model.T, rule=battery_soc_rule)

    def battery_soc_capacity_rule(m, d, t):
        return m.battery_soc[d, t] <= m.battery_energy_capacity_kwh

    model.battery_soc_capacity_constraint = Constraint(
        model.D, model.T, rule=battery_soc_capacity_rule
    )

    def battery_terminal_rule(m, d):
        return m.battery_soc[d, m.T.last()] == 0.5 * m.battery_energy_capacity_kwh

    model.battery_terminal_constraint = Constraint(model.D, rule=battery_terminal_rule)

    def battery_degradation_throughput_rule(m, d, t):
        return (
            sum(
                m.battery_degradation_throughput_segment[d, t, segment]
                for segment in m.BATTERY_DEGRADATION_SEGMENTS
            )
            == m.battery_charge[d, t] + m.battery_discharge[d, t]
        )

    model.battery_degradation_throughput_constraint = Constraint(
        model.D, model.T, rule=battery_degradation_throughput_rule
    )

    def battery_degradation_segment_limit_rule(m, d, t, segment):
        return (
            m.battery_degradation_throughput_segment[d, t, segment]
            <= m.battery_degradation_segment_width_rate[segment]
            * m.battery_energy_capacity_kwh
        )

    model.battery_degradation_segment_limit_constraint = Constraint(
        model.D,
        model.T,
        model.BATTERY_DEGRADATION_SEGMENTS,
        rule=battery_degradation_segment_limit_rule,
    )

    def electrolyzer_capacity_rule(m, d, t):
        return m.electrolyzer_power[d, t] <= m.electrolyzer_power_capacity_kw

    model.electrolyzer_capacity_constraint = Constraint(
        model.D, model.T, rule=electrolyzer_capacity_rule
    )

    def electrolyzer_on_capacity_rule(m, d, t):
        return (
            m.electrolyzer_power[d, t]
            <= _upper_bound(m.electrolyzer_power_capacity_kw, 1.0e7)
            * m.is_electrolyzer_on[d, t]
        )

    model.electrolyzer_on_capacity_constraint = Constraint(
        model.D, model.T, rule=electrolyzer_on_capacity_rule
    )

    def electrolyzer_min_load_rule(m, d, t):
        return (
            m.electrolyzer_power[d, t]
            >= m.electrolyzer_min_load_rate * m.electrolyzer_power_capacity_kw
            - _upper_bound(m.electrolyzer_power_capacity_kw, 1.0e7)
            * (1 - m.is_electrolyzer_on[d, t])
        )

    model.electrolyzer_min_load_constraint = Constraint(
        model.D, model.T, rule=electrolyzer_min_load_rule
    )

    def electrolyzer_power_segment_sum_rule(m, d, t):
        return (
            m.electrolyzer_power[d, t]
            == sum(
                m.electrolyzer_power_segment[d, t, segment]
                for segment in m.ELECTROLYZER_SEGMENTS
            )
        )

    model.electrolyzer_power_segment_sum_constraint = Constraint(
        model.D, model.T, rule=electrolyzer_power_segment_sum_rule
    )

    def electrolyzer_power_segment_limit_rule(m, d, t, segment):
        return (
            m.electrolyzer_power_segment[d, t, segment]
            <= m.electrolyzer_segment_power_fraction[segment]
            * m.electrolyzer_power_capacity_kw
        )

    model.electrolyzer_power_segment_limit_constraint = Constraint(
        model.D,
        model.T,
        model.ELECTROLYZER_SEGMENTS,
        rule=electrolyzer_power_segment_limit_rule,
    )

    def electrolyzer_production_segment_rule(m, d, t, segment):
        return (
            m.h2_production_segment[d, t, segment]
            == m.electrolyzer_power_segment[d, t, segment]
            / m.electrolyzer_segment_kwh_per_kg[segment]
        )

    model.electrolyzer_production_segment_constraint = Constraint(
        model.D,
        model.T,
        model.ELECTROLYZER_SEGMENTS,
        rule=electrolyzer_production_segment_rule,
    )

    def hydrogen_production_rule(m, d, t):
        return (
            m.h2_production[d, t]
            == sum(
                m.h2_production_segment[d, t, segment]
                for segment in m.ELECTROLYZER_SEGMENTS
            )
        )

    model.hydrogen_production_constraint = Constraint(
        model.D, model.T, rule=hydrogen_production_rule
    )

    def h2_storage_rule(m, d, t):
        previous_storage = (
            0.3 * m.h2_storage_capacity_kg
            if t == m.T.first()
            else m.h2_storage[d, t - 1]
        )
        return (
            m.h2_storage[d, t]
            == previous_storage * (1 - m.h2_storage_loss_rate_per_hour)
            + m.h2_charge[d, t]
            - m.h2_discharge[d, t]
        )

    model.h2_storage_constraint = Constraint(model.D, model.T, rule=h2_storage_rule)

    def h2_storage_capacity_rule(m, d, t):
        return m.h2_storage[d, t] <= m.h2_storage_capacity_kg

    model.h2_storage_capacity_constraint = Constraint(
        model.D, model.T, rule=h2_storage_capacity_rule
    )

    def h2_storage_terminal_rule(m, d):
        return m.h2_storage[d, m.T.last()] == 0.3 * m.h2_storage_capacity_kg

    model.h2_storage_terminal_constraint = Constraint(
        model.D, rule=h2_storage_terminal_rule
    )

    def fuel_cell_capacity_rule(m, d, t):
        return m.fuel_cell_power[d, t] <= m.fuel_cell_power_capacity_kw

    model.fuel_cell_capacity_constraint = Constraint(
        model.D, model.T, rule=fuel_cell_capacity_rule
    )

    def fuel_cell_on_capacity_rule(m, d, t):
        return (
            m.fuel_cell_power[d, t]
            <= _upper_bound(m.fuel_cell_power_capacity_kw, 1.0e7)
            * m.is_fuel_cell_on[d, t]
        )

    model.fuel_cell_on_capacity_constraint = Constraint(
        model.D, model.T, rule=fuel_cell_on_capacity_rule
    )

    def fuel_cell_min_load_rule(m, d, t):
        return (
            m.fuel_cell_power[d, t]
            >= m.fuel_cell_min_load_rate * m.fuel_cell_power_capacity_kw
            - _upper_bound(m.fuel_cell_power_capacity_kw, 1.0e7)
            * (1 - m.is_fuel_cell_on[d, t])
        )

    model.fuel_cell_min_load_constraint = Constraint(
        model.D, model.T, rule=fuel_cell_min_load_rule
    )

    def fuel_cell_power_segment_sum_rule(m, d, t):
        return (
            m.fuel_cell_power[d, t]
            == sum(
                m.fuel_cell_power_segment[d, t, segment]
                for segment in m.FUEL_CELL_SEGMENTS
            )
        )

    model.fuel_cell_power_segment_sum_constraint = Constraint(
        model.D, model.T, rule=fuel_cell_power_segment_sum_rule
    )

    def fuel_cell_power_segment_limit_rule(m, d, t, segment):
        return (
            m.fuel_cell_power_segment[d, t, segment]
            <= m.fuel_cell_segment_power_fraction[segment]
            * m.fuel_cell_power_capacity_kw
        )

    model.fuel_cell_power_segment_limit_constraint = Constraint(
        model.D,
        model.T,
        model.FUEL_CELL_SEGMENTS,
        rule=fuel_cell_power_segment_limit_rule,
    )

    def fuel_cell_conversion_segment_rule(m, d, t, segment):
        return (
            m.fuel_cell_power_segment[d, t, segment]
            == m.h2_fuel_cell_segment[d, t, segment]
            * m.fuel_cell_segment_kwh_per_kg[segment]
        )

    model.fuel_cell_conversion_segment_constraint = Constraint(
        model.D,
        model.T,
        model.FUEL_CELL_SEGMENTS,
        rule=fuel_cell_conversion_segment_rule,
    )

    def fuel_cell_conversion_rule(m, d, t):
        return (
            m.h2_fuel_cell[d, t]
            == sum(
                m.h2_fuel_cell_segment[d, t, segment]
                for segment in m.FUEL_CELL_SEGMENTS
            )
        )

    model.fuel_cell_conversion_constraint = Constraint(
        model.D, model.T, rule=fuel_cell_conversion_rule
    )

    def hydrogen_balance_rule(m, d, t):
        return (
            m.h2_production[d, t]
            + m.h2_discharge[d, t]
            + m.h2_external_supply[d, t]
            == m.hydrogen_load[d, t] + m.h2_charge[d, t] + m.h2_fuel_cell[d, t]
        )

    model.hydrogen_balance_constraint = Constraint(
        model.D, model.T, rule=hydrogen_balance_rule
    )

    def fuel_cell_backup_capacity_rule(m):
        return m.fuel_cell_backup_capacity_kw <= m.fuel_cell_power_capacity_kw

    model.fuel_cell_backup_capacity_constraint = Constraint(
        rule=fuel_cell_backup_capacity_rule
    )

    def fuel_cell_backup_reserve_limit_rule(m):
        return m.fuel_cell_backup_capacity_kw <= m.fuel_cell_backup_reserve_kw

    model.fuel_cell_backup_reserve_limit_constraint = Constraint(
        rule=fuel_cell_backup_reserve_limit_rule
    )

    def fuel_cell_backup_required_rule(m):
        return m.fuel_cell_power_capacity_kw >= m.fuel_cell_backup_required_kw

    model.fuel_cell_backup_required_constraint = Constraint(
        rule=fuel_cell_backup_required_rule
    )

    def carbon_emission_rule(m, d, t):
        return (
            m.carbon_emission[d, t]
            == m.grid_buy[d, t] * m.grid_emission_factor[d, t]
            + m.gas_consumption[d, t] * m.gas_emission_factor
        )

    model.carbon_emission_constraint = Constraint(
        model.D, model.T, rule=carbon_emission_rule
    )

    def annual_carbon_cap_rule(m):
        return (
            sum(
                m.weight_days[d] * m.carbon_emission[d, t]
                for d in m.D
                for t in m.T
            )
            <= m.annual_carbon_emission_cap_kg
        )

    model.annual_carbon_cap_constraint = Constraint(rule=annual_carbon_cap_rule)
