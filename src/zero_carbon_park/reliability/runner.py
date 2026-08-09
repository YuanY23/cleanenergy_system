"""Run one islanded event from the actual pre-event annual replay state."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import pandas as pd
from pyomo.environ import Objective, minimize

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.planning.results import extract_capacity_planning_hourly
from zero_carbon_park.reliability.definitions import (
    DEVICE_AVAILABILITY_COLUMNS,
    ReliabilityEvent,
)
from zero_carbon_park.reliability.metrics import (
    compute_deterministic_reliability_metrics,
)
from zero_carbon_park.typical_days.definitions import TypicalDayConfig


@dataclass(frozen=True)
class ReliabilityResult:
    event: ReliabilityEvent
    hourly: pd.DataFrame
    summary: dict[str, float | int | str]


def run_reliability_event(
    annual_workbook: InputWorkbook,
    *,
    replay_hourly: pd.DataFrame,
    fixed_capacities: Mapping[str, float],
    cost_params: PlanningCostParams,
    event: ReliabilityEvent,
    solve: Callable[..., str] = solve_model,
) -> ReliabilityResult:
    """Solve a deterministic outage/fault event with no grid or external H2."""

    event_frame = _event_timeseries(annual_workbook.timeseries, event)
    initial_battery, initial_h2 = _pre_event_state(
        replay_hourly, pd.Timestamp(event.start_timestamp)
    )
    event_workbook = InputWorkbook(
        timeseries=event_frame,
        device_params=annual_workbook.device_params,
        economic_params=annual_workbook.economic_params,
        scenarios=annual_workbook.scenarios,
    )
    config = TypicalDayConfig(
        day_id=event.event_id,
        name=event.description,
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
        [(config, event_workbook)],
        cost_params,
        capacity_mode="fixed",
        fixed_capacities=fixed_capacities,
        islanded=True,
        allow_external_h2=False,
        allow_hydrogen_shedding=True,
        initial_battery_soc_kwh=initial_battery,
        initial_h2_inventory_kg=initial_h2,
        enforce_terminal_states=False,
    )
    # Among solutions with identical tiered ENS, defer critical curtailment as
    # long as physically possible so "survival hours" has its engineering
    # meaning: uninterrupted critical supply from the event start.
    base_objective = model.annual_total_cost.expr
    model.annual_total_cost.deactivate()
    model.reliability_event_objective = Objective(
        expr=base_objective
        + sum(
            (event.duration_hours - int(t)) * model.load_shed_critical[event.event_id, t]
            for t in model.T
        ),
        sense=minimize,
    )
    status = solve(model, time_limit_seconds=120.0, mip_gap=0.001)
    if status != "optimal":
        raise RuntimeError(f"reliability event {event.event_id} terminated as {status}")
    hourly = extract_capacity_planning_hourly(model)
    hourly.insert(0, "timestamp_local", event_frame["timestamp_local"].to_numpy())
    for column in (
        "critical_load_kw",
        "important_load_kw",
        "interruptible_load_kw",
    ):
        hourly[column] = event_frame[column].to_numpy(dtype=float)
    metrics = compute_deterministic_reliability_metrics(hourly)
    summary: dict[str, float | int | str] = {
        "event_id": event.event_id,
        "start_timestamp": pd.Timestamp(event.start_timestamp).isoformat(),
        "duration_hours": event.duration_hours,
        "initial_battery_soc_kwh": initial_battery,
        "initial_h2_inventory_kg": initial_h2,
        "failed_devices": ",".join(event.failed_devices),
        "metric_scope": "deterministic_stress_test",
        "solver_status": status,
        **metrics,
    }
    return ReliabilityResult(event=event, hourly=hourly, summary=summary)


def run_reliability_catalog(
    annual_workbook: InputWorkbook,
    *,
    replay_hourly: pd.DataFrame,
    fixed_capacities: Mapping[str, float],
    cost_params: PlanningCostParams,
    events: tuple[ReliabilityEvent, ...],
    portfolio_id: str,
    solve: Callable[..., str] = solve_model,
) -> dict[str, pd.DataFrame]:
    """Run a deterministic event catalog and retain portfolio/event lineage."""

    if not events:
        raise ValueError("reliability catalog must contain at least one event")
    if not portfolio_id.strip():
        raise ValueError("portfolio_id must not be empty")
    results = [
        run_reliability_event(
            annual_workbook,
            replay_hourly=replay_hourly,
            fixed_capacities=fixed_capacities,
            cost_params=cost_params,
            event=event,
            solve=solve,
        )
        for event in events
    ]
    summaries = pd.DataFrame([result.summary for result in results])
    summaries.insert(0, "portfolio_id", portfolio_id)
    hourly_frames: list[pd.DataFrame] = []
    for result in results:
        frame = result.hourly.copy()
        frame.insert(0, "event_id", result.event.event_id)
        frame.insert(0, "portfolio_id", portfolio_id)
        hourly_frames.append(frame)
    return {
        "summary": summaries,
        "hourly": pd.concat(hourly_frames, ignore_index=True),
    }


def _event_timeseries(
    annual_timeseries: pd.DataFrame, event: ReliabilityEvent
) -> pd.DataFrame:
    timestamps = pd.to_datetime(
        annual_timeseries["timestamp_local"], errors="coerce"
    )
    start = pd.Timestamp(event.start_timestamp)
    end = start + pd.Timedelta(hours=event.duration_hours)
    selected = annual_timeseries.loc[
        (timestamps >= start) & (timestamps < end)
    ].copy(deep=True)
    if len(selected) != event.duration_hours:
        raise ValueError("annual inputs do not fully cover the reliability event")
    selected.reset_index(drop=True, inplace=True)
    availability_columns = set(DEVICE_AVAILABILITY_COLUMNS.values()) | {
        "grid_available_ratio",
        "h2_external_available_ratio",
    }
    for column in availability_columns:
        if column not in selected:
            selected[column] = 1.0
    selected["grid_available_ratio"] = 0.0
    selected["h2_external_available_ratio"] = 0.0
    selected["pv_available_ratio"] *= event.renewable_derate
    selected["wind_available_ratio"] *= event.renewable_derate
    for device in event.failed_devices:
        selected[DEVICE_AVAILABILITY_COLUMNS[device]] = 0.0
    return selected


def _pre_event_state(
    replay_hourly: pd.DataFrame, start: pd.Timestamp
) -> tuple[float, float]:
    required = {"timestamp_local", "battery_soc_kwh", "h2_storage_kg"}
    missing = required - set(replay_hourly.columns)
    if missing:
        raise ValueError(f"annual replay state is missing: {sorted(missing)}")
    timestamps = pd.to_datetime(replay_hourly["timestamp_local"], errors="coerce")
    prior = replay_hourly.loc[timestamps < start]
    if prior.empty:
        raise ValueError("no actual pre-event replay state exists before event start")
    row = prior.iloc[-1]
    return float(row["battery_soc_kwh"]), float(row["h2_storage_kg"])


__all__ = [
    "ReliabilityResult",
    "run_reliability_catalog",
    "run_reliability_event",
]
