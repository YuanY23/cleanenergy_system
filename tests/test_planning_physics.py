import math

import pandas as pd
import pytest
from pyomo.environ import value

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.models.performance_curves import conversion_segments
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.typical_days.definitions import TypicalDayConfig


def _frame(values):
    return pd.DataFrame(
        [{"parameter": parameter, "value": parameter_value} for parameter, parameter_value in values.items()]
    )


def _case(**series_overrides):
    series = {
        "pv_cf": [0.0, 0.0],
        "wind_cf": [0.0, 0.0],
        "electric_load_kw": [0.0, 0.0],
        "heat_load_kw": [0.0, 0.0],
        "hydrogen_load_kg": [0.0, 0.0],
        "electricity_price_cny_per_kwh": [1.0, 1.0],
        "gas_price_cny_per_m3": [3.0, 3.0],
        "grid_emission_kgco2_per_kwh": [0.6, 0.6],
        "carbon_price_cny_per_tco2": [0.0, 0.0],
    }
    series.update(series_overrides)
    workbook = InputWorkbook(
        timeseries=pd.DataFrame(series),
        device_params=_frame(
            {
                "heat_pump_COP": 3.0,
                "gas_boiler_heat_kW": 100.0,
                "gas_boiler_eff": 0.9,
                "gas_lhv_kwh_per_m3": 9.8,
                "battery_eta_ch": 0.95,
                "battery_eta_dis": 0.95,
                "electrolyzer_kWh_per_kgH2": 50.0,
                "fuel_cell_kWh_per_kgH2": 20.0,
                "electrolyzer_segment_1_min_rate": 0.0,
                "electrolyzer_segment_1_max_rate": 0.5,
                "electrolyzer_segment_1_kwh_per_kg": 60.0,
                "electrolyzer_segment_2_min_rate": 0.5,
                "electrolyzer_segment_2_max_rate": 1.0,
                "electrolyzer_segment_2_kwh_per_kg": 45.0,
            }
        ),
        economic_params=_frame(
            {
                "gas_emission_factor": 2.0,
                "curtail_penalty": 0.0,
                "battery_om": 0.0,
                "electrolyzer_om": 0.0,
                "fuel_cell_om": 0.0,
                "h2_external_supply_cost": 1.0,
            }
        ),
        scenarios=pd.DataFrame(),
    )
    typical_day = TypicalDayConfig(
        day_id="D", name="test", weight_days=1, pv_scale=1.0, wind_scale=1.0,
        electric_load_scale=1.0, heat_load_scale=1.0, hydrogen_load_scale=1.0,
        electricity_price_scale=1.0, gas_price_scale=1.0,
        grid_emission_scale=1.0, carbon_price_scale=1.0,
    )
    return [(typical_day, workbook)]


def _fixed(**overrides):
    capacities = {
        "wind_capacity_kw": 0.0,
        "pv_capacity_kw": 0.0,
        "battery_power_capacity_kw": 0.0,
        "battery_energy_capacity_kwh": 0.0,
        "electrolyzer_power_capacity_kw": 0.0,
        "h2_storage_capacity_kg": 0.0,
        "fuel_cell_power_capacity_kw": 0.0,
        "heat_pump_power_capacity_kw": 0.0,
    }
    capacities.update(overrides)
    return capacities


def test_fixed_capacity_mode_and_initial_final_state_interface():
    model = build_capacity_planning_model(
        _case(),
        PlanningCostParams(),
        capacity_mode="fixed",
        fixed_capacities=_fixed(
            battery_power_capacity_kw=10.0,
            battery_energy_capacity_kwh=20.0,
            h2_storage_capacity_kg=8.0,
        ),
        initial_battery_soc_kwh=7.0,
        final_battery_soc_kwh=6.0,
        initial_h2_inventory_kg=3.0,
        final_h2_inventory_kg=2.0,
    )

    assert model.battery_energy_capacity_kwh.fixed
    assert value(model.battery_energy_capacity_kwh) == 20.0
    assert value(model.initial_battery_soc_kwh["D"]) == 7.0
    assert value(model.final_h2_inventory_kg["D"]) == 2.0


def test_grid_import_is_explicitly_limited_and_tiered_shedding_balances_load():
    model = build_capacity_planning_model(
        _case(
            electric_load_kw=[10.0, 10.0],
            critical_load_kw=[4.0, 4.0],
            important_load_kw=[3.0, 3.0],
            interruptible_load_kw=[3.0, 3.0],
        ),
        PlanningCostParams(grid_import_limit_kw=5.0),
        capacity_mode="fixed",
        fixed_capacities=_fixed(),
    )
    assert solve_model(model) == "optimal"
    assert max(value(model.grid_buy["D", t]) for t in model.T) <= 5.0 + 1e-6
    assert sum(value(model.load_shed_interruptible["D", t]) for t in model.T) > 0.0
    assert sum(value(model.load_shed_critical["D", t]) for t in model.T) == pytest.approx(0.0)


def test_storage_charge_and_discharge_modes_are_mutually_exclusive():
    model = build_capacity_planning_model(
        _case(),
        PlanningCostParams(),
        capacity_mode="fixed",
        fixed_capacities=_fixed(
            battery_power_capacity_kw=10.0,
            battery_energy_capacity_kwh=20.0,
            h2_storage_capacity_kg=10.0,
        ),
    )
    for t in model.T:
        model.is_battery_charging["D", t].fix(1)
        model.is_h2_charging["D", t].fix(1)
    assert solve_model(model) == "optimal"
    assert all(math.isclose(value(model.battery_discharge["D", t]), 0.0, abs_tol=1e-8) for t in model.T)
    assert all(math.isclose(value(model.h2_discharge["D", t]), 0.0, abs_tol=1e-8) for t in model.T)


def test_islanded_mode_cannot_hide_hydrogen_shortage_with_external_supply():
    model = build_capacity_planning_model(
        _case(hydrogen_load_kg=[2.0, 2.0]),
        PlanningCostParams(),
        capacity_mode="fixed",
        fixed_capacities=_fixed(),
        islanded=True,
    )
    assert solve_model(model) == "infeasible"


def test_fault_availability_derates_renewables_and_conversion_devices():
    model = build_capacity_planning_model(
        _case(
            pv_cf=[1.0, 1.0],
            pv_available_ratio=[0.0, 0.5],
            fuel_cell_available_ratio=[0.0, 0.5],
        ),
        PlanningCostParams(grid_export_limit_kw=100.0),
        capacity_mode="fixed",
        fixed_capacities=_fixed(pv_capacity_kw=10.0, fuel_cell_power_capacity_kw=10.0),
    )
    assert solve_model(model) == "optimal"
    assert value(model.pv_used["D", 0]) + value(model.pv_sold["D", 0]) == pytest.approx(0.0)
    assert value(model.pv_used["D", 1]) + value(model.pv_sold["D", 1]) <= 5.0 + 1e-6
    assert value(model.fuel_cell_power["D", 0]) == pytest.approx(0.0)


def test_piecewise_conversion_segments_must_be_contiguous_and_ordered():
    with pytest.raises(ValueError, match="contiguous"):
        conversion_segments(
            {
                "unit_segment_1_min_rate": 0.0,
                "unit_segment_1_max_rate": 0.4,
                "unit_segment_2_min_rate": 0.5,
                "unit_segment_2_max_rate": 1.0,
            },
            prefix="unit",
            fallback_kwh_per_kg=50.0,
        )

    model = build_capacity_planning_model(
        _case(hydrogen_load_kg=[0.1, 0.1]),
        PlanningCostParams(),
        capacity_mode="fixed",
        fixed_capacities=_fixed(electrolyzer_power_capacity_kw=10.0),
        allow_external_h2=False,
        performance_curve_mode="ordered_incremental",
    )
    assert solve_model(model) == "optimal"
    # Segment 2 is more efficient, but it cannot be used until segment 1 is full.
    assert value(model.electrolyzer_power_segment["D", 0, 1]) == pytest.approx(5.0)
    assert value(model.electrolyzer_power_segment["D", 0, 2]) > 0.0


def test_solver_attaches_reproducible_metadata():
    model = build_capacity_planning_model(
        _case(), PlanningCostParams(), capacity_mode="fixed", fixed_capacities=_fixed()
    )
    status = solve_model(model, time_limit_seconds=10.0, mip_gap=0.01)
    assert status == "optimal"
    assert model.solve_metadata["time_limit_seconds"] == 10.0
    assert model.solve_metadata["requested_mip_gap"] == 0.01
    assert model.solve_metadata["termination_condition"] == "optimal"
    assert model.solve_metadata["solver_status"]
