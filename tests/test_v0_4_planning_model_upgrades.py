import math

import pandas as pd
from pyomo.environ import value

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.planning.results import extract_capacity_planning_results
from zero_carbon_park.typical_days.definitions import TypicalDayConfig


def _typical_day(weight_days: int = 1) -> TypicalDayConfig:
    return TypicalDayConfig(
        day_id="TD_TEST",
        name="test",
        weight_days=weight_days,
        pv_scale=1.0,
        wind_scale=1.0,
        electric_load_scale=1.0,
        heat_load_scale=1.0,
        hydrogen_load_scale=1.0,
        electricity_price_scale=1.0,
        gas_price_scale=1.0,
        grid_emission_scale=1.0,
        carbon_price_scale=1.0,
    )


def _params_frame(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"parameter": parameter, "value": value} for parameter, value in values.items()]
    )


def _workbook(timeseries: pd.DataFrame) -> InputWorkbook:
    return InputWorkbook(
        timeseries=timeseries,
        device_params=_params_frame(
            {
                "heat_pump_COP": 3.0,
                "gas_boiler_heat_kW": 1000.0,
                "gas_boiler_eff": 0.9,
                "gas_lhv_kwh_per_m3": 9.8,
                "battery_eta_ch": 1.0,
                "battery_eta_dis": 1.0,
                "electrolyzer_kWh_per_kgH2": 50.0,
                "fuel_cell_kWh_per_kgH2": 20.0,
            }
        ),
        economic_params=_params_frame(
            {
                "gas_emission_factor": 2.0,
                "curtail_penalty": 0.0,
                "battery_om": 0.0,
                "electrolyzer_om": 0.0,
                "fuel_cell_om": 0.0,
                "h2_external_supply_cost": 1000.0,
            }
        ),
        scenarios=pd.DataFrame(),
    )


def _base_timeseries(**overrides) -> pd.DataFrame:
    data = {
        "pv_cf": [0.0, 0.0],
        "wind_cf": [0.0, 0.0],
        "electric_load_kw": [0.0, 0.0],
        "heat_load_kw": [0.0, 0.0],
        "hydrogen_load_kg": [0.0, 0.0],
        "electricity_price_cny_per_kwh": [0.5, 0.5],
        "gas_price_cny_per_m3": [3.0, 3.0],
        "grid_emission_kgco2_per_kwh": [0.6, 0.6],
        "carbon_price_cny_per_tco2": [0.0, 0.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _zero_capex_params(**overrides) -> PlanningCostParams:
    values = {
        "discount_rate": 0.0,
        "wind_capex_cny_per_kw": 0.0,
        "pv_capex_cny_per_kw": 0.0,
        "battery_power_capex_cny_per_kw": 0.0,
        "battery_energy_capex_cny_per_kwh": 0.0,
        "electrolyzer_capex_cny_per_kw": 0.0,
        "h2_storage_capex_cny_per_kg": 0.0,
        "fuel_cell_capex_cny_per_kw": 0.0,
        "heat_pump_capex_cny_per_kw": 0.0,
    }
    values.update(overrides)
    return PlanningCostParams(**values)


def test_planning_model_accepts_time_varying_efficiency_and_market_params():
    workbook = _workbook(
        _base_timeseries(
            heat_pump_cop=[2.0, 4.0],
            electrolyzer_kwh_per_kg=[55.0, 45.0],
            fuel_cell_kwh_per_kg=[18.0, 22.0],
            grid_sell_price_cny_per_kwh=[0.1, 0.2],
        )
    )

    model = build_capacity_planning_model(
        typical_days=[(_typical_day(), workbook)],
        cost_params=PlanningCostParams(
            battery_degradation_cost_cny_per_kwh=0.03,
            grid_export_limit_kw=7.0,
            demand_charge_cny_per_kw_year=12.0,
        ),
    )

    assert value(model.heat_pump_cop["TD_TEST", 0]) == 2.0
    assert value(model.heat_pump_cop["TD_TEST", 1]) == 4.0
    assert value(model.electrolyzer_kwh_per_kg["TD_TEST", 0]) == 55.0
    assert value(model.fuel_cell_kwh_per_kg["TD_TEST", 1]) == 22.0
    assert value(model.grid_sell_price["TD_TEST", 1]) == 0.2
    assert value(model.grid_export_limit_kw) == 7.0
    assert value(model.demand_charge_cny_per_kw_year) == 12.0
    assert value(model.battery_degradation_cost_cny_per_kwh) == 0.03


def test_renewable_export_market_creates_sold_power_and_revenue():
    workbook = _workbook(
        _base_timeseries(
            pv_cf=[1.0, 1.0],
            grid_sell_price_cny_per_kwh=[1.0, 1.0],
        )
    )

    model = build_capacity_planning_model(
        typical_days=[(_typical_day(), workbook)],
        cost_params=_zero_capex_params(grid_export_limit_kw=5.0),
    )
    status = solve_model(model)
    results = extract_capacity_planning_results(model, status)
    summary = results["summary"].iloc[0]
    hourly = results["hourly"]

    assert status == "optimal"
    assert math.isclose(hourly["grid_sell_kw"].sum(), 10.0, abs_tol=1e-5)
    assert math.isclose(summary["annual_grid_sell_revenue_cny"], 10.0, abs_tol=1e-5)
    assert summary["annual_operation_cost_cny"] < 0.0


def test_fuel_cell_backup_value_selects_capacity_up_to_reserve_need():
    workbook = _workbook(_base_timeseries())

    model = build_capacity_planning_model(
        typical_days=[(_typical_day(), workbook)],
        cost_params=PlanningCostParams(
            discount_rate=0.0,
            fuel_cell_capex_cny_per_kw=100.0,
            fuel_cell_life_years=10,
            fuel_cell_backup_value_cny_per_kw_year=50.0,
            fuel_cell_backup_reserve_kw=3.0,
        ),
    )
    status = solve_model(model)
    results = extract_capacity_planning_results(model, status)
    summary = results["summary"].iloc[0]

    assert status == "optimal"
    assert math.isclose(value(model.fuel_cell_backup_capacity_kw), 3.0, abs_tol=1e-5)
    assert math.isclose(value(model.fuel_cell_power_capacity_kw), 3.0, abs_tol=1e-5)
    assert math.isclose(summary["annual_fuel_cell_backup_value_cny"], 150.0, abs_tol=1e-5)


def test_demand_charge_adds_grid_import_peak_and_encourages_peak_shaving():
    timeseries = _base_timeseries(
        electric_load_kw=[10.0, 0.0],
        electricity_price_cny_per_kwh=[0.5, 0.5],
    )
    workbook = _workbook(timeseries)
    workbook.economic_params.loc[
        workbook.economic_params["parameter"] == "h2_external_supply_cost",
        "value",
    ] = 1.0e7

    model = build_capacity_planning_model(
        typical_days=[(_typical_day(), workbook)],
        cost_params=_zero_capex_params(
            demand_charge_cny_per_kw_year=100.0,
            fuel_cell_capex_cny_per_kw=1.0e7,
            h2_storage_capex_cny_per_kg=1.0e7,
        ),
    )
    status = solve_model(model)

    assert status == "optimal"
    assert value(model.grid_import_peak_kw) < 10.0
    assert math.isclose(value(model.grid_import_peak_kw), 5.0, abs_tol=1e-5)
