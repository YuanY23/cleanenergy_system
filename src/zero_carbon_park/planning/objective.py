"""容量规划目标函数。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Constraint, Expression, Objective, minimize


def add_capacity_planning_objective(
    model: ConcreteModel,
    *,
    objective_mode: str = "economic",
    annual_total_cost_cap_cny: float | None = None,
) -> None:
    """添加年度运行成本和年化投资成本目标函数。"""

    def annual_operation_cost_rule(m):
        return sum(
            m.weight_days[d]
            * sum(
                m.grid_buy[d, t] * m.grid_price[d, t]
                + m.gas_consumption[d, t] * m.gas_price[d, t]
                + (m.pv_curtail[d, t] + m.wind_curtail[d, t]) * m.curtail_penalty
                + m.carbon_emission[d, t] * m.carbon_price[d, t]
                + (m.battery_charge[d, t] + m.battery_discharge[d, t]) * m.battery_om
                + sum(
                    m.battery_degradation_throughput_segment[d, t, segment]
                    * m.battery_degradation_segment_cost[segment]
                    for segment in m.BATTERY_DEGRADATION_SEGMENTS
                )
                + m.h2_production[d, t] * m.electrolyzer_om
                + m.h2_external_supply[d, t] * m.h2_external_supply_cost
                + m.fuel_cell_power[d, t] * m.fuel_cell_om
                + m.load_shed_critical[d, t] * m.critical_load_shed_penalty
                + m.load_shed_important[d, t] * m.important_load_shed_penalty
                + m.load_shed_interruptible[d, t]
                * m.interruptible_load_shed_penalty
                - m.grid_sell[d, t] * m.grid_sell_price[d, t]
                for t in m.T
            )
            for d in m.D
        )

    model.annual_operation_cost = Expression(rule=annual_operation_cost_rule)

    def annualized_investment_cost_rule(m):
        return (
            m.wind_capacity_kw * m.wind_capex_annual_cny_per_kw
            + m.pv_capacity_kw * m.pv_capex_annual_cny_per_kw
            + m.battery_power_capacity_kw * m.battery_power_capex_annual_cny_per_kw
            + m.battery_energy_capacity_kwh * m.battery_energy_capex_annual_cny_per_kwh
            + m.electrolyzer_power_capacity_kw * m.electrolyzer_capex_annual_cny_per_kw
            + m.h2_storage_capacity_kg * m.h2_storage_capex_annual_cny_per_kg
            + m.fuel_cell_power_capacity_kw * m.fuel_cell_capex_annual_cny_per_kw
            + m.heat_pump_power_capacity_kw * m.heat_pump_capex_annual_cny_per_kw
        )

    model.annualized_investment_cost = Expression(
        rule=annualized_investment_cost_rule
    )

    model.annual_demand_charge_cost = Expression(
        expr=model.grid_import_peak_kw * model.demand_charge_cny_per_kw_year
    )
    model.annual_fuel_cell_backup_value = Expression(
        expr=model.fuel_cell_backup_capacity_kw
        * model.fuel_cell_backup_value_cny_per_kw_year
    )
    model.annual_total_cost_expression = Expression(
        expr=model.annual_operation_cost
        + model.annualized_investment_cost
        + model.annual_demand_charge_cost
        - model.annual_fuel_cell_backup_value
    )
    model.annual_operating_carbon_emission = Expression(
        expr=sum(
            model.weight_days[d] * model.carbon_emission[d, t]
            for d in model.D
            for t in model.T
        )
    )
    model.annual_total_cost_cap_constraint = Constraint(
        expr=(
            model.annual_total_cost_expression <= float(annual_total_cost_cap_cny)
            if annual_total_cost_cap_cny is not None
            else Constraint.Feasible
        )
    )
    if objective_mode == "economic":
        objective_expression = model.annual_total_cost_expression
    elif objective_mode == "carbon":
        # Exports never appear in the carbon expression, so exported renewable
        # energy cannot offset grid-import or fuel combustion emissions.
        objective_expression = model.annual_operating_carbon_emission
    else:
        raise ValueError("objective_mode must be economic or carbon")
    model.annual_total_cost = Objective(expr=objective_expression, sense=minimize)
