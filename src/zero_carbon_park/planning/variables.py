"""容量规划变量定义。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, NonNegativeReals, Var


def add_capacity_variables(model: ConcreteModel) -> None:
    """添加设备容量规划变量。"""

    model.wind_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 30000))
    model.pv_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 30000))
    model.battery_power_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 15000))
    model.battery_energy_capacity_kwh = Var(domain=NonNegativeReals, bounds=(0, 60000))
    model.electrolyzer_power_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 10000))
    model.h2_storage_capacity_kg = Var(domain=NonNegativeReals, bounds=(0, 5000))
    model.fuel_cell_power_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 5000))
    model.heat_pump_power_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 10000))


def add_operation_variables(model: ConcreteModel) -> None:
    """添加多典型日逐小时运行变量。"""

    model.grid_buy = Var(model.D, model.T, domain=NonNegativeReals)
    model.pv_used = Var(model.D, model.T, domain=NonNegativeReals)
    model.pv_curtail = Var(model.D, model.T, domain=NonNegativeReals)
    model.wind_used = Var(model.D, model.T, domain=NonNegativeReals)
    model.wind_curtail = Var(model.D, model.T, domain=NonNegativeReals)

    model.heat_pump_power = Var(model.D, model.T, domain=NonNegativeReals)
    model.heat_pump_heat = Var(model.D, model.T, domain=NonNegativeReals)
    model.gas_boiler_heat = Var(model.D, model.T, domain=NonNegativeReals)
    model.gas_consumption = Var(model.D, model.T, domain=NonNegativeReals)

    model.battery_charge = Var(model.D, model.T, domain=NonNegativeReals)
    model.battery_discharge = Var(model.D, model.T, domain=NonNegativeReals)
    model.battery_soc = Var(model.D, model.T, domain=NonNegativeReals)

    model.electrolyzer_power = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_production = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_charge = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_discharge = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_storage = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_external_supply = Var(model.D, model.T, domain=NonNegativeReals)
    model.h2_fuel_cell = Var(model.D, model.T, domain=NonNegativeReals)
    model.fuel_cell_power = Var(model.D, model.T, domain=NonNegativeReals)

    model.carbon_emission = Var(model.D, model.T, domain=NonNegativeReals)

