"""Rolling-horizon fixed-capacity replay with committed-state handoff."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import pandas as pd

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.planning.results import extract_capacity_planning_results
from zero_carbon_park.replay.results import (
    ReplayResult,
    ReplayState,
    evaluate_replay_quality,
)
from zero_carbon_park.typical_days.definitions import TypicalDayConfig


class ReplaySolveError(RuntimeError):
    """Raised before any failed or incomplete window can be published."""


@dataclass(frozen=True)
class ReplayConfig:
    lookahead_hours: int = 168
    commit_hours: int = 24
    solver_time_limit_seconds: float = 600.0
    solver_mip_gap: float = 0.01
    ens_tolerance_kwh: float = 1e-6
    balance_tolerance_kw: float = 1e-5
    enforce_annual_cycle: bool = True
    formal_validation: bool = True
    study_year: int = 2024
    expected_hours: int = 8_784
    local_timezone: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        if self.commit_hours <= 0 or self.lookahead_hours < self.commit_hours:
            raise ValueError("lookahead_hours must be >= positive commit_hours")
        if self.solver_time_limit_seconds <= 0:
            raise ValueError("solver_time_limit_seconds must be positive")
        if not 0 <= self.solver_mip_gap < 1:
            raise ValueError("solver_mip_gap must be within [0, 1)")
        if self.expected_hours <= 0:
            raise ValueError("expected_hours must be positive")


def run_rolling_replay(
    workbook: InputWorkbook,
    *,
    fixed_capacities: Mapping[str, float],
    cost_params: PlanningCostParams,
    config: ReplayConfig | None = None,
    initial_state: ReplayState | None = None,
    solve: Callable[..., str] = solve_model,
) -> ReplayResult:
    """Replay every input hour once while optimizing overlapping lookahead windows.

    Only the first ``commit_hours`` rows are retained from each solve.  The state
    at that committed boundary—not the lookahead endpoint—is passed to the next
    window, preventing overlap duplication and silent storage resets.
    """

    selected = config or ReplayConfig()
    timeseries = workbook.timeseries.reset_index(drop=True).copy()
    if "timestamp_local" not in timeseries:
        raise ValueError("chronological replay requires timestamp_local")
    timestamps = pd.to_datetime(timeseries["timestamp_local"], errors="coerce")
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError("timestamp_local must be valid and unique")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("timestamp_local must be chronological")
    if len(timeseries) > 1 and not timestamps.diff().iloc[1:].eq(
        pd.Timedelta(hours=1)
    ).all():
        raise ValueError("timestamp_local must be continuous hourly data")
    formal_time_axis_valid = _is_formal_time_axis(timestamps, selected)
    if selected.formal_validation and not formal_time_axis_valid:
        raise ValueError(
            f"formal replay requires the complete {selected.study_year} local-time "
            f"axis with {selected.expected_hours} hourly rows in {selected.local_timezone}"
        )

    state = initial_state or ReplayState(
        0.5 * float(fixed_capacities["battery_energy_capacity_kwh"]),
        0.3 * float(fixed_capacities["h2_storage_capacity_kg"]),
    )
    start_state = state
    committed_frames: list[pd.DataFrame] = []
    window_rows: list[dict[str, float | int | str]] = []

    for window_number, start in enumerate(
        range(0, len(timeseries), selected.commit_hours)
    ):
        stop = min(start + selected.lookahead_hours, len(timeseries))
        commit_count = min(selected.commit_hours, len(timeseries) - start)
        is_final_commit = start + commit_count == len(timeseries)
        terminal_state = (
            start_state
            if is_final_commit and selected.enforce_annual_cycle
            else state
        )
        window_workbook = _slice_workbook(workbook, start, stop)
        day_id = f"RW{window_number:04d}"
        day = TypicalDayConfig(
            day_id=day_id,
            name="rolling replay window",
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
            [(day, window_workbook)],
            cost_params,
            capacity_mode="fixed",
            fixed_capacities=fixed_capacities,
            initial_battery_soc_kwh=state.battery_soc_kwh,
            initial_h2_inventory_kg=state.h2_inventory_kg,
            # Until the common builder's optional terminal-state switch is used,
            # a neutral horizon boundary prevents artificial depletion.  State
            # handoff still occurs at the shorter committed boundary.
            final_battery_soc_kwh=terminal_state.battery_soc_kwh,
            final_h2_inventory_kg=terminal_state.h2_inventory_kg,
        )
        status = solve(
            model,
            time_limit_seconds=selected.solver_time_limit_seconds,
            mip_gap=selected.solver_mip_gap,
        )
        if status != "optimal":
            raise ReplaySolveError(
                f"window {window_number} starting at {timestamps.iloc[start]} "
                f"terminated as {status}; no replay result was published"
            )
        extracted = extract_capacity_planning_results(model, status)["hourly"]
        committed = extracted.iloc[:commit_count].copy()
        committed.insert(
            0,
            "timestamp_local",
            timestamps.iloc[start : start + commit_count].to_numpy(),
        )
        committed.insert(0, "window_number", window_number)
        committed_frames.append(committed)

        end_row = committed.iloc[-1]
        next_state = ReplayState(
            battery_soc_kwh=float(end_row["battery_soc_kwh"]),
            h2_inventory_kg=float(end_row["h2_storage_kg"]),
        )
        window_rows.append(
            {
                "window_number": window_number,
                "start_timestamp": timestamps.iloc[start].isoformat(),
                "lookahead_hours": stop - start,
                "commit_hours": commit_count,
                "annual_cycle_target_applied": bool(
                    is_final_commit and selected.enforce_annual_cycle
                ),
                "initial_battery_soc_kwh": state.battery_soc_kwh,
                "initial_h2_inventory_kg": state.h2_inventory_kg,
                "committed_end_battery_soc_kwh": next_state.battery_soc_kwh,
                "committed_end_h2_inventory_kg": next_state.h2_inventory_kg,
                "termination_condition": getattr(model, "solve_metadata", {}).get(
                    "termination_condition", status
                ),
                "mip_gap": getattr(model, "solve_metadata", {}).get("actual_gap"),
            }
        )
        state = next_state

    hourly = pd.concat(committed_frames, ignore_index=True)
    windows = pd.DataFrame(window_rows)
    report, eligible, extreme_dates = evaluate_replay_quality(
        hourly,
        expected_hours=(
            selected.expected_hours if selected.formal_validation else len(timeseries)
        ),
        ens_tolerance_kwh=selected.ens_tolerance_kwh,
        balance_tolerance_kw=selected.balance_tolerance_kw,
    )
    report["formal_time_axis_valid"] = formal_time_axis_valid
    eligible = eligible and selected.formal_validation and formal_time_axis_valid
    return ReplayResult(
        hourly=hourly,
        windows=windows,
        initial_state=start_state,
        final_state=state,
        quality_report=report,
        publication_eligible=eligible,
        suggested_extreme_dates=extreme_dates,
    )


def _slice_workbook(workbook: InputWorkbook, start: int, stop: int) -> InputWorkbook:
    return InputWorkbook(
        timeseries=workbook.timeseries.iloc[start:stop].reset_index(drop=True).copy(),
        device_params=workbook.device_params.copy(deep=True),
        economic_params=workbook.economic_params.copy(deep=True),
        scenarios=workbook.scenarios.copy(deep=True),
    )


def _is_formal_time_axis(timestamps: pd.Series, config: ReplayConfig) -> bool:
    if len(timestamps) != config.expected_hours:
        return False
    actual = pd.DatetimeIndex(timestamps)
    if actual.tz is None or str(actual.tz) != config.local_timezone:
        return False
    expected = pd.date_range(
        f"{config.study_year}-01-01 00:00:00",
        periods=config.expected_hours,
        freq="h",
        tz=config.local_timezone,
    )
    return actual.equals(expected)


__all__ = [
    "ReplayConfig",
    "ReplayResult",
    "ReplaySolveError",
    "ReplayState",
    "run_rolling_replay",
]
