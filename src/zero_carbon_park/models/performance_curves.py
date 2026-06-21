"""Helpers for MILP-friendly hourly and piecewise device performance curves."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversionSegment:
    index: int
    width_rate: float
    kwh_per_kg: float


@dataclass(frozen=True)
class CostSegment:
    index: int
    width_rate: float
    cost_cny_per_kwh: float


def conversion_segments(
    params: dict[str, float],
    *,
    prefix: str,
    fallback_kwh_per_kg: float,
) -> list[ConversionSegment]:
    """Return load-rate segments for electrolyzers or fuel cells.

    Expected parameter names:
    ``{prefix}_segment_1_min_rate``, ``{prefix}_segment_1_max_rate`` and
    ``{prefix}_segment_1_kwh_per_kg``.
    """

    segments: list[ConversionSegment] = []
    index = 1
    previous_max_rate = 0.0
    while f"{prefix}_segment_{index}_max_rate" in params:
        max_rate = float(params[f"{prefix}_segment_{index}_max_rate"])
        kwh_per_kg = float(
            params.get(f"{prefix}_segment_{index}_kwh_per_kg", fallback_kwh_per_kg)
        )
        width_rate = max(0.0, max_rate - previous_max_rate)
        if width_rate > 0.0:
            segments.append(
                ConversionSegment(
                    index=index,
                    width_rate=width_rate,
                    kwh_per_kg=kwh_per_kg,
                )
            )
        previous_max_rate = max(previous_max_rate, max_rate)
        index += 1

    if segments:
        return segments

    return [
        ConversionSegment(
            index=1,
            width_rate=1.0,
            kwh_per_kg=float(fallback_kwh_per_kg),
        )
    ]


def battery_degradation_segments(
    params: dict[str, float],
    *,
    fallback_cost_cny_per_kwh: float,
) -> list[CostSegment]:
    """Return piecewise battery throughput degradation cost segments."""

    segments: list[CostSegment] = []
    index = 1
    while f"battery_degradation_segment_{index}_width_rate" in params:
        width_rate = float(params[f"battery_degradation_segment_{index}_width_rate"])
        cost = float(
            params.get(
                f"battery_degradation_segment_{index}_cost_cny_per_kwh",
                fallback_cost_cny_per_kwh,
            )
        )
        if width_rate > 0.0:
            segments.append(
                CostSegment(
                    index=index,
                    width_rate=width_rate,
                    cost_cny_per_kwh=cost,
                )
            )
        index += 1

    if segments:
        return segments

    return [
        CostSegment(
            index=1,
            width_rate=1.0,
            cost_cny_per_kwh=float(fallback_cost_cny_per_kwh),
        )
    ]
