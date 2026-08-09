"""Deterministic representative-day compression for the 2024 leap year.

All representatives are medoids: an actual dated day from the formal hourly
series.  Four operational extremes are fixed into the medoid set, while the
remaining dates are selected with a deterministic k-medoids refinement.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from zero_carbon_park.typical_days.definitions import (
    RepresentativePeriodConfig,
    RepresentativePeriodResult,
)


EXTREME_KINDS = (
    "electric_peak",
    "heat_peak",
    "low_renewable",
    "joint_stress",
)


def build_representative_periods(
    annual_timeseries: pd.DataFrame,
    config: RepresentativePeriodConfig | None = None,
) -> RepresentativePeriodResult:
    """Compress timezone-aware 2024 hourly data into 8, 12 or 16 real days."""

    selected = config or RepresentativePeriodConfig()
    frame = _validate_annual_frame(
        annual_timeseries, timestamp_column=selected.timestamp_column
    )
    feature_columns = _resolve_feature_columns(frame, selected.feature_columns)
    dates, normalized_matrix, normalization = _daily_feature_matrix(
        frame, feature_columns, timestamp_column=selected.timestamp_column
    )
    distance = _pairwise_squared_distance(normalized_matrix)
    extreme_days = _identify_extreme_days(
        frame, timestamp_column=selected.timestamp_column
    )
    date_to_index = {day: index for index, day in enumerate(dates)}
    fixed_indices = list(
        dict.fromkeys(date_to_index[day] for day in extreme_days.values())
    )
    medoids, labels = _fit_k_medoids(
        distance,
        k=selected.k,
        fixed_indices=fixed_indices,
        seed=selected.seed,
        max_iterations=selected.max_iterations,
    )

    # Stable, human-auditable identifiers follow calendar order.
    medoids = np.asarray(sorted(medoids, key=lambda index: dates[index]), dtype=int)
    labels = _assign_with_nonempty_medoids(distance, medoids)
    representative_ids = [f"RP{number:02d}" for number in range(1, selected.k + 1)]
    representative_date_by_id = {
        representative_ids[position]: dates[index]
        for position, index in enumerate(medoids)
    }
    id_by_position = np.asarray(representative_ids, dtype=object)
    assigned_ids = id_by_position[labels]
    assigned_dates = np.asarray(
        [representative_date_by_id[rep_id] for rep_id in assigned_ids], dtype=object
    )

    day_mapping = pd.DataFrame(
        {
            "calendar_date": dates,
            "representative_id": assigned_ids,
            "representative_date": assigned_dates,
        }
    )
    weights = day_mapping["representative_id"].value_counts()
    extreme_by_date: dict[object, list[str]] = {}
    for kind, day in extreme_days.items():
        extreme_by_date.setdefault(day, []).append(kind)
    representative_days = pd.DataFrame(
        {
            "representative_id": representative_ids,
            "representative_date": [
                representative_date_by_id[rep_id] for rep_id in representative_ids
            ],
            "weight_days": [int(weights.get(rep_id, 0)) for rep_id in representative_ids],
            "is_forced_extreme": [
                representative_date_by_id[rep_id] in extreme_by_date
                for rep_id in representative_ids
            ],
            "extreme_kinds": [
                tuple(extreme_by_date.get(representative_date_by_id[rep_id], ()))
                for rep_id in representative_ids
            ],
        }
    )
    representative_hourly = _representative_hourly_profiles(
        frame,
        representative_days,
        feature_columns,
        timestamp_column=selected.timestamp_column,
    )
    chronology_links, transition_counts = _build_chronology(
        day_mapping,
        representative_ids,
        include_year_wrap=selected.include_year_wrap,
    )

    if int(representative_days["weight_days"].sum()) != 366:
        raise RuntimeError("representative-day weights do not sum to 366")
    return RepresentativePeriodResult(
        representative_days=representative_days,
        representative_hourly=representative_hourly,
        day_mapping=day_mapping,
        transition_counts=transition_counts,
        chronology_links=chronology_links,
        normalization=normalization,
        extreme_days=extreme_days,
        feature_columns=feature_columns,
        seed=selected.seed,
        k=selected.k,
    )


def _validate_annual_frame(
    annual_timeseries: pd.DataFrame,
    *,
    timestamp_column: str,
) -> pd.DataFrame:
    if timestamp_column not in annual_timeseries:
        raise ValueError(f"missing timestamp column: {timestamp_column}")
    frame = annual_timeseries.copy(deep=True)
    timestamps = pd.to_datetime(frame[timestamp_column], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("timestamp column contains invalid values")
    if timestamps.dt.tz is None:
        raise ValueError("2024 timestamps must be timezone-aware")
    if len(frame) != 8784:
        raise ValueError("formal representative periods require exactly 8784 hours")
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("timestamps must be unique and monotonically increasing")
    if set(timestamps.dt.year.unique()) != {2024}:
        raise ValueError("formal representative periods require local calendar year 2024")
    expected = pd.date_range(
        timestamps.iloc[0], timestamps.iloc[-1], freq="h", tz=timestamps.dt.tz
    )
    if len(expected) != 8784 or not np.array_equal(
        timestamps.astype("int64").to_numpy(), expected.astype("int64").to_numpy()
    ):
        raise ValueError("2024 timestamps must be a contiguous hourly series")
    if timestamps.iloc[0].month != 1 or timestamps.iloc[0].day != 1:
        raise ValueError("hourly series must start on local 2024-01-01")
    if timestamps.iloc[-1].month != 12 or timestamps.iloc[-1].day != 31:
        raise ValueError("hourly series must end on local 2024-12-31")
    frame[timestamp_column] = timestamps
    return frame


def _resolve_feature_columns(
    frame: pd.DataFrame,
    requested: Sequence[str] | None,
) -> tuple[str, ...]:
    if requested is not None:
        columns = tuple(requested)
    else:
        pv_column = "pv_cf" if "pv_cf" in frame else "pv_available_kw"
        if "wind_cf_calibrated" in frame:
            wind_column = "wind_cf_calibrated"
        elif "wind_cf" in frame:
            wind_column = "wind_cf"
        else:
            wind_column = "wind_available_kw"
        columns = (
            "electric_load_kw",
            "heat_load_kw",
            "hydrogen_load_kg",
            pv_column,
            wind_column,
        )
        if "electricity_price_cny_per_kwh" in frame:
            columns = (*columns, "electricity_price_cny_per_kwh")
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ValueError(f"representative-day features are missing: {missing}")
    numeric = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("representative-day features contain invalid values")
    return columns


def _daily_feature_matrix(
    frame: pd.DataFrame,
    feature_columns: tuple[str, ...],
    *,
    timestamp_column: str,
) -> tuple[list[object], np.ndarray, pd.DataFrame]:
    values = frame.loc[:, feature_columns].astype(float)
    means = values.mean(axis=0)
    scales = values.std(axis=0, ddof=0).replace(0.0, 1.0)
    standardized = (values - means) / scales
    dates = frame[timestamp_column].dt.date
    if dates.nunique() != 366 or not (dates.value_counts() == 24).all():
        raise ValueError("2024 data must contain 366 complete local days")
    ordered_dates = dates.iloc[::24].tolist()
    normalized_matrix = (
        standardized.to_numpy()
        .reshape(366, 24, len(feature_columns))
        .transpose(0, 2, 1)
        .reshape(366, -1)
    )
    normalization = pd.DataFrame(
        {
            "feature": feature_columns,
            "mean": [float(means[column]) for column in feature_columns],
            "scale": [float(scales[column]) for column in feature_columns],
        }
    )
    return ordered_dates, normalized_matrix, normalization


def _identify_extreme_days(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
) -> dict[str, object]:
    dated = frame.assign(_date=frame[timestamp_column].dt.date)
    electric_peak = dated.loc[dated["electric_load_kw"].idxmax(), "_date"]
    heat_peak = dated.loc[dated["heat_load_kw"].idxmax(), "_date"]
    pv_column = "pv_cf" if "pv_cf" in dated else "pv_available_kw"
    if "wind_cf_calibrated" in dated:
        wind_column = "wind_cf_calibrated"
    elif "wind_cf" in dated:
        wind_column = "wind_cf"
    else:
        wind_column = "wind_available_kw"

    daily = dated.groupby("_date", sort=True).agg(
        electric=("electric_load_kw", "sum"),
        heat=("heat_load_kw", "sum"),
        hydrogen=("hydrogen_load_kg", "sum"),
        pv=(pv_column, "sum"),
        wind=(wind_column, "sum"),
    )
    renewable_scale = daily[["pv", "wind"]].max(axis=0).replace(0.0, 1.0)
    renewable_score = (daily[["pv", "wind"]] / renewable_scale).sum(axis=1)
    low_renewable = renewable_score.idxmin()
    standardized = (daily - daily.mean()) / daily.std(ddof=0).replace(0.0, 1.0)
    joint_score = (
        standardized["electric"]
        + standardized["heat"]
        + standardized["hydrogen"]
        - standardized["pv"]
        - standardized["wind"]
    )
    joint_stress = joint_score.idxmax()
    return {
        "electric_peak": electric_peak,
        "heat_peak": heat_peak,
        "low_renewable": low_renewable,
        "joint_stress": joint_stress,
    }


def _pairwise_squared_distance(matrix: np.ndarray) -> np.ndarray:
    squared_norm = np.sum(matrix * matrix, axis=1)
    distance = squared_norm[:, None] + squared_norm[None, :] - 2 * matrix @ matrix.T
    return np.maximum(distance, 0.0)


def _fit_k_medoids(
    distance: np.ndarray,
    *,
    k: int,
    fixed_indices: list[int],
    seed: int,
    max_iterations: int,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    medoids = list(dict.fromkeys(fixed_indices))
    candidate_order = rng.permutation(len(distance))
    while len(medoids) < k:
        if medoids:
            nearest = distance[:, medoids].min(axis=1)
            nearest[np.asarray(medoids, dtype=int)] = -1.0
            best_distance = nearest.max()
            tied = set(np.flatnonzero(np.isclose(nearest, best_distance)).tolist())
            next_index = next(
                int(index) for index in candidate_order if int(index) in tied
            )
        else:
            next_index = int(candidate_order[0])
        medoids.append(next_index)

    fixed = set(fixed_indices)
    medoid_array = np.asarray(medoids, dtype=int)
    for _ in range(max_iterations):
        labels = _assign_with_nonempty_medoids(distance, medoid_array)
        changed = medoid_array.copy()
        for position, current in enumerate(medoid_array):
            if int(current) in fixed:
                continue
            members = np.flatnonzero(labels == position)
            within_cost = distance[np.ix_(members, members)].sum(axis=1)
            best_cost = within_cost.min()
            tied_members = members[np.isclose(within_cost, best_cost)]
            changed[position] = int(tied_members.min())
        if np.array_equal(changed, medoid_array):
            break
        medoid_array = changed
    return medoid_array, _assign_with_nonempty_medoids(distance, medoid_array)


def _assign_with_nonempty_medoids(
    distance: np.ndarray, medoids: np.ndarray
) -> np.ndarray:
    labels = np.argmin(distance[:, medoids], axis=1)
    # Equal profiles can occur on several dates.  Retain every selected date as
    # its own occurrence so every requested representative has positive weight.
    for position, medoid in enumerate(medoids):
        labels[int(medoid)] = position
    return labels


def _representative_hourly_profiles(
    frame: pd.DataFrame,
    representative_days: pd.DataFrame,
    feature_columns: tuple[str, ...],
    *,
    timestamp_column: str,
) -> pd.DataFrame:
    dated = frame.assign(
        representative_date=frame[timestamp_column].dt.date,
        hour=frame[timestamp_column].dt.hour,
    )
    metadata = representative_days.loc[
        :, ["representative_id", "representative_date"]
    ]
    profiles = metadata.merge(
        dated.loc[:, ["representative_date", "hour", *feature_columns]],
        on="representative_date",
        how="left",
        validate="one_to_many",
    )
    if len(profiles) != len(representative_days) * 24:
        raise RuntimeError("each representative date must retain exactly 24 hours")
    return profiles


def _build_chronology(
    day_mapping: pd.DataFrame,
    representative_ids: list[str],
    *,
    include_year_wrap: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    final_index = len(day_mapping) if include_year_wrap else len(day_mapping) - 1
    records: list[dict[str, object]] = []
    for occurrence in range(final_index):
        next_occurrence = (occurrence + 1) % len(day_mapping)
        current = day_mapping.iloc[occurrence]
        following = day_mapping.iloc[next_occurrence]
        records.append(
            {
                "occurrence_index": occurrence,
                "from_calendar_date": current["calendar_date"],
                "to_calendar_date": following["calendar_date"],
                "from_representative_id": current["representative_id"],
                "to_representative_id": following["representative_id"],
                "is_year_wrap": next_occurrence == 0,
            }
        )
    links = pd.DataFrame.from_records(records)
    counts = pd.crosstab(
        links["from_representative_id"], links["to_representative_id"]
    ).reindex(index=representative_ids, columns=representative_ids, fill_value=0)
    counts.index.name = "from_representative_id"
    counts.columns.name = "to_representative_id"
    return links, counts.astype(int)


__all__ = [
    "EXTREME_KINDS",
    "RepresentativePeriodConfig",
    "RepresentativePeriodResult",
    "build_representative_periods",
]
