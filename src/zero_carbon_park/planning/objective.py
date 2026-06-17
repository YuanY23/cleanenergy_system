"""容量规划目标函数。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Expression, Objective, minimize


def add_capacity_planning_objective(model: ConcreteModel) -> None:
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
                + m.h2_production[d, t] * m.electrolyzer_om
                + m.h2_external_supply[d, t] * m.h2_external_supply_cost
                + m.fuel_cell_power[d, t] * m.fuel_cell_om
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
    model.annual_total_cost = Objective(
        expr=model.annual_operation_cost + model.annualized_investment_cost,
        sense=minimize,
    )

