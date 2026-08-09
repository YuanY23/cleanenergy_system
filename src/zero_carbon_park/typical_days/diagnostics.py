"""Reconstruction diagnostics for representative-day compression."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from zero_carbon_park.typical_days.definitions import RepresentativePeriodResult


class CompressionQualityError(ValueError):
    """Raised when a representative-period error threshold is exceeded."""


@dataclass(frozen=True)
class CompressionThresholds:
    annual_energy: float = 0.05
    annual_shape: float = 0.10
    monthly_energy: float = 0.15
    monthly_shape: float = 0.20

    def __post_init__(self) -> None:
        if min(
            self.annual_energy,
            self.annual_shape,
            self.monthly_energy,
            self.monthly_shape,
        ) < 0:
            raise ValueError("compression thresholds cannot be negative")


def reconstruct_hourly(
    annual_timeseries: pd.DataFrame,
    result: RepresentativePeriodResult,
    *,
    timestamp_column: str = "timestamp_local",
) -> pd.DataFrame:
    """Replay representative profiles in the original 366-day chronology."""

    timestamps = pd.to_datetime(annual_timeseries[timestamp_column], errors="coerce")
    keys = pd.DataFrame(
        {
            timestamp_column: timestamps,
            "calendar_date": timestamps.dt.date,
            "hour": timestamps.dt.hour,
        }
    )
    keys = keys.merge(
        result.day_mapping,
        on="calendar_date",
        how="left",
        validate="many_to_one",
    )
    profiles = result.representative_hourly.drop(columns="representative_date")
    reconstructed = keys.merge(
        profiles,
        on=["representative_id", "hour"],
        how="left",
        validate="many_to_one",
    )
    if reconstructed.loc[:, result.feature_columns].isna().any().any():
        raise ValueError("representative profiles cannot reconstruct every calendar hour")
    return reconstructed


def evaluate_compression(
    annual_timeseries: pd.DataFrame,
    result: RepresentativePeriodResult,
    *,
    timestamp_column: str = "timestamp_local",
) -> pd.DataFrame:
    """Report annual and monthly energy, peak and P5/P50/P95 errors."""

    reconstructed = reconstruct_hourly(
        annual_timeseries, result, timestamp_column=timestamp_column
    )
    original = annual_timeseries.copy()
    original["_month"] = pd.to_datetime(original[timestamp_column]).dt.month
    reconstructed["_month"] = reconstructed[timestamp_column].dt.month
    records: list[dict[str, object]] = []
    scopes = [("annual", None), *[("monthly", value) for value in range(1, 13)]]
    for scope, month in scopes:
        if month is None:
            original_scope = original
            reconstructed_scope = reconstructed
        else:
            original_scope = original.loc[original["_month"] == month]
            reconstructed_scope = reconstructed.loc[reconstructed["_month"] == month]
        for column in result.feature_columns:
            actual = original_scope[column].astype(float)
            estimate = reconstructed_scope[column].astype(float)
            values = {
                "energy": (actual.sum(), estimate.sum()),
                "peak": (actual.max(), estimate.max()),
                "p5": (actual.quantile(0.05), estimate.quantile(0.05)),
                "p50": (actual.quantile(0.50), estimate.quantile(0.50)),
                "p95": (actual.quantile(0.95), estimate.quantile(0.95)),
            }
            value_range = max(float(actual.max() - actual.min()), 1e-9)
            for metric, (actual_value, estimate_value) in values.items():
                denominator = max(abs(float(actual_value)), value_range * 1e-9, 1e-9)
                records.append(
                    {
                        "scope": scope,
                        "month": month,
                        "feature": column,
                        "metric": metric,
                        "original_value": float(actual_value),
                        "reconstructed_value": float(estimate_value),
                        "relative_error": abs(float(estimate_value - actual_value))
                        / denominator,
                    }
                )
    return pd.DataFrame.from_records(records)


def validate_compression(
    diagnostics: pd.DataFrame,
    thresholds: CompressionThresholds | None = None,
) -> None:
    """Fail with the exact offending diagnostics when configured gates fail."""

    selected = thresholds or CompressionThresholds()
    metric_is_energy = diagnostics["metric"].eq("energy")
    scope_is_annual = diagnostics["scope"].eq("annual")
    limits = np.select(
        [
            scope_is_annual & metric_is_energy,
            scope_is_annual & ~metric_is_energy,
            ~scope_is_annual & metric_is_energy,
        ],
        [
            selected.annual_energy,
            selected.annual_shape,
            selected.monthly_energy,
        ],
        default=selected.monthly_shape,
    )
    failed = diagnostics.loc[diagnostics["relative_error"].to_numpy() > limits]
    if not failed.empty:
        worst = failed.sort_values("relative_error", ascending=False).iloc[0]
        raise CompressionQualityError(
            "representative-period quality gate failed: "
            f"{worst['scope']} month={worst['month']} feature={worst['feature']} "
            f"metric={worst['metric']} error={worst['relative_error']:.4f}"
        )


__all__ = [
    "CompressionQualityError",
    "CompressionThresholds",
    "evaluate_compression",
    "reconstruct_hourly",
    "validate_compression",
]
