"""Auditable annual industrial-park load reconstruction.

The generated profiles are an engineering scenario calibrated to public park-
scale evidence.  They are deliberately decomposed and must not be described as
measured SCADA data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from zero_carbon_park.config import LoadReconstructionConfig


LOAD_OUTPUT_COLUMNS = (
    "timestamp_local",
    "air_temperature_c",
    "electric_baseload_kw",
    "electric_workday_kw",
    "electric_shift_kw",
    "electric_temperature_kw",
    "electric_load_kw",
    "heat_process_kw",
    "heat_space_heating_kw",
    "heat_load_kw",
    "hydrogen_continuous_kg",
    "hydrogen_interruptible_kg",
    "hydrogen_load_kg",
)


def generate_annual_loads(
    weather: pd.DataFrame,
    config: LoadReconstructionConfig | None = None,
) -> pd.DataFrame:
    """Build electric, heat and hydrogen hourly loads for a complete local year.

    Electric demand combines a constant industrial base, weekday effect, shift
    schedule and heating/cooling response.  Heat demand combines process heat
    and heating-degree hours.  Hydrogen combines a continuous process and a
    daily interruptible production task.  Electric and heat components are
    jointly calibrated to both annual energy and a declared peak.
    """

    selected = config or LoadReconstructionConfig()
    frame = _validated_weather(weather)
    local = frame["timestamp_local"]
    temperature = frame["air_temperature_c"].astype(float)

    workday = (local.dt.dayofweek < 5).astype(float)
    hour = local.dt.hour
    shift = np.select(
        [(hour >= 8) & (hour < 17), (hour >= 17) & (hour < 24)],
        [1.0, 0.55],
        default=0.18,
    )
    heating = np.maximum(selected.heating_balance_temperature_c - temperature, 0.0)
    cooling = np.maximum(temperature - selected.cooling_balance_temperature_c, 0.0)
    temperature_driver = heating / max(float(heating.max()), 1.0) + 0.55 * (
        cooling / max(float(cooling.max()), 1.0)
    )

    electric = _calibrate_additive_components(
        {
            "electric_workday_kw": 0.10 * workday.to_numpy(),
            "electric_shift_kw": 0.24 * np.asarray(shift, dtype=float),
            "electric_temperature_kw": 0.10 * np.asarray(temperature_driver, dtype=float),
        },
        annual_energy_mwh=selected.annual_electricity_mwh,
        peak_mw=selected.peak_electric_load_mw,
        base_name="electric_baseload_kw",
        label="annual electric energy",
    )

    heating_driver = heating.to_numpy(dtype=float, copy=True)
    heating_driver /= max(float(heating_driver.max()), 1.0)
    heat = _calibrate_additive_components(
        {"heat_space_heating_kw": heating_driver},
        annual_energy_mwh=selected.annual_heat_energy_mwh,
        peak_mw=selected.peak_heat_load_mw_th,
        base_name="heat_process_kw",
        label="annual heat energy",
    )

    continuous_hourly = (
        selected.daily_hydrogen_demand_kg
        * (1.0 - selected.hydrogen_interruptible_share)
        / 24.0
    )
    task_hours = (hour >= 10) & (hour < 18)
    task_hourly = (
        selected.daily_hydrogen_demand_kg
        * selected.hydrogen_interruptible_share
        / float(task_hours.groupby(local.dt.normalize()).transform("sum").iloc[0])
    )

    result = frame.copy()
    for name, values in electric.items():
        result[name] = values
    result["electric_load_kw"] = result[list(electric)].sum(axis=1)
    for name, values in heat.items():
        result[name] = values
    result["heat_load_kw"] = result[list(heat)].sum(axis=1)
    result["hydrogen_continuous_kg"] = continuous_hourly
    result["hydrogen_interruptible_kg"] = np.where(task_hours, task_hourly, 0.0)
    result["hydrogen_load_kg"] = (
        result["hydrogen_continuous_kg"] + result["hydrogen_interruptible_kg"]
    )

    numeric = result.drop(columns=["timestamp_local"])
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("load reconstruction produced missing or non-finite values")
    nonnegative = numeric.drop(columns=["air_temperature_c"])
    if (nonnegative < -1e-9).any().any():
        raise ValueError("load reconstruction produced negative values")
    return result.loc[:, LOAD_OUTPUT_COLUMNS]


def _validated_weather(weather: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp_local", "air_temperature_c"}
    missing = required - set(weather.columns)
    if missing:
        raise ValueError(f"weather input missing columns: {', '.join(sorted(missing))}")
    frame = weather.loc[:, ["timestamp_local", "air_temperature_c"]].copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"], errors="coerce")
    frame["air_temperature_c"] = pd.to_numeric(
        frame["air_temperature_c"], errors="coerce"
    )
    if frame.isna().any().any():
        raise ValueError("weather input contains invalid values")
    if len(frame) not in (8760, 8784):
        raise ValueError("load reconstruction requires a complete 8760/8784-hour year")
    if frame["timestamp_local"].duplicated().any():
        raise ValueError("weather input contains duplicate local timestamps")
    if not frame["timestamp_local"].diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
        raise ValueError("weather input timestamps must be continuous hourly values")
    return frame.reset_index(drop=True)


def _calibrate_additive_components(
    variable_components: dict[str, np.ndarray],
    *,
    annual_energy_mwh: float,
    peak_mw: float,
    base_name: str,
    label: str,
) -> dict[str, np.ndarray]:
    hours = len(next(iter(variable_components.values())))
    average_kw = annual_energy_mwh * 1000.0 / hours
    peak_kw = peak_mw * 1000.0
    if average_kw > peak_kw:
        raise ValueError(f"{label} exceeds the declared peak capacity")

    variable_total = sum(variable_components.values(), start=np.zeros(hours))
    mean_driver = float(variable_total.mean())
    max_driver = float(variable_total.max())
    if max_driver <= mean_driver:
        raise ValueError(f"{label} profile has no calibratable peak variation")
    multiplier = (peak_kw - average_kw) / (max_driver - mean_driver)
    base_kw = average_kw - multiplier * mean_driver
    if base_kw < -1e-9:
        raise ValueError(
            f"{label} and peak imply an infeasible load factor for this shape"
        )
    calibrated = {base_name: np.full(hours, max(base_kw, 0.0))}
    calibrated.update(
        {name: multiplier * np.asarray(values) for name, values in variable_components.items()}
    )
    return calibrated
