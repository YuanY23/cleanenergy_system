import pandas as pd
from pyomo.environ import value

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.optimization.builder import build_minimal_milp_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.scenarios.definitions import get_minimal_scenario_config
from zero_carbon_park.typical_days.definitions import TypicalDayConfig


def _params_frame(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"parameter": parameter, "value": value} for parameter, value in values.items()]
    )


def _base_timeseries(**overrides) -> pd.DataFrame:
    data = {
        "electric_load_kw": [10.0, 10.0],
        "heat_load_kw": [5.0, 5.0],
        "hydrogen_load_kg": [0.0, 0.0],
        "pv_available_kw": [0.0, 0.0],
        "wind_available_kw": [0.0, 0.0],
        "pv_cf": [0.0, 0.0],
        "wind_cf": [0.0, 0.0],
        "electricity_price_cny_per_kwh": [0.5, 0.5],
        "gas_price_cny_per_m3": [3.0, 3.0],
        "grid_emission_kgco2_per_kwh": [0.6, 0.6],
        "carbon_price_cny_per_tco2": [0.0, 0.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _device_params() -> pd.DataFrame:
    return _params_frame(
        {
            "heat_pump_power_kW": 100.0,
            "heat_pump_COP": 3.0,
            "gas_boiler_heat_kW": 100.0,
            "gas_boiler_eff": 0.9,
            "gas_lhv_kwh_per_m3": 9.8,
            "battery_power_kW": 100.0,
            "battery_energy_kWh": 200.0,
            "battery_eta_ch": 0.95,
            "battery_eta_dis": 0.95,
            "battery_initial_soc": 100.0,
            "electrolyzer_power_kW": 80.0,
            "electrolyzer_kWh_per_kgH2": 55.0,
            "electrolyzer_min_load_rate": 0.2,
            "electrolyzer_segment_1_min_rate": 0.0,
            "electrolyzer_segment_1_max_rate": 0.4,
            "electrolyzer_segment_1_kwh_per_kg": 58.0,
            "electrolyzer_segment_2_min_rate": 0.4,
            "electrolyzer_segment_2_max_rate": 1.0,
            "electrolyzer_segment_2_kwh_per_kg": 52.0,
            "h2_storage_capacity_kg": 100.0,
            "h2_storage_initial_kg": 30.0,
            "h2_storage_loss_rate_per_hour": 0.001,
            "fuel_cell_power_kW": 60.0,
            "fuel_cell_kWh_per_kgH2": 18.0,
            "fuel_cell_min_load_rate": 0.15,
            "fuel_cell_segment_1_min_rate": 0.0,
            "fuel_cell_segment_1_max_rate": 0.5,
            "fuel_cell_segment_1_kwh_per_kg": 17.0,
            "fuel_cell_segment_2_min_rate": 0.5,
            "fuel_cell_segment_2_max_rate": 1.0,
            "fuel_cell_segment_2_kwh_per_kg": 19.0,
        }
    )


def _economic_params() -> pd.DataFrame:
    return _params_frame(
        {
            "gas_emission_factor": 2.0,
            "curtail_penalty": 0.0,
            "battery_om": 0.0,
            "battery_degradation_segment_1_width_rate": 0.5,
            "battery_degradation_segment_1_cost_cny_per_kwh": 0.05,
            "battery_degradation_segment_2_width_rate": 0.5,
            "battery_degradation_segment_2_cost_cny_per_kwh": 0.15,
            "electrolyzer_om": 0.0,
            "fuel_cell_om": 0.0,
            "h2_external_supply_cost": 1000.0,
        }
    )


def test_operational_model_registers_hourly_and_piecewise_device_performance():
    model = build_minimal_milp_model(
        timeseries=_base_timeseries(
            heat_pump_cop=[2.4, 3.6],
            heat_pump_available_ratio=[0.8, 1.0],
        ),
        device_params=_device_params(),
        economic_params=_economic_params(),
        scenario=get_minimal_scenario_config("S4"),
    )

    assert value(model.heat_pump_cop[0]) == 2.4
    assert value(model.heat_pump_available_ratio[0]) == 0.8
    assert list(model.ELECTROLYZER_SEGMENTS) == [1, 2]
    assert value(model.electrolyzer_segment_power_fraction[2]) == 0.6
    assert value(model.electrolyzer_segment_kwh_per_kg[1]) == 58.0
    assert list(model.FUEL_CELL_SEGMENTS) == [1, 2]
    assert value(model.fuel_cell_segment_power_fraction[1]) == 0.5
    assert value(model.fuel_cell_segment_kwh_per_kg[2]) == 19.0
    assert list(model.BATTERY_DEGRADATION_SEGMENTS) == [1, 2]
    assert value(model.battery_degradation_segment_cost[2]) == 0.15
    assert value(model.electrolyzer_min_load_rate) == 0.2
    assert value(model.fuel_cell_min_load_rate) == 0.15
    assert value(model.h2_storage_loss_rate_per_hour) == 0.001
    assert (0, 1) in model.electrolyzer_power_segment
    assert (0, 2) in model.fuel_cell_power_segment
    assert (1, 2) in model.battery_degradation_throughput_segment


def test_planning_model_registers_piecewise_performance_and_on_off_limits():
    workbook = InputWorkbook(
        timeseries=_base_timeseries(
            heat_pump_cop=[2.4, 3.6],
            heat_pump_available_ratio=[0.8, 1.0],
        ),
        device_params=_device_params(),
        economic_params=_economic_params(),
        scenarios=pd.DataFrame(),
    )
    typical_day = TypicalDayConfig(
        day_id="TD",
        name="test",
        weight_days=1,
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

    model = build_capacity_planning_model(
        typical_days=[(typical_day, workbook)],
        cost_params=PlanningCostParams(battery_degradation_cost_cny_per_kwh=0.03),
    )

    assert value(model.heat_pump_available_ratio["TD", 0]) == 0.8
    assert list(model.ELECTROLYZER_SEGMENTS) == [1, 2]
    assert list(model.FUEL_CELL_SEGMENTS) == [1, 2]
    assert list(model.BATTERY_DEGRADATION_SEGMENTS) == [1, 2]
    assert value(model.electrolyzer_min_load_rate) == 0.2
    assert value(model.fuel_cell_min_load_rate) == 0.15
    assert ("TD", 0) in model.is_electrolyzer_on
    assert ("TD", 1) in model.is_fuel_cell_on
    assert ("TD", 0, 2) in model.electrolyzer_power_segment
    assert ("TD", 1, 1) in model.fuel_cell_power_segment
    assert ("TD", 0, 2) in model.battery_degradation_throughput_segment
