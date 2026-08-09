from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from zero_carbon_park.typical_days.clustering import (
    RepresentativePeriodConfig,
    build_representative_periods,
)
from zero_carbon_park.typical_days.diagnostics import (
    CompressionThresholds,
    evaluate_compression,
    validate_compression,
)
from zero_carbon_park.typical_days.runner import write_representative_period_artifacts


def _annual_frame() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2024-01-01", "2024-12-31 23:00", freq="h", tz="Asia/Shanghai"
    )
    day_index = np.arange(len(timestamps)) // 24
    pattern = day_index % 8
    hour = timestamps.hour.to_numpy()

    electric_levels = np.array([80, 160, 100, 120, 90, 110, 130, 140], dtype=float)
    heat_levels = np.array([100, 90, 180, 120, 80, 140, 110, 130], dtype=float)
    h2_levels = np.array([10, 11, 12, 17, 9, 13, 14, 15], dtype=float)
    pv_levels = np.array([0.1, 1.0, 0.8, 0.3, 0.5, 0.7, 0.9, 0.6], dtype=float)
    wind_levels = np.array([0.1, 0.9, 0.7, 0.2, 0.6, 0.8, 1.0, 0.5], dtype=float)

    daylight = np.maximum(np.sin((hour - 6) / 12 * np.pi), 0.0)
    load_shape = 1.0 + 0.08 * np.sin(hour / 24 * 2 * np.pi)
    return pd.DataFrame(
        {
            "timestamp_local": timestamps,
            "electric_load_kw": electric_levels[pattern] * load_shape,
            "heat_load_kw": heat_levels[pattern] * (1.05 - 0.05 * load_shape),
            "hydrogen_load_kg": h2_levels[pattern],
            "pv_cf": pv_levels[pattern] * daylight,
            "wind_cf_calibrated": wind_levels[pattern]
            * (0.9 + 0.1 * np.cos(hour / 24 * 2 * np.pi)),
            "electricity_price_cny_per_kwh": 0.35
            + 0.08 * (hour >= 17) * (hour < 21),
        }
    )


def test_representative_periods_require_timezone_aware_2024_leap_year() -> None:
    frame = _annual_frame()
    naive = frame.copy()
    naive["timestamp_local"] = naive["timestamp_local"].dt.tz_localize(None)

    with pytest.raises(ValueError, match="timezone-aware"):
        build_representative_periods(naive, RepresentativePeriodConfig(k=8))
    with pytest.raises(ValueError, match="8784"):
        build_representative_periods(frame.iloc[:-24], RepresentativePeriodConfig(k=8))
    with pytest.raises(ValueError, match="8, 12 or 16"):
        RepresentativePeriodConfig(k=10)


def test_compression_is_deterministic_traceable_and_chronological() -> None:
    frame = _annual_frame()
    config = RepresentativePeriodConfig(k=8, seed=20240809)

    first = build_representative_periods(frame, config)
    second = build_representative_periods(frame, config)

    assert len(first.representative_days) == 8
    assert len(first.day_mapping) == 366
    assert first.representative_days["weight_days"].sum() == 366
    assert set(first.representative_days["representative_date"]).issubset(
        set(first.day_mapping["calendar_date"])
    )
    assert set(first.extreme_days) == {
        "electric_peak",
        "heat_peak",
        "low_renewable",
        "joint_stress",
    }
    for kind, day in first.extreme_days.items():
        selected = first.representative_days.set_index("representative_date")
        assert day in selected.index
        assert kind in selected.loc[day, "extreme_kinds"]

    pd.testing.assert_frame_equal(first.day_mapping, second.day_mapping)
    pd.testing.assert_frame_equal(first.transition_counts, second.transition_counts)
    pd.testing.assert_frame_equal(first.normalization, second.normalization)
    assert len(first.chronology_links) == 366
    assert first.chronology_links["is_year_wrap"].sum() == 1
    assert int(first.transition_counts.to_numpy().sum()) == 366
    assert first.seed == 20240809
    assert "electricity_price_cny_per_kwh" in first.feature_columns


def test_diagnostics_cover_annual_and_monthly_metrics_and_thresholds() -> None:
    frame = _annual_frame()
    compressed = build_representative_periods(
        frame, RepresentativePeriodConfig(k=8, seed=7)
    )

    diagnostics = evaluate_compression(frame, compressed)

    assert set(diagnostics["scope"]) == {"annual", "monthly"}
    assert set(diagnostics["metric"]) == {"energy", "peak", "p5", "p50", "p95"}
    assert set(diagnostics.loc[diagnostics["scope"] == "monthly", "month"]) == set(
        range(1, 13)
    )
    assert diagnostics["relative_error"].max() < 1e-10
    validate_compression(
        diagnostics,
        CompressionThresholds(
            annual_energy=1e-9,
            annual_shape=1e-9,
            monthly_energy=1e-9,
            monthly_shape=1e-9,
        ),
    )


@pytest.mark.parametrize("k", [8, 12, 16])
def test_supported_period_counts_preserve_366_day_weights(k: int) -> None:
    result = build_representative_periods(
        _annual_frame(), RepresentativePeriodConfig(k=k, seed=11)
    )
    assert len(result.representative_days) == k
    assert result.representative_days["weight_days"].sum() == 366


def test_artifact_writer_exports_auditable_chronology(tmp_path) -> None:
    frame = _annual_frame()
    result = build_representative_periods(
        frame, RepresentativePeriodConfig(k=8, seed=99)
    )
    diagnostics = evaluate_compression(frame, result)

    paths = write_representative_period_artifacts(result, diagnostics, tmp_path)

    assert set(paths) == {
        "representative_days",
        "representative_hourly",
        "day_mapping",
        "transition_counts",
        "chronology_links",
        "normalization",
        "diagnostics",
        "metadata",
    }
    assert all(path.is_file() for path in paths.values())
    metadata = paths["metadata"].read_text(encoding="utf-8")
    assert '"seed": 99' in metadata
    assert '"weight_days_total": 366' in metadata
