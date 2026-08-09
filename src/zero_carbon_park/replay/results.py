"""Result contract and physical quality checks for chronological replay."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ReplayState:
    """State handed from the committed end of one window to the next."""

    battery_soc_kwh: float
    h2_inventory_kg: float


@dataclass(frozen=True)
class ReplayResult:
    hourly: pd.DataFrame
    windows: pd.DataFrame
    initial_state: ReplayState
    final_state: ReplayState
    quality_report: dict[str, float | int | str | bool]
    publication_eligible: bool
    suggested_extreme_dates: tuple[str, ...]


def evaluate_replay_quality(
    hourly: pd.DataFrame,
    *,
    expected_hours: int,
    ens_tolerance_kwh: float,
    balance_tolerance_kw: float,
) -> tuple[dict[str, float | int | str], bool, tuple[str, ...]]:
    """Apply uniqueness, balance and normal-year ENS publication gates."""

    if len(hourly) != expected_hours:
        raise ValueError(
            f"replay must contain {expected_hours} committed hours, got {len(hourly)}"
        )
    timestamp = pd.to_datetime(hourly["timestamp_local"], errors="coerce")
    if timestamp.isna().any() or timestamp.duplicated().any():
        raise ValueError("replay timestamps must be valid and unique")
    if not timestamp.is_monotonic_increasing:
        raise ValueError("replay timestamps must be chronological")

    shed_columns = [
        "load_shed_critical_kwh",
        "load_shed_important_kwh",
        "load_shed_interruptible_kwh",
    ]
    ens = hourly[shed_columns].sum(axis=1)
    served_load = hourly["electric_load_kw"] - ens
    supply = (
        hourly["grid_buy_kw"]
        + hourly["pv_used_kw"]
        + hourly["wind_used_kw"]
        + hourly["battery_discharge_kw"]
        + hourly["fuel_cell_power_kw"]
    )
    demand = (
        served_load
        + hourly["heat_pump_power_kw"]
        + hourly["battery_charge_kw"]
        + hourly["electrolyzer_power_kw"]
    )
    max_balance_residual = float((supply - demand).abs().max())
    ens_total = float(ens.sum())
    worst_dates: tuple[str, ...] = ()
    if ens_total > ens_tolerance_kwh:
        dated = pd.DataFrame({"date": timestamp.dt.date, "ens": ens})
        worst_dates = tuple(
            str(value)
            for value in (
                dated.groupby("date")["ens"]
                .sum()
                .sort_values(ascending=False)
                .loc[lambda values: values > ens_tolerance_kwh]
                .head(4)
                .index
            )
        )
    report: dict[str, float | int | str] = {
        "status": "passed"
        if ens_total <= ens_tolerance_kwh
        and max_balance_residual <= balance_tolerance_kw
        else "failed",
        "committed_hours": len(hourly),
        "unique_hours": int(timestamp.nunique()),
        "ens_total_kwh": ens_total,
        "ens_critical_kwh": float(hourly["load_shed_critical_kwh"].sum()),
        "ens_important_kwh": float(hourly["load_shed_important_kwh"].sum()),
        "ens_interruptible_kwh": float(
            hourly["load_shed_interruptible_kwh"].sum()
        ),
        "max_power_balance_residual_kw": max_balance_residual,
    }
    eligible = (
        ens_total <= ens_tolerance_kwh
        and max_balance_residual <= balance_tolerance_kw
    )
    return report, eligible, worst_dates


__all__ = ["ReplayResult", "ReplayState", "evaluate_replay_quality"]
