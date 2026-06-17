"""容量规划约束。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def add_planning_constraints(model: ConcreteModel) -> None:
    """添加容量规划和运行调度耦合约束。"""

    def pv_available_rule(m, d, t):
        return m.pv_used[d, t] + m.pv_curtail[d, t] == m.pv_capacity_kw * m.pv_cf[d, t]

    model.pv_available_constraint = Constraint(model.D, model.T, rule=pv_available_rule)

    def wind_available_rule(m, d, t):
        return (
            m.wind_used[d, t] + m.wind_curtail[d, t]
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

    def heat_pump_capacity_rule(m, d, t):
        return m.heat_pump_power[d, t] <= m.heat_pump_power_capacity_kw

    model.heat_pump_capacity_constraint = Constraint(
        model.D, model.T, rule=heat_pump_capacity_rule
    )

    def heat_pump_conversion_rule(m, d, t):
        return m.heat_pump_heat[d, t] == m.heat_pump_power[d, t] * m.heat_pump_cop

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

    def electrolyzer_capacity_rule(m, d, t):
        return m.electrolyzer_power[d, t] <= m.electrolyzer_power_capacity_kw

    model.electrolyzer_capacity_constraint = Constraint(
        model.D, model.T, rule=electrolyzer_capacity_rule
    )

    def hydrogen_production_rule(m, d, t):
        return (
            m.h2_production[d, t]
            == m.electrolyzer_power[d, t] / m.electrolyzer_kwh_per_kg
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
        return m.h2_storage[d, t] == previous_storage + m.h2_charge[d, t] - m.h2_discharge[d, t]

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

    def fuel_cell_conversion_rule(m, d, t):
        return m.fuel_cell_power[d, t] == m.h2_fuel_cell[d, t] * m.fuel_cell_kwh_per_kg

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
