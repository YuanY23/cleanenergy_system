"""Probability-free reliability metrics for deterministic stress tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_deterministic_reliability_metrics(
    hourly: pd.DataFrame, *, tolerance_kwh: float = 1e-9
) -> dict[str, float | int]:
    """Compute ENS and survival metrics without implying outage probabilities."""

    required = {
        "critical_load_kw",
        "important_load_kw",
        "interruptible_load_kw",
        "load_shed_critical_kwh",
        "load_shed_important_kwh",
        "load_shed_interruptible_kwh",
        "battery_soc_kwh",
        "h2_storage_kg",
    }
    missing = required - set(hourly.columns)
    if missing:
        raise ValueError(f"reliability hourly result missing columns: {sorted(missing)}")
    critical_ens = float(hourly["load_shed_critical_kwh"].sum())
    important_ens = float(hourly["load_shed_important_kwh"].sum())
    interruptible_ens = float(hourly["load_shed_interruptible_kwh"].sum())
    total_ens = critical_ens + important_ens + interruptible_ens
    critical_demand = float(hourly["critical_load_kw"].sum())
    any_loss = (
        hourly[
            [
                "load_shed_critical_kwh",
                "load_shed_important_kwh",
                "load_shed_interruptible_kwh",
            ]
        ].sum(axis=1)
        > tolerance_kwh
    ).to_numpy()
    critical_loss = (
        hourly["load_shed_critical_kwh"].to_numpy(dtype=float) > tolerance_kwh
    )
    first_critical_loss = np.flatnonzero(critical_loss)
    survival = int(first_critical_loss[0]) if len(first_critical_loss) else len(hourly)
    return {
        "ens_critical_kwh": critical_ens,
        "ens_important_kwh": important_ens,
        "ens_interruptible_kwh": interruptible_ens,
        "ens_total_kwh": total_ens,
        "critical_load_supply_ratio": (
            1.0 - critical_ens / critical_demand if critical_demand > 0 else 1.0
        ),
        "loss_of_load_hours": int(any_loss.sum()),
        "max_consecutive_loss_hours": _max_consecutive_true(any_loss),
        "island_survival_hours": survival,
        "minimum_battery_soc_kwh": float(hourly["battery_soc_kwh"].min()),
        "minimum_h2_inventory_kg": float(hourly["h2_storage_kg"].min()),
    }


def validate_nested_event_results(
    summary: pd.DataFrame, *, tolerance_kwh: float = 1e-8
) -> None:
    """Reject unexplained ENS improvement as a same-start event gets longer."""

    required = {"duration_hours", "ens_total_kwh"}
    if not required.issubset(summary.columns):
        raise ValueError("nested event summary requires duration_hours and ens_total_kwh")
    ordered = summary.sort_values("duration_hours")
    if (ordered["ens_total_kwh"].diff().fillna(0.0) < -tolerance_kwh).any():
        raise ValueError("nested-event ENS must be non-decreasing with duration")


def _max_consecutive_true(values: np.ndarray) -> int:
    longest = current = 0
    for selected in values:
        current = current + 1 if bool(selected) else 0
        longest = max(longest, current)
    return int(longest)


__all__ = [
    "compute_deterministic_reliability_metrics",
    "validate_nested_event_results",
]
