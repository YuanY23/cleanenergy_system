"""Fresh ERA5-based 8784-hour weather pipeline for the 2024 study year.

ERA5 is the production time series.  NASA POWER is deliberately exposed only
as a separate monthly cross-check so that it can never silently fill or splice
the production series.  All network-facing imports are lazy: unit tests and
downstream users can validate already acquired data without CDS credentials.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml


ERA5_DATASET = "reanalysis-era5-single-levels"
NASA_POWER_HOURLY_URL = (
    "https://power.larc.nasa.gov/api/temporal/hourly/point"
)

ANNUAL_WEATHER_COLUMNS = (
    "timestamp_utc",
    "timestamp_local",
    "wind_speed_100m",
    "solar_irradiance_w_m2",
    "air_temperature_c",
    "pv_cf",
    "wind_cf_uncalibrated",
    "wind_cf_calibrated",
)


class CDSPreflightError(RuntimeError):
    """Raised before any output is written when CDS access is not authorised."""


class AnnualWeatherQualityError(ValueError):
    """Raised when the formal 8784-hour quality gate fails."""


@dataclass(frozen=True)
class AnnualWeatherConfig:
    """Coordinates and transparent conversion assumptions for one study year."""

    year: int = 2024
    latitude: float = 39.61
    longitude: float = 109.78
    timezone_name: str = "Asia/Shanghai"
    pv_tilt_degrees: float = 35.0
    pv_azimuth_degrees: float = 180.0
    pv_system_loss_fraction: float = 0.14
    wind_cut_in_m_s: float = 3.0
    wind_rated_m_s: float = 12.0
    wind_cut_out_m_s: float = 25.0
    wind_calibration_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.year != 2024:
            raise ValueError("the approved formal study year is 2024")
        ZoneInfo(self.timezone_name)
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("latitude or longitude is outside its valid range")
        if not 0 <= self.pv_system_loss_fraction < 1:
            raise ValueError("pv_system_loss_fraction must be in [0, 1)")
        if not (
            0 <= self.wind_cut_in_m_s
            < self.wind_rated_m_s
            < self.wind_cut_out_m_s
        ):
            raise ValueError("wind speeds must satisfy cut-in < rated < cut-out")
        if self.wind_calibration_factor <= 0:
            raise ValueError("wind_calibration_factor must be positive")


@dataclass(frozen=True)
class CDSCredentials:
    url: str
    key: str
    source: str


def preflight_cds_access(
    *,
    terms_accepted: bool,
    environment: Mapping[str, str] | None = None,
    cdsapirc_path: str | Path | None = None,
) -> CDSCredentials:
    """Verify explicit licence acceptance and credentials without writing files."""

    if not terms_accepted:
        raise CDSPreflightError(
            "ERA5 terms must be explicitly accepted with terms_accepted=True"
        )

    env = os.environ if environment is None else environment
    env_url = str(env.get("CDSAPI_URL", "")).strip()
    env_key = str(env.get("CDSAPI_KEY", "")).strip()
    if env_url and env_key:
        return CDSCredentials(env_url, env_key, "environment")

    config_path = (
        Path(cdsapirc_path)
        if cdsapirc_path is not None
        else Path.home() / ".cdsapirc"
    )
    if config_path.is_file():
        try:
            values = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise CDSPreflightError(f"cannot read CDS credentials: {config_path}") from exc
        url = str(values.get("url", "")).strip()
        key = str(values.get("key", "")).strip()
        if url and key:
            return CDSCredentials(url, key, str(config_path))

    raise CDSPreflightError(
        "CDS credentials are missing; configure .cdsapirc or both "
        "CDSAPI_URL and CDSAPI_KEY"
    )


def required_utc_window(config: AnnualWeatherConfig) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the inclusive UTC window covering the local calendar year."""

    local_start = pd.Timestamp(f"{config.year}-01-01 00:00", tz=config.timezone_name)
    local_end = pd.Timestamp(f"{config.year}-12-31 23:00", tz=config.timezone_name)
    return local_start.tz_convert("UTC"), local_end.tz_convert("UTC")


def transform_era5_hourly(
    raw: pd.DataFrame,
    config: AnnualWeatherConfig,
    *,
    pv_converter: Callable[[pd.DataFrame, AnnualWeatherConfig], pd.Series]
    | None = None,
) -> pd.DataFrame:
    """Convert ERA5 native fields and retain exactly the local 2024 leap year."""

    required = {"timestamp_utc", "u100", "v100", "ssrd", "t2m"}
    missing = required - set(raw.columns)
    if missing:
        raise AnnualWeatherQualityError(
            f"ERA5 input missing columns: {', '.join(sorted(missing))}"
        )

    frame = raw.loc[:, list(required)].copy()
    frame["timestamp_utc"] = pd.to_datetime(
        frame["timestamp_utc"], errors="coerce", utc=True
    )
    numeric = ["u100", "v100", "ssrd", "t2m"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    if frame[["timestamp_utc", *numeric]].isna().any().any():
        raise AnnualWeatherQualityError("ERA5 input contains missing or invalid values")
    if (frame[numeric] <= -999).any().any():
        raise AnnualWeatherQualityError("ERA5 input contains -999 sentinel values")
    if frame["timestamp_utc"].duplicated().any():
        raise AnnualWeatherQualityError("ERA5 input contains duplicate timestamps")

    frame = frame.sort_values("timestamp_utc").reset_index(drop=True)
    frame["timestamp_local"] = frame["timestamp_utc"].dt.tz_convert(
        config.timezone_name
    )
    frame = frame.loc[frame["timestamp_local"].dt.year == config.year].copy()
    frame.reset_index(drop=True, inplace=True)

    result = pd.DataFrame(
        {
            "timestamp_utc": frame["timestamp_utc"],
            "timestamp_local": frame["timestamp_local"],
            "wind_speed_100m": np.hypot(frame["u100"], frame["v100"]),
            # ERA5 ssrd is accumulated energy over the hour in J/m2.
            "solar_irradiance_w_m2": frame["ssrd"] / 3600.0,
            "air_temperature_c": frame["t2m"] - 273.15,
        }
    )

    converter = pv_converter or _pvlib_capacity_factor
    pv_cf = converter(result.copy(), config)
    result["pv_cf"] = pd.to_numeric(pv_cf, errors="coerce").to_numpy()
    result["wind_cf_uncalibrated"] = wind_capacity_factor(
        result["wind_speed_100m"],
        cut_in=config.wind_cut_in_m_s,
        rated=config.wind_rated_m_s,
        cut_out=config.wind_cut_out_m_s,
    )
    result["wind_cf_calibrated"] = np.clip(
        result["wind_cf_uncalibrated"] * config.wind_calibration_factor,
        0.0,
        1.0,
    )

    validate_annual_weather(
        result, year=config.year, timezone_name=config.timezone_name
    )
    return result.loc[:, ANNUAL_WEATHER_COLUMNS]


def wind_capacity_factor(
    wind_speed_m_s: pd.Series,
    *,
    cut_in: float = 3.0,
    rated: float = 12.0,
    cut_out: float = 25.0,
) -> pd.Series:
    """Transparent idealised turbine curve with cubic partial-load output."""

    speed = pd.to_numeric(wind_speed_m_s, errors="coerce").astype(float)
    values = np.zeros(len(speed), dtype=float)
    partial = (speed > cut_in) & (speed < rated)
    values[partial.to_numpy()] = (
        (speed[partial].to_numpy() ** 3 - cut_in**3)
        / (rated**3 - cut_in**3)
    )
    rated_region = (speed >= rated) & (speed < cut_out)
    values[rated_region.to_numpy()] = 1.0
    return pd.Series(values, index=speed.index, dtype=float)


def validate_annual_weather(
    data: pd.DataFrame,
    *,
    year: int = 2024,
    timezone_name: str = "Asia/Shanghai",
) -> dict[str, Any]:
    """Apply the publication quality gate and return its report payload."""

    missing_columns = set(ANNUAL_WEATHER_COLUMNS) - set(data.columns)
    if missing_columns:
        raise AnnualWeatherQualityError(
            f"annual weather missing columns: {', '.join(sorted(missing_columns))}"
        )
    expected_hours = 8784 if _is_leap_year(year) else 8760
    if len(data) != expected_hours:
        raise AnnualWeatherQualityError(
            f"annual weather must contain {expected_hours} hours, got {len(data)}"
        )

    frame = data.copy()
    utc = pd.to_datetime(frame["timestamp_utc"], errors="coerce", utc=True)
    local = pd.to_datetime(frame["timestamp_local"], errors="coerce", utc=True).dt.tz_convert(
        timezone_name
    )
    if local.duplicated().any():
        raise AnnualWeatherQualityError("annual weather contains duplicate local timestamps")
    if utc.isna().any() or local.isna().any():
        raise AnnualWeatherQualityError("annual weather contains missing timestamps")

    one_hour = pd.Timedelta(hours=1)
    if not utc.diff().iloc[1:].eq(one_hour).all() or not local.diff().iloc[1:].eq(
        one_hour
    ).all():
        raise AnnualWeatherQualityError("annual timestamps must be continuous hourly values")
    if utc.duplicated().any():
        raise AnnualWeatherQualityError("annual weather contains duplicate UTC timestamps")
    if not utc.dt.tz_convert(timezone_name).reset_index(drop=True).equals(
        local.reset_index(drop=True)
    ):
        raise AnnualWeatherQualityError("UTC and local timestamps are inconsistent")

    expected_start = pd.Timestamp(f"{year}-01-01 00:00", tz=timezone_name)
    expected_end = pd.Timestamp(f"{year}-12-31 23:00", tz=timezone_name)
    if local.iloc[0] != expected_start or local.iloc[-1] != expected_end:
        raise AnnualWeatherQualityError(
            "local timestamps must cover the complete calendar year"
        )

    numeric_columns = [
        column for column in ANNUAL_WEATHER_COLUMNS if not column.startswith("timestamp_")
    ]
    numeric = frame[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise AnnualWeatherQualityError("annual weather contains missing numeric values")
    if (~np.isfinite(numeric.to_numpy())).any():
        raise AnnualWeatherQualityError("annual weather contains non-finite values")
    if (numeric <= -999).any().any():
        raise AnnualWeatherQualityError("annual weather contains -999 sentinel values")

    cf_columns = ["pv_cf", "wind_cf_uncalibrated", "wind_cf_calibrated"]
    if ((numeric[cf_columns] < 0) | (numeric[cf_columns] > 1)).any().any():
        raise AnnualWeatherQualityError("capacity factor must remain within [0, 1]")
    if (numeric["wind_speed_100m"] < 0).any() or (
        numeric["solar_irradiance_w_m2"] < 0
    ).any():
        raise AnnualWeatherQualityError("wind speed and solar irradiance must be non-negative")
    if (numeric["wind_speed_100m"] > 100).any() or (
        numeric["solar_irradiance_w_m2"] > 1600
    ).any() or not numeric["air_temperature_c"].between(-90, 65).all():
        raise AnnualWeatherQualityError("weather values fail physical unit bounds")

    return {
        "status": "passed",
        "row_count": len(frame),
        "utc_start": utc.iloc[0].isoformat(),
        "utc_end": utc.iloc[-1].isoformat(),
        "local_start": local.iloc[0].isoformat(),
        "local_end": local.iloc[-1].isoformat(),
        "duplicate_hours": 0,
        "missing_values": 0,
        "minimum_pv_cf": float(numeric["pv_cf"].min()),
        "maximum_pv_cf": float(numeric["pv_cf"].max()),
        "minimum_wind_cf": float(numeric["wind_cf_calibrated"].min()),
        "maximum_wind_cf": float(numeric["wind_cf_calibrated"].max()),
    }


def build_annual_weather(
    config: AnnualWeatherConfig,
    *,
    raw_dir: str | Path,
    processed_dir: str | Path,
    terms_accepted: bool,
    environment: Mapping[str, str] | None = None,
    cdsapirc_path: str | Path | None = None,
    era5_fetcher: Callable[[AnnualWeatherConfig, CDSCredentials], pd.DataFrame]
    | None = None,
    pv_converter: Callable[[pd.DataFrame, AnnualWeatherConfig], pd.Series]
    | None = None,
) -> dict[str, Path]:
    """Acquire, transform, validate and persist one fresh annual weather run.

    The credential and licence preflight intentionally runs before ``mkdir`` or
    any other write beneath either output directory.
    """

    credentials = preflight_cds_access(
        terms_accepted=terms_accepted,
        environment=environment,
        cdsapirc_path=cdsapirc_path,
    )

    raw_path = Path(raw_dir)
    processed_path = Path(processed_dir)
    raw_path.mkdir(parents=True, exist_ok=True)
    processed_path.mkdir(parents=True, exist_ok=True)

    if era5_fetcher is None:
        raw_file = raw_path / f"era5_ordos_{config.year}_utc.nc"
        download_era5_hourly(config, raw_file, credentials=credentials)
        raw_frame = load_era5_netcdf(raw_file)
    else:
        raw_frame = era5_fetcher(config, credentials)
        raw_file = raw_path / f"era5_ordos_{config.year}_utc.csv"
        raw_frame.to_csv(raw_file, index=False, encoding="utf-8")

    annual = transform_era5_hourly(
        raw_frame, config, pv_converter=pv_converter
    )
    report = validate_annual_weather(
        annual, year=config.year, timezone_name=config.timezone_name
    )

    processed_file = processed_path / f"weather_ordos_{config.year}_8784.csv"
    quality_json = processed_path / f"weather_ordos_{config.year}_quality.json"
    quality_csv = processed_path / f"weather_ordos_{config.year}_quality.csv"
    annual.to_csv(processed_file, index=False, encoding="utf-8")
    quality_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    pd.DataFrame([report]).to_csv(quality_csv, index=False, encoding="utf-8")
    return {
        "raw": raw_file,
        "processed": processed_file,
        "quality_json": quality_json,
        "quality_csv": quality_csv,
    }


def download_era5_hourly(
    config: AnnualWeatherConfig,
    target_path: str | Path,
    *,
    credentials: CDSCredentials,
    client_factory: Callable[..., Any] | None = None,
) -> Path:
    """Download ERA5 with the UTC boundary hours needed by the local year."""

    if client_factory is None:
        try:
            import cdsapi
        except ImportError as exc:  # pragma: no cover - production dependency path
            raise RuntimeError(
                "ERA5 download requires cdsapi; install the declared project dependencies"
            ) from exc
        factory = cdsapi.Client
    else:
        factory = client_factory
    client = factory(url=credentials.url, key=credentials.key, quiet=False)
    start_utc, end_utc = required_utc_window(config)
    first_day = start_utc.date()
    last_day = end_utc.date()
    dates: list[str] = []
    cursor = first_day
    while cursor <= last_day:
        dates.append(cursor.isoformat())
        cursor += timedelta(days=1)

    request = {
        "product_type": ["reanalysis"],
        "variable": [
            "100m_u_component_of_wind",
            "100m_v_component_of_wind",
            "2m_temperature",
            "surface_solar_radiation_downwards",
        ],
        "date": dates,
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": [
            config.latitude + 0.25,
            config.longitude - 0.25,
            config.latitude - 0.25,
            config.longitude + 0.25,
        ],
    }
    target = Path(target_path)
    client.retrieve(ERA5_DATASET, request, str(target))
    return target


def load_era5_netcdf(path: str | Path) -> pd.DataFrame:
    """Reduce the downloaded point box to one hourly site-average table."""

    try:
        import xarray as xr
    except ImportError as exc:  # pragma: no cover - depends on production environment
        raise RuntimeError(
            "ERA5 NetCDF processing requires xarray and netcdf4"
        ) from exc

    with xr.open_dataset(path) as dataset:
        time_name = "valid_time" if "valid_time" in dataset.coords else "time"
        if time_name not in dataset.coords:
            raise AnnualWeatherQualityError("ERA5 NetCDF has no time coordinate")
        variables: dict[str, np.ndarray] = {}
        for name in ("u100", "v100", "ssrd", "t2m"):
            if name not in dataset:
                raise AnnualWeatherQualityError(
                    f"ERA5 NetCDF missing required variable {name}"
                )
            array = dataset[name]
            spatial_dims = [dimension for dimension in array.dims if dimension != time_name]
            if spatial_dims:
                array = array.mean(dim=spatial_dims)
            variables[name] = np.asarray(array.values).reshape(-1)
        timestamps = pd.to_datetime(dataset[time_name].values, utc=True)
    return pd.DataFrame({"timestamp_utc": timestamps, **variables})


def fetch_nasa_power_monthly_check(
    config: AnnualWeatherConfig,
    *,
    session: Any | None = None,
    timeout: float = 60.0,
) -> pd.DataFrame:
    """Fresh NASA POWER monthly QA summary; never returns an hourly model input."""

    if session is None:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - declared production dependency
            raise RuntimeError("NASA POWER check requires requests") from exc
        session = requests.Session()

    params: dict[str, object] = {
        "parameters": "ALLSKY_SFC_SW_DWN,T2M,WS50M",
        "community": "RE",
        "longitude": config.longitude,
        "latitude": config.latitude,
        "start": f"{config.year}0101",
        "end": f"{config.year}1231",
        "format": "JSON",
        "time-standard": "UTC",
    }
    response = session.get(NASA_POWER_HOURLY_URL, params=params, timeout=timeout)
    response.raise_for_status()
    try:
        parameters = response.json()["properties"]["parameter"]
    except (KeyError, TypeError) as exc:
        raise AnnualWeatherQualityError("NASA POWER response schema is invalid") from exc

    series_by_name: dict[str, pd.Series] = {}
    for name in ("ALLSKY_SFC_SW_DWN", "T2M", "WS50M"):
        values = parameters.get(name)
        if not isinstance(values, dict):
            raise AnnualWeatherQualityError(f"NASA POWER response missing {name}")
        series = pd.Series(values, dtype=float)
        series.index = pd.to_datetime(series.index, format="%Y%m%d%H", utc=True)
        series = series.mask(series <= -999)
        series_by_name[name] = series.sort_index()

    solar_daily = series_by_name["ALLSKY_SFC_SW_DWN"].resample("D").sum(min_count=1)
    solar_monthly = solar_daily.resample("MS").mean()
    temperature_monthly = series_by_name["T2M"].resample("MS").mean()
    wind_monthly = series_by_name["WS50M"].resample("MS").mean()
    index = solar_monthly.index.union(temperature_monthly.index).union(wind_monthly.index)
    result = pd.DataFrame(
        {
            "month": index.strftime("%Y-%m"),
            "nasa_solar_kwh_m2_day": solar_monthly.reindex(index).to_numpy(),
            "nasa_temperature_c": temperature_monthly.reindex(index).to_numpy(),
            "nasa_wind_speed_50m_m_s": wind_monthly.reindex(index).to_numpy(),
        }
    )
    if result.iloc[:, 1:].isna().any().any():
        raise AnnualWeatherQualityError("NASA POWER monthly check contains missing values")
    return result


def compare_nasa_power_monthly(
    annual_weather: pd.DataFrame,
    nasa_monthly: pd.DataFrame,
    *,
    year: int = 2024,
    timezone_name: str = "Asia/Shanghai",
) -> pd.DataFrame:
    """Compare ERA5 monthly summaries with the separately acquired NASA data.

    Wind columns retain their source heights in the names because 100 m ERA5
    wind and 50 m NASA wind are a plausibility check, not interchangeable data.
    """

    validate_annual_weather(
        annual_weather, year=year, timezone_name=timezone_name
    )
    required_nasa = {
        "month",
        "nasa_solar_kwh_m2_day",
        "nasa_temperature_c",
        "nasa_wind_speed_50m_m_s",
    }
    missing = required_nasa - set(nasa_monthly.columns)
    if missing:
        raise AnnualWeatherQualityError(
            f"NASA monthly check missing columns: {', '.join(sorted(missing))}"
        )

    frame = annual_weather.copy()
    local = pd.to_datetime(frame["timestamp_local"], utc=True).dt.tz_convert(
        timezone_name
    )
    frame.index = pd.DatetimeIndex(local)
    era5_daily_solar = frame["solar_irradiance_w_m2"].resample("D").sum() / 1000.0
    era5 = pd.DataFrame(
        {
            "month": era5_daily_solar.resample("MS").mean().index.strftime("%Y-%m"),
            "era5_solar_kwh_m2_day": era5_daily_solar.resample("MS").mean().to_numpy(),
            "era5_temperature_c": frame["air_temperature_c"].resample("MS").mean().to_numpy(),
            "era5_wind_speed_100m_m_s": frame["wind_speed_100m"].resample("MS").mean().to_numpy(),
        }
    )
    comparison = era5.merge(nasa_monthly.loc[:, list(required_nasa)], on="month", how="left")
    if comparison[list(required_nasa - {"month"})].isna().any().any():
        raise AnnualWeatherQualityError(
            "NASA monthly check does not cover every ERA5 study month"
        )
    comparison["solar_bias_percent"] = np.where(
        comparison["nasa_solar_kwh_m2_day"].abs() > 1e-12,
        100.0
        * (
            comparison["era5_solar_kwh_m2_day"]
            - comparison["nasa_solar_kwh_m2_day"]
        )
        / comparison["nasa_solar_kwh_m2_day"],
        np.nan,
    )
    comparison["temperature_bias_c"] = (
        comparison["era5_temperature_c"] - comparison["nasa_temperature_c"]
    )
    comparison["wind_speed_height_unadjusted_difference_m_s"] = (
        comparison["era5_wind_speed_100m_m_s"]
        - comparison["nasa_wind_speed_50m_m_s"]
    )
    return comparison


def _pvlib_capacity_factor(
    frame: pd.DataFrame, config: AnnualWeatherConfig
) -> pd.Series:
    try:
        import pvlib
    except ImportError as exc:  # pragma: no cover - explicit dependency failure path
        raise RuntimeError(
            "PV capacity-factor conversion requires pvlib; install the declared "
            "project dependencies or inject pv_converter for a controlled test"
        ) from exc

    times = pd.DatetimeIndex(frame["timestamp_local"])
    location = pvlib.location.Location(
        config.latitude,
        config.longitude,
        tz=config.timezone_name,
        name="Ordos zero-carbon park study point",
    )
    solar_position = location.get_solarposition(times)
    ghi = frame["solar_irradiance_w_m2"].clip(lower=0).to_numpy()
    decomposition = pvlib.irradiance.erbs(
        ghi,
        solar_position["zenith"].to_numpy(),
        times,
    )
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=config.pv_tilt_degrees,
        surface_azimuth=config.pv_azimuth_degrees,
        solar_zenith=solar_position["apparent_zenith"].to_numpy(),
        solar_azimuth=solar_position["azimuth"].to_numpy(),
        dni=np.nan_to_num(decomposition["dni"].to_numpy()),
        ghi=ghi,
        dhi=np.nan_to_num(decomposition["dhi"].to_numpy()),
    )["poa_global"]
    poa = np.nan_to_num(np.asarray(poa), nan=0.0, posinf=0.0, neginf=0.0)
    cell_temperature = pvlib.temperature.faiman(
        poa,
        frame["air_temperature_c"].to_numpy(),
        frame["wind_speed_100m"].to_numpy(),
    )
    dc_power = pvlib.pvsystem.pvwatts_dc(
        poa,
        cell_temperature,
        pdc0=1.0,
        gamma_pdc=-0.004,
    )
    cf = np.clip(
        np.nan_to_num(dc_power) * (1.0 - config.pv_system_loss_fraction), 0.0, 1.0
    )
    return pd.Series(cf, index=frame.index, dtype=float)


def _is_leap_year(year: int) -> bool:
    return date(year, 12, 31).timetuple().tm_yday == 366
