"""Physical constraints shared by capacity planning and fixed-capacity studies."""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint


def _upper_bound(variable, fallback: float) -> float:
    return float(variable.ub) if variable.ub is not None else fallback


def _initial_state(model, name: str, capacity_name: str, day):
    boundary = getattr(model, name)[day]
    if model._absolute_boundary_state[name]:
        return boundary
    return boundary * getattr(model, capacity_name)


def add_planning_constraints(model: ConcreteModel) -> None:
    """Add balances, availability, commitment, storage and policy constraints."""

    model.pv_available_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.pv_used[d, t] + m.pv_sold[d, t] + m.pv_curtail[d, t]
        == m.pv_capacity_kw * m.pv_cf[d, t] * m.pv_available_ratio[d, t],
    )
    model.wind_available_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.wind_used[d, t]
        + m.wind_sold[d, t]
        + m.wind_curtail[d, t]
        == m.wind_capacity_kw * m.wind_cf[d, t] * m.wind_available_ratio[d, t],
    )

    model.load_shed_critical_limit = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.load_shed_critical[d, t] <= m.critical_load[d, t],
    )
    model.load_shed_important_limit = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.load_shed_important[d, t] <= m.important_load[d, t],
    )
    model.load_shed_interruptible_limit = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.load_shed_interruptible[d, t]
        <= m.interruptible_load[d, t],
    )
    model.critical_supply_requirement = Constraint(
        model.D,
        rule=lambda m, d: sum(
            m.critical_load[d, t] - m.load_shed_critical[d, t] for t in m.T
        )
        >= m.critical_supply_min_ratio
        * sum(m.critical_load[d, t] for t in m.T),
    )
    # Engineering screening benchmark: dispatchable self-owned electric power
    # must cover the security load with the selected design margin. Renewable
    # nameplate is intentionally excluded because it is not firm capacity.
    model.secure_self_supply_capacity_constraint = Constraint(
        rule=lambda m: m.battery_power_capacity_kw + m.fuel_cell_power_capacity_kw
        >= m.secure_capacity_multiplier * m.peak_critical_load_kw
    )
    model.secure_battery_duration_constraint = Constraint(
        rule=lambda m: m.battery_energy_capacity_kwh
        >= m.secure_battery_duration_hours * m.battery_power_capacity_kw
    )

    def power_balance_rule(m, d, t):
        served_electric_load = (
            m.critical_load[d, t]
            + m.important_load[d, t]
            + m.interruptible_load[d, t]
            - m.load_shed_critical[d, t]
            - m.load_shed_important[d, t]
            - m.load_shed_interruptible[d, t]
        )
        return (
            m.grid_buy[d, t]
            + m.pv_used[d, t]
            + m.wind_used[d, t]
            + m.battery_discharge[d, t]
            + m.fuel_cell_power[d, t]
            == served_electric_load
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
    model.grid_sell_definition_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.grid_sell[d, t] == m.pv_sold[d, t] + m.wind_sold[d, t],
    )
    model.grid_export_limit_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.grid_sell[d, t]
        <= m.grid_export_limit_kw * m.grid_available_ratio[d, t],
    )
    model.grid_import_limit_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.grid_buy[d, t]
        <= m.grid_import_limit_kw * m.grid_available_ratio[d, t],
    )
    model.grid_import_peak_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.grid_buy[d, t] <= m.grid_import_peak_kw,
    )

    model.heat_pump_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.heat_pump_power[d, t]
        <= m.heat_pump_power_capacity_kw * m.heat_pump_available_ratio[d, t],
    )
    model.heat_pump_conversion_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.heat_pump_heat[d, t]
        == m.heat_pump_power[d, t] * m.heat_pump_cop[d, t],
    )
    model.gas_boiler_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.gas_boiler_heat[d, t]
        <= m.gas_boiler_heat_max * m.gas_boiler_available_ratio[d, t],
    )
    model.gas_consumption_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.gas_consumption[d, t]
        == m.gas_boiler_heat[d, t] / m.gas_boiler_eff / m.gas_lhv,
    )
    model.heat_balance_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.heat_pump_heat[d, t] + m.gas_boiler_heat[d, t]
        == m.heat_load[d, t],
    )

    battery_power_big_m = _upper_bound(model.battery_power_capacity_kw, 1.0e9)
    model.battery_charge_limit_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.battery_charge[d, t]
        <= m.battery_power_capacity_kw * m.battery_available_ratio[d, t],
    )
    model.battery_discharge_limit_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.battery_discharge[d, t]
        <= m.battery_power_capacity_kw * m.battery_available_ratio[d, t],
    )
    model.battery_charge_mode_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.battery_charge[d, t]
        <= battery_power_big_m * m.is_battery_charging[d, t],
    )
    model.battery_discharge_mode_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.battery_discharge[d, t]
        <= battery_power_big_m * (1 - m.is_battery_charging[d, t]),
    )

    def battery_soc_rule(m, d, t):
        previous = (
            _initial_state(m, "initial_battery_soc_kwh", "battery_energy_capacity_kwh", d)
            if t == m.T.first()
            else m.battery_soc[d, t - 1]
        )
        return m.battery_soc[d, t] == (
            previous
            + m.battery_charge[d, t] * m.battery_eta_ch
            - m.battery_discharge[d, t] / m.battery_eta_dis
        )

    model.battery_soc_constraint = Constraint(model.D, model.T, rule=battery_soc_rule)
    model.battery_soc_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.battery_soc[d, t] <= m.battery_energy_capacity_kwh,
    )

    def battery_terminal_rule(m, d):
        terminal = _initial_state(
            m, "final_battery_soc_kwh", "battery_energy_capacity_kwh", d
        )
        return m.battery_soc[d, m.T.last()] == terminal

    model.battery_terminal_constraint = Constraint(model.D, rule=battery_terminal_rule)
    model.battery_degradation_throughput_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: sum(
            m.battery_degradation_throughput_segment[d, t, segment]
            for segment in m.BATTERY_DEGRADATION_SEGMENTS
        )
        == m.battery_charge[d, t] + m.battery_discharge[d, t],
    )
    model.battery_degradation_segment_limit_constraint = Constraint(
        model.D,
        model.T,
        model.BATTERY_DEGRADATION_SEGMENTS,
        rule=lambda m, d, t, segment: m.battery_degradation_throughput_segment[
            d, t, segment
        ]
        <= m.battery_degradation_segment_width_rate[segment]
        * m.battery_energy_capacity_kwh,
    )

    electrolyzer_big_m = _upper_bound(model.electrolyzer_power_capacity_kw, 1.0e9)
    model.electrolyzer_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.electrolyzer_power[d, t]
        <= m.electrolyzer_power_capacity_kw * m.electrolyzer_available_ratio[d, t],
    )
    model.electrolyzer_on_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.electrolyzer_power[d, t]
        <= electrolyzer_big_m * m.is_electrolyzer_on[d, t],
    )
    model.electrolyzer_min_load_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.electrolyzer_power[d, t]
        >= m.electrolyzer_min_load_rate * m.electrolyzer_power_capacity_kw
        - electrolyzer_big_m * (1 - m.is_electrolyzer_on[d, t]),
    )
    model.electrolyzer_power_segment_sum_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.electrolyzer_power[d, t]
        == sum(
            m.electrolyzer_power_segment[d, t, segment]
            for segment in m.ELECTROLYZER_SEGMENTS
        ),
    )
    model.electrolyzer_power_segment_limit_constraint = Constraint(
        model.D,
        model.T,
        model.ELECTROLYZER_SEGMENTS,
        rule=lambda m, d, t, segment: m.electrolyzer_power_segment[d, t, segment]
        <= m.electrolyzer_segment_power_fraction[segment]
        * m.electrolyzer_power_capacity_kw,
    )

    electrolyzer_segments = list(model.ELECTROLYZER_SEGMENTS)
    electrolyzer_previous = {
        segment: electrolyzer_segments[index - 1]
        for index, segment in enumerate(electrolyzer_segments)
        if index > 0
    }
    if model.performance_curve_mode == "constant_efficiency":
        for variable in model.electrolyzer_segment_active.values():
            variable.fix(0)
    model.electrolyzer_constant_efficiency_distribution_constraint = Constraint(
        model.D,
        model.T,
        model.ELECTROLYZER_SEGMENTS,
        rule=lambda m, d, t, segment: (
            m.electrolyzer_power_segment[d, t, segment]
            == m.electrolyzer_segment_power_fraction[segment]
            * m.electrolyzer_power[d, t]
            if m.performance_curve_mode == "constant_efficiency"
            else Constraint.Skip
        ),
    )
    model.electrolyzer_segment_activation_constraint = Constraint(
        model.D,
        model.T,
        model.ELECTROLYZER_ORDERED_SEGMENTS,
        rule=lambda m, d, t, segment: (
            m.electrolyzer_power_segment[d, t, segment]
            <= electrolyzer_big_m * m.electrolyzer_segment_active[d, t, segment]
            if m.performance_curve_mode == "ordered_incremental"
            else Constraint.Skip
        ),
    )
    model.electrolyzer_segment_fill_constraint = Constraint(
        model.D,
        model.T,
        model.ELECTROLYZER_ORDERED_SEGMENTS,
        rule=lambda m, d, t, segment: (
            m.electrolyzer_power_segment[d, t, electrolyzer_previous[segment]]
            >= m.electrolyzer_segment_power_fraction[electrolyzer_previous[segment]]
            * m.electrolyzer_power_capacity_kw
            - electrolyzer_big_m * (1 - m.electrolyzer_segment_active[d, t, segment])
            if m.performance_curve_mode == "ordered_incremental"
            else Constraint.Skip
        ),
    )
    model.electrolyzer_production_segment_constraint = Constraint(
        model.D,
        model.T,
        model.ELECTROLYZER_SEGMENTS,
        rule=lambda m, d, t, segment: m.h2_production_segment[d, t, segment]
        == m.electrolyzer_power_segment[d, t, segment]
        / m.electrolyzer_segment_kwh_per_kg[segment],
    )
    model.hydrogen_production_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_production[d, t]
        == sum(
            m.h2_production_segment[d, t, segment]
            for segment in m.ELECTROLYZER_SEGMENTS
        ),
    )

    def electrolyzer_ramp_up_rule(m, d, t):
        if t == m.T.first():
            return Constraint.Skip
        return m.electrolyzer_power[d, t] - m.electrolyzer_power[d, t - 1] <= (
            m.electrolyzer_ramp_rate_per_hour * m.electrolyzer_power_capacity_kw
        )

    def electrolyzer_ramp_down_rule(m, d, t):
        if t == m.T.first():
            return Constraint.Skip
        return m.electrolyzer_power[d, t - 1] - m.electrolyzer_power[d, t] <= (
            m.electrolyzer_ramp_rate_per_hour * m.electrolyzer_power_capacity_kw
        )

    model.electrolyzer_ramp_up_constraint = Constraint(
        model.D, model.T, rule=electrolyzer_ramp_up_rule
    )
    model.electrolyzer_ramp_down_constraint = Constraint(
        model.D, model.T, rule=electrolyzer_ramp_down_rule
    )

    h2_big_m = _upper_bound(model.h2_storage_capacity_kg, 1.0e9)
    model.h2_charge_rate_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_charge[d, t]
        <= m.h2_storage_charge_rate_per_hour * m.h2_storage_capacity_kg,
    )
    model.h2_discharge_rate_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_discharge[d, t]
        <= m.h2_storage_discharge_rate_per_hour * m.h2_storage_capacity_kg,
    )
    model.h2_charge_mode_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_charge[d, t]
        <= h2_big_m * m.is_h2_charging[d, t],
    )
    model.h2_discharge_mode_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_discharge[d, t]
        <= h2_big_m * (1 - m.is_h2_charging[d, t]),
    )

    def h2_storage_rule(m, d, t):
        previous = (
            _initial_state(m, "initial_h2_inventory_kg", "h2_storage_capacity_kg", d)
            if t == m.T.first()
            else m.h2_storage[d, t - 1]
        )
        return m.h2_storage[d, t] == (
            previous * (1 - m.h2_storage_loss_rate_per_hour)
            + m.h2_charge[d, t]
            - m.h2_discharge[d, t]
        )

    model.h2_storage_constraint = Constraint(model.D, model.T, rule=h2_storage_rule)
    model.h2_storage_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_storage[d, t] <= m.h2_storage_capacity_kg,
    )

    def h2_terminal_rule(m, d):
        terminal = _initial_state(
            m, "final_h2_inventory_kg", "h2_storage_capacity_kg", d
        )
        return m.h2_storage[d, m.T.last()] == terminal

    model.h2_storage_terminal_constraint = Constraint(model.D, rule=h2_terminal_rule)
    model.h2_external_supply_limit_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_external_supply[d, t]
        <= m.h2_external_supply_limit_kg_per_hour
        * m.h2_external_available_ratio[d, t],
    )

    fuel_cell_big_m = _upper_bound(model.fuel_cell_power_capacity_kw, 1.0e9)
    model.fuel_cell_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.fuel_cell_power[d, t]
        <= m.fuel_cell_power_capacity_kw * m.fuel_cell_available_ratio[d, t],
    )
    model.fuel_cell_on_capacity_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.fuel_cell_power[d, t]
        <= fuel_cell_big_m * m.is_fuel_cell_on[d, t],
    )
    model.fuel_cell_min_load_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.fuel_cell_power[d, t]
        >= m.fuel_cell_min_load_rate * m.fuel_cell_power_capacity_kw
        - fuel_cell_big_m * (1 - m.is_fuel_cell_on[d, t]),
    )
    model.fuel_cell_power_segment_sum_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.fuel_cell_power[d, t]
        == sum(
            m.fuel_cell_power_segment[d, t, segment]
            for segment in m.FUEL_CELL_SEGMENTS
        ),
    )
    model.fuel_cell_power_segment_limit_constraint = Constraint(
        model.D,
        model.T,
        model.FUEL_CELL_SEGMENTS,
        rule=lambda m, d, t, segment: m.fuel_cell_power_segment[d, t, segment]
        <= m.fuel_cell_segment_power_fraction[segment] * m.fuel_cell_power_capacity_kw,
    )
    fuel_cell_segments = list(model.FUEL_CELL_SEGMENTS)
    fuel_cell_previous = {
        segment: fuel_cell_segments[index - 1]
        for index, segment in enumerate(fuel_cell_segments)
        if index > 0
    }
    if model.performance_curve_mode == "constant_efficiency":
        for variable in model.fuel_cell_segment_active.values():
            variable.fix(0)
    model.fuel_cell_constant_efficiency_distribution_constraint = Constraint(
        model.D,
        model.T,
        model.FUEL_CELL_SEGMENTS,
        rule=lambda m, d, t, segment: (
            m.fuel_cell_power_segment[d, t, segment]
            == m.fuel_cell_segment_power_fraction[segment] * m.fuel_cell_power[d, t]
            if m.performance_curve_mode == "constant_efficiency"
            else Constraint.Skip
        ),
    )
    model.fuel_cell_segment_activation_constraint = Constraint(
        model.D,
        model.T,
        model.FUEL_CELL_ORDERED_SEGMENTS,
        rule=lambda m, d, t, segment: (
            m.fuel_cell_power_segment[d, t, segment]
            <= fuel_cell_big_m * m.fuel_cell_segment_active[d, t, segment]
            if m.performance_curve_mode == "ordered_incremental"
            else Constraint.Skip
        ),
    )
    model.fuel_cell_segment_fill_constraint = Constraint(
        model.D,
        model.T,
        model.FUEL_CELL_ORDERED_SEGMENTS,
        rule=lambda m, d, t, segment: (
            m.fuel_cell_power_segment[d, t, fuel_cell_previous[segment]]
            >= m.fuel_cell_segment_power_fraction[fuel_cell_previous[segment]]
            * m.fuel_cell_power_capacity_kw
            - fuel_cell_big_m * (1 - m.fuel_cell_segment_active[d, t, segment])
            if m.performance_curve_mode == "ordered_incremental"
            else Constraint.Skip
        ),
    )
    model.fuel_cell_conversion_segment_constraint = Constraint(
        model.D,
        model.T,
        model.FUEL_CELL_SEGMENTS,
        rule=lambda m, d, t, segment: m.fuel_cell_power_segment[d, t, segment]
        == m.h2_fuel_cell_segment[d, t, segment]
        * m.fuel_cell_segment_kwh_per_kg[segment],
    )
    model.fuel_cell_conversion_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_fuel_cell[d, t]
        == sum(
            m.h2_fuel_cell_segment[d, t, segment]
            for segment in m.FUEL_CELL_SEGMENTS
        ),
    )

    def fuel_cell_ramp_up_rule(m, d, t):
        if t == m.T.first():
            return Constraint.Skip
        return m.fuel_cell_power[d, t] - m.fuel_cell_power[d, t - 1] <= (
            m.fuel_cell_ramp_rate_per_hour * m.fuel_cell_power_capacity_kw
        )

    def fuel_cell_ramp_down_rule(m, d, t):
        if t == m.T.first():
            return Constraint.Skip
        return m.fuel_cell_power[d, t - 1] - m.fuel_cell_power[d, t] <= (
            m.fuel_cell_ramp_rate_per_hour * m.fuel_cell_power_capacity_kw
        )

    model.fuel_cell_ramp_up_constraint = Constraint(
        model.D, model.T, rule=fuel_cell_ramp_up_rule
    )
    model.fuel_cell_ramp_down_constraint = Constraint(
        model.D, model.T, rule=fuel_cell_ramp_down_rule
    )

    model.hydrogen_balance_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.h2_production[d, t]
        + m.h2_discharge[d, t]
        + m.h2_external_supply[d, t]
        == m.hydrogen_load[d, t] + m.h2_charge[d, t] + m.h2_fuel_cell[d, t],
    )
    model.fuel_cell_backup_capacity_constraint = Constraint(
        rule=lambda m: m.fuel_cell_backup_capacity_kw <= m.fuel_cell_power_capacity_kw
    )
    model.fuel_cell_backup_reserve_limit_constraint = Constraint(
        rule=lambda m: m.fuel_cell_backup_capacity_kw <= m.fuel_cell_backup_reserve_kw
    )
    model.fuel_cell_backup_required_constraint = Constraint(
        rule=lambda m: m.fuel_cell_power_capacity_kw >= m.fuel_cell_backup_required_kw
    )

    model.carbon_emission_constraint = Constraint(
        model.D,
        model.T,
        rule=lambda m, d, t: m.carbon_emission[d, t]
        == m.grid_buy[d, t] * m.grid_emission_factor[d, t]
        + m.gas_consumption[d, t] * m.gas_emission_factor,
    )
    model.annual_carbon_cap_constraint = Constraint(
        rule=lambda m: sum(
            m.weight_days[d] * m.carbon_emission[d, t] for d in m.D for t in m.T
        )
        <= m.annual_carbon_emission_cap_kg
    )
