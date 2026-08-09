from __future__ import annotations

import pandas as pd
import pytest

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.replay.runner import (
    ReplayConfig,
    ReplaySolveError,
    ReplayState,
    run_rolling_replay,
)


def _parameters(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"parameter": name, "value": value} for name, value in values.items()]
    )


def _workbook(hours: int = 72, *, grid_limited_case: bool = False) -> InputWorkbook:
    timestamps = pd.date_range(
        "2024-01-01", periods=hours, freq="h", tz="Asia/Shanghai"
    )
    electric = 5.0 if grid_limited_case else 2.0
    timeseries = pd.DataFrame(
        {
            "timestamp_local": timestamps,
            "pv_cf": 0.0,
            "wind_cf": 0.0,
            "electric_load_kw": electric,
            "critical_load_kw": 1.0,
            "important_load_kw": 1.0,
            "interruptible_load_kw": electric - 2.0,
            "heat_load_kw": 0.0,
            "hydrogen_load_kg": 0.0,
            "electricity_price_cny_per_kwh": 1.0,
            "gas_price_cny_per_m3": 3.0,
            "grid_emission_kgco2_per_kwh": 0.6,
            "carbon_price_cny_per_tco2": 0.0,
        }
    )
    return InputWorkbook(
        timeseries=timeseries,
        device_params=_parameters(
            {
                "heat_pump_COP": 3.0,
                "gas_boiler_heat_kW": 10.0,
                "gas_boiler_eff": 0.9,
                "gas_lhv_kwh_per_m3": 9.8,
                "battery_eta_ch": 0.95,
                "battery_eta_dis": 0.95,
                "electrolyzer_kWh_per_kgH2": 50.0,
                "fuel_cell_kWh_per_kgH2": 20.0,
            }
        ),
        economic_params=_parameters(
            {
                "gas_emission_factor": 2.0,
                "curtail_penalty": 0.0,
                "battery_om": 0.0,
                "electrolyzer_om": 0.0,
                "fuel_cell_om": 0.0,
                "h2_external_supply_cost": 100.0,
            }
        ),
        scenarios=pd.DataFrame(),
    )


def _fixed() -> dict[str, float]:
    return {
        "wind_capacity_kw": 0.0,
        "pv_capacity_kw": 0.0,
        "battery_power_capacity_kw": 0.0,
        "battery_energy_capacity_kwh": 0.0,
        "electrolyzer_power_capacity_kw": 0.0,
        "h2_storage_capacity_kg": 0.0,
        "fuel_cell_power_capacity_kw": 0.0,
        "heat_pump_power_capacity_kw": 0.0,
    }


def test_rolling_replay_commits_each_hour_once_and_passes_state() -> None:
    result = run_rolling_replay(
        _workbook(72),
        fixed_capacities=_fixed(),
        cost_params=PlanningCostParams(grid_import_limit_kw=10.0),
        config=ReplayConfig(lookahead_hours=48, commit_hours=24),
        initial_state=ReplayState(0.0, 0.0),
    )

    assert len(result.hourly) == 72
    assert result.hourly["timestamp_local"].is_unique
    assert result.hourly["timestamp_local"].is_monotonic_increasing
    assert list(result.windows["commit_hours"]) == [24, 24, 24]
    assert result.windows.iloc[1]["initial_battery_soc_kwh"] == pytest.approx(
        result.windows.iloc[0]["committed_end_battery_soc_kwh"]
    )
    assert result.final_state == ReplayState(0.0, 0.0)
    assert result.publication_eligible
    assert result.quality_report["ens_total_kwh"] == pytest.approx(0.0)


def test_last_window_can_be_shorter_than_lookahead_without_duplicates() -> None:
    result = run_rolling_replay(
        _workbook(50),
        fixed_capacities=_fixed(),
        cost_params=PlanningCostParams(grid_import_limit_kw=10.0),
        config=ReplayConfig(lookahead_hours=48, commit_hours=24),
        initial_state=ReplayState(0.0, 0.0),
    )
    assert len(result.hourly) == 50
    assert list(result.windows["commit_hours"]) == [24, 24, 2]
    assert result.hourly["timestamp_local"].nunique() == 50


def test_normal_year_ens_is_explicit_and_blocks_publication() -> None:
    result = run_rolling_replay(
        _workbook(48, grid_limited_case=True),
        fixed_capacities=_fixed(),
        cost_params=PlanningCostParams(grid_import_limit_kw=2.0),
        config=ReplayConfig(lookahead_hours=48, commit_hours=24),
        initial_state=ReplayState(0.0, 0.0),
    )
    assert result.quality_report["ens_total_kwh"] > 0.0
    assert not result.publication_eligible
    assert result.suggested_extreme_dates


def test_failed_window_is_not_returned_as_a_valid_replay() -> None:
    with pytest.raises(ReplaySolveError, match="window 0"):
        run_rolling_replay(
            _workbook(48),
            fixed_capacities=_fixed(),
            cost_params=PlanningCostParams(grid_import_limit_kw=10.0),
            config=ReplayConfig(lookahead_hours=48, commit_hours=24),
            initial_state=ReplayState(0.0, 0.0),
            solve=lambda model, **kwargs: "time_limit",
        )
