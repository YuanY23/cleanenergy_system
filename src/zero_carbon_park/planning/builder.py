"""容量规划模型组装。"""

from __future__ import annotations

from pyomo.environ import ConcreteModel, Param, RangeSet, Set

from zero_carbon_park.models.parameters import parameter_frame_to_dict
from zero_carbon_park.planning.constraints import add_planning_constraints
from zero_carbon_park.planning.cost_params import (
    PlanningCostParams,
    capital_recovery_factor,
)
from zero_carbon_park.planning.objective import add_capacity_planning_objective
from zero_carbon_park.planning.variables import (
    add_capacity_variables,
    add_operation_variables,
)


def build_capacity_planning_model(
    typical_days,
    cost_params: PlanningCostParams,
    annual_carbon_emission_cap_kg: float | None = None,
) -> ConcreteModel:
    """构建多典型日容量规划优化模型。"""

    if not typical_days:
        raise ValueError("容量规划至少需要一个典型日")

    first_workbook = typical_days[0][1]
    device = parameter_frame_to_dict(first_workbook.device_params)
    economic = parameter_frame_to_dict(first_workbook.economic_params)
    day_ids = [config.day_id for config, _ in typical_days]
    last_hour = len(first_workbook.timeseries) - 1

    model = ConcreteModel(name="capacity_planning")
    model.D = Set(initialize=day_ids, ordered=True)
    model.T = RangeSet(0, last_hour)

    _add_timeseries_params(model, typical_days, device, economic)
    _add_device_params(model, device)
    _add_economic_params(model, economic)
    _add_investment_params(model, cost_params)
    model.annual_carbon_emission_cap_kg = Param(
        initialize=(
            float(annual_carbon_emission_cap_kg)
            if annual_carbon_emission_cap_kg is not None
            else 1.0e15
        )
    )

    add_capacity_variables(model)
    add_operation_variables(model)
    add_planning_constraints(model)
    add_capacity_planning_objective(model)

    return model


def _add_timeseries_params(
    model: ConcreteModel,
    typical_days,
    device: dict[str, float],
    economic: dict[str, float],
) -> None:
    """写入多典型日时间序列参数。"""

    by_day = {config.day_id: (config, workbook.timeseries.reset_index(drop=True)) for config, workbook in typical_days}

    model.weight_days = Param(model.D, initialize={d: by_day[d][0].weight_days for d in model.D})
    for column, param_name in [
        ("pv_cf", "pv_cf"),
        ("wind_cf", "wind_cf"),
        ("electric_load_kw", "electric_load"),
        ("heat_load_kw", "heat_load"),
        ("hydrogen_load_kg", "hydrogen_load"),
        ("electricity_price_cny_per_kwh", "grid_price"),
        ("gas_price_cny_per_m3", "gas_price"),
        ("grid_emission_kgco2_per_kwh", "grid_emission_factor"),
    ]:
        setattr(
            model,
            param_name,
            Param(
                model.D,
                model.T,
                initialize={(d, t): float(by_day[d][1].loc[t, column]) for d in model.D for t in model.T},
            ),
        )

    model.carbon_price = Param(
        model.D,
        model.T,
        initialize={
            (d, t): float(by_day[d][1].loc[t, "carbon_price_cny_per_tco2"]) / 1000.0
            for d in model.D
            for t in model.T
        },
    )

    for column, param_name, default in [
        ("heat_pump_cop", "heat_pump_cop", device["heat_pump_COP"]),
        (
            "electrolyzer_kwh_per_kg",
            "electrolyzer_kwh_per_kg",
            device["electrolyzer_kWh_per_kgH2"],
        ),
        (
            "fuel_cell_kwh_per_kg",
            "fuel_cell_kwh_per_kg",
            device["fuel_cell_KWh_per_kgH2"]
            if "fuel_cell_KWh_per_kgH2" in device
            else device["fuel_cell_kWh_per_kgH2"],
        ),
        (
            "grid_sell_price_cny_per_kwh",
            "grid_sell_price",
            economic.get("grid_sell_price_cny_per_kwh", 0.0),
        ),
    ]:
        setattr(
            model,
            param_name,
            Param(
                model.D,
                model.T,
                initialize={
                    (d, t): _timeseries_value(by_day[d][1], t, column, default)
                    for d in model.D
                    for t in model.T
                },
            ),
        )


def _add_device_params(model: ConcreteModel, device: dict[str, float]) -> None:
    """写入设备效率和固定容量参数。"""

    model.gas_boiler_heat_max = Param(initialize=float(device["gas_boiler_heat_kW"]))
    model.gas_boiler_eff = Param(initialize=float(device["gas_boiler_eff"]))
    model.gas_lhv = Param(initialize=float(device["gas_lhv_kwh_per_m3"]))
    model.battery_eta_ch = Param(initialize=float(device["battery_eta_ch"]))
    model.battery_eta_dis = Param(initialize=float(device["battery_eta_dis"]))


def _add_economic_params(model: ConcreteModel, economic: dict[str, float]) -> None:
    """写入运行经济参数。"""

    model.gas_emission_factor = Param(initialize=float(economic["gas_emission_factor"]))
    model.curtail_penalty = Param(initialize=float(economic["curtail_penalty"]))
    model.battery_om = Param(initialize=float(economic["battery_om"]))
    model.electrolyzer_om = Param(initialize=float(economic["electrolyzer_om"]))
    model.fuel_cell_om = Param(initialize=float(economic["fuel_cell_om"]))
    model.h2_external_supply_cost = Param(
        initialize=float(economic.get("h2_external_supply_cost", 1000.0))
    )


def _add_investment_params(
    model: ConcreteModel,
    cost_params: PlanningCostParams,
) -> None:
    """写入年化投资成本参数。"""

    rate = cost_params.discount_rate
    model.wind_capex_annual_cny_per_kw = Param(
        initialize=cost_params.wind_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.wind_life_years)
    )
    model.pv_capex_annual_cny_per_kw = Param(
        initialize=cost_params.pv_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.pv_life_years)
    )
    battery_crf = capital_recovery_factor(rate, cost_params.battery_life_years)
    model.battery_power_capex_annual_cny_per_kw = Param(
        initialize=cost_params.battery_power_capex_cny_per_kw * battery_crf
    )
    model.battery_energy_capex_annual_cny_per_kwh = Param(
        initialize=cost_params.battery_energy_capex_cny_per_kwh * battery_crf
    )
    model.electrolyzer_capex_annual_cny_per_kw = Param(
        initialize=cost_params.electrolyzer_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.electrolyzer_life_years)
    )
    model.h2_storage_capex_annual_cny_per_kg = Param(
        initialize=cost_params.h2_storage_capex_cny_per_kg
        * capital_recovery_factor(rate, cost_params.h2_storage_life_years)
    )
    model.fuel_cell_capex_annual_cny_per_kw = Param(
        initialize=cost_params.fuel_cell_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.fuel_cell_life_years)
    )
    model.heat_pump_capex_annual_cny_per_kw = Param(
        initialize=cost_params.heat_pump_capex_cny_per_kw
        * capital_recovery_factor(rate, cost_params.heat_pump_life_years)
    )
    model.battery_degradation_cost_cny_per_kwh = Param(
        initialize=cost_params.battery_degradation_cost_cny_per_kwh
    )
    model.fuel_cell_backup_value_cny_per_kw_year = Param(
        initialize=cost_params.fuel_cell_backup_value_cny_per_kw_year
    )
    model.fuel_cell_backup_reserve_kw = Param(
        initialize=cost_params.fuel_cell_backup_reserve_kw
    )
    model.fuel_cell_backup_required_kw = Param(
        initialize=cost_params.fuel_cell_backup_required_kw
    )
    model.grid_export_limit_kw = Param(initialize=cost_params.grid_export_limit_kw)
    model.demand_charge_cny_per_kw_year = Param(
        initialize=cost_params.demand_charge_cny_per_kw_year
    )


def _timeseries_value(frame, row_index: int, column: str, default: float) -> float:
    if column in frame.columns:
        return float(frame.loc[row_index, column])
    return float(default)
