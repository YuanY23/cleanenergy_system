from __future__ import annotations

import pandas as pd
import pytest

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.reliability.definitions import (
    ReliabilityEvent,
    select_stress_start_times,
)
from zero_carbon_park.reliability.runner import (
    run_reliability_catalog,
    run_reliability_event,
)


def _params(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"parameter": name, "value": value} for name, value in values.items()]
    )


def _workbook(hours: int = 24) -> InputWorkbook:
    timestamp = pd.date_range(
        "2024-01-01", periods=hours, freq="h", tz="Asia/Shanghai"
    )
    return InputWorkbook(
        timeseries=pd.DataFrame(
            {
                "timestamp_local": timestamp,
                "pv_cf": 0.0,
                "wind_cf": 0.0,
                "electric_load_kw": 4.0,
                "critical_load_kw": 2.0,
                "important_load_kw": 1.0,
                "interruptible_load_kw": 1.0,
                "heat_load_kw": 0.0,
                "hydrogen_load_kg": 0.0,
                "electricity_price_cny_per_kwh": 1.0,
                "gas_price_cny_per_m3": 3.0,
                "grid_emission_kgco2_per_kwh": 0.6,
                "carbon_price_cny_per_tco2": 0.0,
            }
        ),
        device_params=_params(
            {
                "heat_pump_COP": 3.0,
                "gas_boiler_heat_kW": 10.0,
                "gas_boiler_eff": 0.9,
                "gas_lhv_kwh_per_m3": 9.8,
                "battery_eta_ch": 1.0,
                "battery_eta_dis": 1.0,
                "electrolyzer_kWh_per_kgH2": 50.0,
                "fuel_cell_kWh_per_kgH2": 20.0,
            }
        ),
        economic_params=_params(
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


def _fixed() -> dict[str, float]:
    return {
        "wind_capacity_kw": 0.0,
        "pv_capacity_kw": 0.0,
        "battery_power_capacity_kw": 2.0,
        "battery_energy_capacity_kwh": 4.0,
        "electrolyzer_power_capacity_kw": 0.0,
        "h2_storage_capacity_kg": 0.0,
        "fuel_cell_power_capacity_kw": 0.0,
        "heat_pump_power_capacity_kw": 0.0,
    }


def _replay_state() -> pd.DataFrame:
    timestamp = pd.date_range(
        "2023-12-31 23:00", periods=25, freq="h", tz="Asia/Shanghai"
    )
    return pd.DataFrame(
        {
            "timestamp_local": timestamp,
            "battery_soc_kwh": [4.0] * 25,
            "h2_storage_kg": [0.0] * 25,
        }
    )


def test_island_event_inherits_pre_event_state_and_forbids_external_supply() -> None:
    event = ReliabilityEvent(
        event_id="OUTAGE_4H",
        start_timestamp=pd.Timestamp("2024-01-01 00:00", tz="Asia/Shanghai"),
        duration_hours=4,
    )
    result = run_reliability_event(
        _workbook(),
        replay_hourly=_replay_state(),
        fixed_capacities=_fixed(),
        cost_params=PlanningCostParams(grid_import_limit_kw=100.0),
        event=event,
    )

    assert result.summary["initial_battery_soc_kwh"] == pytest.approx(4.0)
    assert result.hourly["grid_buy_kw"].sum() == pytest.approx(0.0)
    assert result.hourly["grid_sell_kw"].sum() == pytest.approx(0.0)
    assert result.hourly["h2_external_supply_kg"].sum() == pytest.approx(0.0)
    assert result.summary["island_survival_hours"] == 2
    assert result.summary["ens_critical_kwh"] == pytest.approx(4.0)


def test_device_fault_derates_the_named_device_for_the_event() -> None:
    event = ReliabilityEvent(
        event_id="BATTERY_FAULT",
        start_timestamp=pd.Timestamp("2024-01-01 00:00", tz="Asia/Shanghai"),
        duration_hours=2,
        failed_devices=("battery",),
    )
    result = run_reliability_event(
        _workbook(),
        replay_hourly=_replay_state(),
        fixed_capacities=_fixed(),
        cost_params=PlanningCostParams(grid_import_limit_kw=100.0),
        event=event,
    )
    assert result.hourly["battery_discharge_kw"].sum() == pytest.approx(0.0)
    assert result.summary["ens_critical_kwh"] == pytest.approx(4.0)


def test_short_island_event_does_not_force_storage_to_an_artificial_terminal_state() -> None:
    workbook = _workbook()
    workbook.timeseries.loc[:, [
        "electric_load_kw",
        "critical_load_kw",
        "important_load_kw",
        "interruptible_load_kw",
    ]] = 0.0
    workbook.timeseries["hydrogen_load_kg"] = 1.0
    fixed = _fixed()
    fixed["h2_storage_capacity_kg"] = 4.0
    replay = _replay_state()
    replay["h2_storage_kg"] = 4.0
    event = ReliabilityEvent(
        event_id="OUTAGE_WITH_SURPLUS_H2_2H",
        start_timestamp=pd.Timestamp("2024-01-01 00:00", tz="Asia/Shanghai"),
        duration_hours=2,
    )

    result = run_reliability_event(
        workbook,
        replay_hourly=replay,
        fixed_capacities=fixed,
        cost_params=PlanningCostParams(grid_import_limit_kw=100.0),
        event=event,
    )

    assert result.hourly["h2_external_supply_kg"].sum() == pytest.approx(0.0)
    assert result.hourly["h2_storage_kg"].iloc[-1] == pytest.approx(2.0)


def test_island_event_reports_unserved_hydrogen_instead_of_becoming_infeasible() -> None:
    workbook = _workbook()
    workbook.timeseries.loc[:, [
        "electric_load_kw",
        "critical_load_kw",
        "important_load_kw",
        "interruptible_load_kw",
    ]] = 0.0
    workbook.timeseries["hydrogen_load_kg"] = 1.0
    replay = _replay_state()
    replay["h2_storage_kg"] = 0.0
    event = ReliabilityEvent(
        event_id="OUTAGE_WITH_H2_SHORTAGE_2H",
        start_timestamp=pd.Timestamp("2024-01-01 00:00", tz="Asia/Shanghai"),
        duration_hours=2,
    )

    result = run_reliability_event(
        workbook,
        replay_hourly=replay,
        fixed_capacities=_fixed(),
        cost_params=PlanningCostParams(grid_import_limit_kw=100.0),
        event=event,
    )

    assert result.hourly["h2_unserved_kg"].sum() == pytest.approx(2.0)
    assert result.summary["unserved_hydrogen_kg"] == pytest.approx(2.0)
    assert result.summary["critical_load_supply_ratio"] == pytest.approx(1.0)


def test_stress_selector_keeps_pre_state_and_complete_24h_horizon() -> None:
    timestamps = pd.date_range(
        "2024-01-01", periods=72, freq="h", tz="Asia/Shanghai"
    )
    annual = pd.DataFrame(
        {
            "timestamp_local": timestamps,
            "electric_load_kw": [1000.0] + [1.0] * 70 + [2000.0],
            "pv_cf": [0.0] * 72,
            "wind_cf": [0.0] * 72,
        }
    )
    replay = pd.DataFrame(
        {
            "timestamp_local": timestamps,
            "battery_soc_kwh": [0.0] + [10.0] * 71,
            "h2_storage_kg": [0.0] + [10.0] * 71,
        }
    )

    starts = select_stress_start_times(annual, replay)

    assert (starts["start_timestamp"] > timestamps[0]).all()
    assert (starts["start_timestamp"] <= timestamps[-24]).all()


def test_catalog_runner_keeps_portfolio_and_event_lineage() -> None:
    start = pd.Timestamp("2024-01-01 00:00", tz="Asia/Shanghai")
    events = (
        ReliabilityEvent("OUTAGE_2H", start, 2),
        ReliabilityEvent("OUTAGE_4H", start, 4),
    )

    result = run_reliability_catalog(
        _workbook(),
        replay_hourly=_replay_state(),
        fixed_capacities=_fixed(),
        cost_params=PlanningCostParams(grid_import_limit_kw=100.0),
        events=events,
        portfolio_id="resilience",
    )

    assert set(result["summary"]["event_id"]) == {"OUTAGE_2H", "OUTAGE_4H"}
    assert result["summary"]["portfolio_id"].eq("resilience").all()
    assert set(result["hourly"]["event_id"]) == {"OUTAGE_2H", "OUTAGE_4H"}
