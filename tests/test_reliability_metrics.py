from __future__ import annotations

import pandas as pd
import pytest

from zero_carbon_park.reliability.metrics import (
    compute_deterministic_reliability_metrics,
    validate_nested_event_results,
)


def _hourly_shedding() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "critical_load_kw": [2.0] * 6,
            "important_load_kw": [1.0] * 6,
            "interruptible_load_kw": [1.0] * 6,
            "load_shed_critical_kwh": [0.0, 0.0, 1.0, 2.0, 0.0, 0.0],
            "load_shed_important_kwh": [0.0, 1.0, 1.0, 1.0, 0.0, 0.0],
            "load_shed_interruptible_kwh": [1.0, 1.0, 1.0, 1.0, 0.0, 0.0],
            "battery_soc_kwh": [4.0, 2.0, 1.0, 0.0, 0.0, 0.0],
            "h2_storage_kg": [3.0, 3.0, 2.0, 1.0, 1.0, 1.0],
        }
    )


def test_deterministic_metrics_use_ens_not_probability_names() -> None:
    metrics = compute_deterministic_reliability_metrics(_hourly_shedding())

    assert metrics["ens_critical_kwh"] == pytest.approx(3.0)
    assert metrics["ens_total_kwh"] == pytest.approx(10.0)
    assert metrics["critical_load_supply_ratio"] == pytest.approx(0.75)
    assert metrics["loss_of_load_hours"] == 4
    assert metrics["max_consecutive_loss_hours"] == 4
    assert metrics["island_survival_hours"] == 2
    assert metrics["minimum_battery_soc_kwh"] == 0.0
    assert not any("eens" in name.lower() or "lolp" in name.lower() for name in metrics)


def test_nested_longer_events_cannot_report_unexplained_lower_ens() -> None:
    valid = pd.DataFrame(
        {"duration_hours": [2, 4, 8, 24], "ens_total_kwh": [0.0, 1.0, 4.0, 20.0]}
    )
    validate_nested_event_results(valid)

    invalid = valid.copy()
    invalid.loc[2, "ens_total_kwh"] = 0.5
    with pytest.raises(ValueError, match="non-decreasing"):
        validate_nested_event_results(invalid)
