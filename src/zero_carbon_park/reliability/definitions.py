"""Auditable definitions for deterministic reliability stress events."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


SUPPORTED_DURATIONS = (2, 4, 8, 24)
DEVICE_AVAILABILITY_COLUMNS = {
    "battery": "battery_available_ratio",
    "fuel_cell": "fuel_cell_available_ratio",
    "heat_pump": "heat_pump_available_ratio",
    "electrolyzer": "electrolyzer_available_ratio",
    "pv": "pv_available_ratio",
    "wind": "wind_available_ratio",
    "gas_boiler": "gas_boiler_available_ratio",
}


@dataclass(frozen=True)
class ReliabilityEvent:
    event_id: str
    start_timestamp: pd.Timestamp
    duration_hours: int
    failed_devices: tuple[str, ...] = ()
    renewable_derate: float = 1.0
    description: str = "deterministic islanding stress event"

    def __post_init__(self) -> None:
        timestamp = pd.Timestamp(self.start_timestamp)
        if timestamp.tzinfo is None:
            raise ValueError("reliability event start_timestamp must be timezone-aware")
        if self.duration_hours <= 0:
            raise ValueError("reliability event duration_hours must be positive")
        unknown = set(self.failed_devices) - set(DEVICE_AVAILABILITY_COLUMNS)
        if unknown:
            raise ValueError(f"unknown failed devices: {sorted(unknown)}")
        if not 0.0 <= self.renewable_derate <= 1.0:
            raise ValueError("renewable_derate must be within [0, 1]")


def default_outage_durations() -> tuple[int, ...]:
    return SUPPORTED_DURATIONS


def select_stress_start_times(
    annual_inputs: pd.DataFrame,
    replay_hourly: pd.DataFrame,
    *,
    max_duration_hours: int = max(SUPPORTED_DURATIONS),
) -> pd.DataFrame:
    """Select auditable outage starts from annual loads, weather and actual states."""

    inputs = annual_inputs.copy()
    states = replay_hourly.copy()
    inputs["timestamp_local"] = pd.to_datetime(inputs["timestamp_local"], errors="coerce")
    states["timestamp_local"] = pd.to_datetime(states["timestamp_local"], errors="coerce")
    merged = inputs.merge(
        states.loc[:, ["timestamp_local", "battery_soc_kwh", "h2_storage_kg"]],
        on="timestamp_local",
        how="inner",
        validate="one_to_one",
    )
    if merged.empty or merged["timestamp_local"].isna().any():
        raise ValueError("annual inputs and replay states must share valid timestamps")
    if max_duration_hours <= 0:
        raise ValueError("max_duration_hours must be positive")
    first_state = states["timestamp_local"].min()
    final_input = inputs["timestamp_local"].max()
    latest_start = final_input - pd.Timedelta(hours=max_duration_hours - 1)
    merged = merged.loc[
        (merged["timestamp_local"] > first_state)
        & (merged["timestamp_local"] <= latest_start)
    ].copy()
    if merged.empty:
        raise ValueError(
            "annual replay does not leave a pre-event state and complete outage horizon"
        )
    pv = "pv_cf" if "pv_cf" in merged else "pv_available_kw"
    wind = "wind_cf_calibrated" if "wind_cf_calibrated" in merged else (
        "wind_cf" if "wind_cf" in merged else "wind_available_kw"
    )
    merged["renewable_score"] = merged[pv].astype(float) + merged[wind].astype(float)
    merged["month"] = merged["timestamp_local"].dt.month
    records: list[dict[str, object]] = []
    for month, group in merged.groupby("month", sort=True):
        row = group.loc[group["electric_load_kw"].idxmax()]
        records.append(
            {
                "reason": "monthly_high_electric_load",
                "month": int(month),
                "start_timestamp": row["timestamp_local"],
            }
        )
    selectors = {
        "minimum_battery_soc": merged["battery_soc_kwh"].idxmin(),
        "minimum_h2_inventory": merged["h2_storage_kg"].idxmin(),
        "lowest_renewable": merged["renewable_score"].idxmin(),
    }
    if "air_temperature_c" in merged:
        selectors["extreme_cold"] = merged["air_temperature_c"].idxmin()
    for reason, index in selectors.items():
        row = merged.loc[index]
        records.append(
            {
                "reason": reason,
                "month": int(row["timestamp_local"].month),
                "start_timestamp": row["timestamp_local"],
            }
        )
    return pd.DataFrame(records).drop_duplicates(
        ["reason", "start_timestamp"]
    ).reset_index(drop=True)


def build_outage_event_catalog(
    starts: pd.DataFrame,
    *,
    durations: tuple[int, ...] = SUPPORTED_DURATIONS,
) -> tuple[ReliabilityEvent, ...]:
    """Expand selected starts into the deterministic 2/4/8/24-hour event set."""

    events: list[ReliabilityEvent] = []
    for row_number, row in starts.iterrows():
        for duration in durations:
            events.append(
                ReliabilityEvent(
                    event_id=f"{str(row['reason']).upper()}_{row_number:02d}_{duration:02d}H",
                    start_timestamp=pd.Timestamp(row["start_timestamp"]),
                    duration_hours=int(duration),
                    description=f"{row['reason']} + grid outage",
                )
            )
    return tuple(events)


__all__ = [
    "DEVICE_AVAILABILITY_COLUMNS",
    "ReliabilityEvent",
    "SUPPORTED_DURATIONS",
    "build_outage_event_catalog",
    "default_outage_durations",
    "select_stress_start_times",
]
