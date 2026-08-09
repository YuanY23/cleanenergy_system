from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import pytest

from zero_carbon_park.data.annual_pipeline import (
    AnnualWeatherConfig,
    AnnualWeatherQualityError,
    CDSCredentials,
    CDSPreflightError,
    build_annual_weather,
    compare_nasa_power_monthly,
    download_era5_hourly,
    fetch_nasa_power_monthly_check,
    load_nasa_power_monthly_check,
    transform_era5_hourly,
    validate_annual_weather,
    wind_capacity_factor,
)


def _raw_era5_utc_frame() -> pd.DataFrame:
    utc = pd.date_range(
        "2023-12-31 16:00",
        "2024-12-31 15:00",
        freq="h",
        tz="UTC",
    )
    return pd.DataFrame(
        {
            "timestamp_utc": utc,
            "u100": np.full(len(utc), 3.0),
            "v100": np.full(len(utc), 4.0),
            "ssrd": np.full(len(utc), 3_600_000.0),
            "t2m": np.full(len(utc), 273.15),
        }
    )


def _pv_converter(frame: pd.DataFrame, _config: AnnualWeatherConfig) -> pd.Series:
    return pd.Series(0.25, index=frame.index, dtype=float)


def test_transform_era5_keeps_exact_local_leap_year_and_converts_units() -> None:
    result = transform_era5_hourly(
        _raw_era5_utc_frame(),
        AnnualWeatherConfig(year=2024, wind_calibration_factor=1.1),
        pv_converter=_pv_converter,
    )

    assert len(result) == 8784
    assert str(result["timestamp_utc"].dt.tz) == "UTC"
    assert str(result["timestamp_local"].dt.tz) == "Asia/Shanghai"
    assert result["timestamp_local"].iloc[0] == pd.Timestamp(
        "2024-01-01 00:00", tz="Asia/Shanghai"
    )
    assert result["timestamp_local"].iloc[-1] == pd.Timestamp(
        "2024-12-31 23:00", tz="Asia/Shanghai"
    )
    assert result["wind_speed_100m"].iloc[0] == pytest.approx(5.0)
    assert result["solar_irradiance_w_m2"].iloc[0] == pytest.approx(1000.0)
    assert result["air_temperature_c"].iloc[0] == pytest.approx(0.0)
    assert result["pv_cf"].iloc[0] == pytest.approx(0.25)
    assert result["wind_cf_calibrated"].iloc[0] == pytest.approx(
        min(result["wind_cf_uncalibrated"].iloc[0] * 1.1, 1.0)
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: frame.drop(index=12), "8784"),
        (
            lambda frame: frame.assign(
                timestamp_local=lambda value: value["timestamp_local"].mask(
                    value.index == 12, value["timestamp_local"].iloc[11]
                )
            ),
            "duplicate",
        ),
        (
            lambda frame: frame.assign(
                solar_irradiance_w_m2=lambda value: value[
                    "solar_irradiance_w_m2"
                ].mask(value.index == 12, -999.0)
            ),
            "sentinel",
        ),
        (
            lambda frame: frame.assign(
                air_temperature_c=lambda value: value["air_temperature_c"].mask(
                    value.index == 12, np.nan
                )
            ),
            "missing",
        ),
        (
            lambda frame: frame.assign(
                pv_cf=lambda value: value["pv_cf"].mask(value.index == 12, 1.01)
            ),
            "capacity factor",
        ),
        (
            lambda frame: frame.assign(
                timestamp_utc=lambda value: value["timestamp_utc"].mask(
                    value.index == 12,
                    value["timestamp_utc"].iloc[12] + pd.Timedelta(hours=2),
                )
            ),
            "continuous",
        ),
    ],
)
def test_quality_gate_rejects_invalid_annual_series(mutate, message: str) -> None:
    valid = transform_era5_hourly(
        _raw_era5_utc_frame(), AnnualWeatherConfig(), pv_converter=_pv_converter
    )

    with pytest.raises(AnnualWeatherQualityError, match=message):
        validate_annual_weather(mutate(valid))


def test_wind_power_curve_has_explainable_cut_in_rated_and_cut_out_regions() -> None:
    cf = wind_capacity_factor(pd.Series([0.0, 2.9, 3.0, 7.5, 12.0, 20.0, 25.0]))

    assert cf.iloc[:3].eq(0.0).all()
    assert 0.0 < cf.iloc[3] < 1.0
    assert cf.iloc[4] == pytest.approx(1.0)
    assert cf.iloc[5] == pytest.approx(1.0)
    assert cf.iloc[6] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("terms_accepted", "environment", "message"),
    [
        (False, {"CDSAPI_URL": "https://cds.example", "CDSAPI_KEY": "abc"}, "terms"),
        (True, {}, "credentials"),
    ],
)
def test_preflight_fails_before_any_raw_or_processed_write(
    tmp_path: Path,
    terms_accepted: bool,
    environment: dict[str, str],
    message: str,
) -> None:
    raw_dir = tmp_path / "data" / "raw"
    processed_dir = tmp_path / "data" / "processed"

    with pytest.raises(CDSPreflightError, match=message):
        build_annual_weather(
            AnnualWeatherConfig(),
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            terms_accepted=terms_accepted,
            environment=environment,
            cdsapirc_path=tmp_path / "absent-cdsapirc",
            era5_fetcher=lambda *_args, **_kwargs: _raw_era5_utc_frame(),
            pv_converter=_pv_converter,
        )

    assert not raw_dir.exists()
    assert not processed_dir.exists()


def test_pipeline_integration_writes_only_fresh_raw_processed_and_quality_files(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "data" / "raw"
    processed_dir = tmp_path / "data" / "processed"

    outputs = build_annual_weather(
        AnnualWeatherConfig(),
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        terms_accepted=True,
        environment={"CDSAPI_URL": "https://cds.example", "CDSAPI_KEY": "abc"},
        cdsapirc_path=tmp_path / "absent-cdsapirc",
        era5_fetcher=lambda *_args, **_kwargs: _raw_era5_utc_frame(),
        pv_converter=_pv_converter,
    )

    assert set(outputs) == {"raw", "processed", "quality_json", "quality_csv"}
    assert all(path.exists() for path in outputs.values())
    annual = pd.read_csv(outputs["processed"])
    assert len(annual) == 8784
    report = json.loads(outputs["quality_json"].read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["row_count"] == 8784
    assert report["local_start"] == "2024-01-01T00:00:00+08:00"
    assert report["local_end"] == "2024-12-31T23:00:00+08:00"


def test_era5_request_includes_utc_days_on_both_local_year_boundaries(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs

        def retrieve(self, dataset: str, request: dict, target: str) -> None:
            captured["dataset"] = dataset
            captured["request"] = request
            captured["target"] = target
            Path(target).write_bytes(b"netcdf-fixture")

    target = tmp_path / "era5.nc"
    download_era5_hourly(
        AnnualWeatherConfig(),
        target,
        credentials=CDSCredentials("https://cds.example", "abc", "test"),
        client_factory=FakeClient,
        chunk_by_month=False,
    )

    request = captured["request"]
    assert request["date"][0] == "2023-12-31"
    assert request["date"][-1] == "2024-12-31"
    assert len(request["date"]) == 367
    assert request["time"][0] == "00:00"
    assert request["time"][-1] == "23:00"
    assert str(captured["target"]).endswith(".part")
    assert target.read_bytes() == b"netcdf-fixture"


def test_era5_download_splits_formal_request_into_monthly_chunks(
    tmp_path: Path,
) -> None:
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def retrieve(self, _dataset: str, request: dict, target: str) -> None:
            requests.append(request)
            Path(target).write_bytes(b"chunk")

    def combine(chunks: list[Path], target: Path) -> None:
        assert len(chunks) == 13
        assert all(path.is_file() for path in chunks)
        target.write_bytes(b"combined-netcdf")

    target = tmp_path / "era5.nc"
    download_era5_hourly(
        AnnualWeatherConfig(),
        target,
        credentials=CDSCredentials("https://cds.example", "abc", "test"),
        client_factory=FakeClient,
        chunk_combiner=combine,
    )

    assert len(requests) == 13
    assert requests[0]["date"] == ["2023-12-31"]
    assert requests[-1]["date"][-1] == "2024-12-31"
    assert max(len(request["date"]) for request in requests) == 31
    assert target.read_bytes() == b"combined-netcdf"


def test_cds_zip_with_instant_and_accumulated_streams_is_normalized(
    tmp_path: Path,
) -> None:
    import xarray as xr

    timestamps = pd.date_range("2024-01-01", periods=2, freq="h")

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def retrieve(self, _dataset: str, _request: dict, target: str) -> None:
            instant = tmp_path / "instant.nc"
            accumulated = tmp_path / "accum.nc"
            xr.Dataset(
                {
                    "u100": ("valid_time", [1.0, 2.0]),
                    "v100": ("valid_time", [3.0, 4.0]),
                    "t2m": ("valid_time", [273.0, 274.0]),
                },
                coords={"valid_time": timestamps},
            ).to_netcdf(instant)
            xr.Dataset(
                {"ssrd": ("valid_time", [0.0, 3600.0])},
                coords={"valid_time": timestamps},
            ).to_netcdf(accumulated)
            with zipfile.ZipFile(target, "w") as bundle:
                bundle.write(instant, "instant.nc")
                bundle.write(accumulated, "accum.nc")

    target = tmp_path / "normalized.nc"
    download_era5_hourly(
        AnnualWeatherConfig(),
        target,
        credentials=CDSCredentials("https://cds.example", "abc", "test"),
        client_factory=FakeClient,
        chunk_by_month=False,
    )

    with xr.open_dataset(target) as dataset:
        assert {"u100", "v100", "t2m", "ssrd"}.issubset(dataset.data_vars)


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "properties": {
                "parameter": {
                    "ALLSKY_SFC_SW_DWN": {
                        "2024010100": 0.0,
                        "2024010112": 2.0,
                        "2024020112": 4.0,
                    },
                    "T2M": {
                        "2024010100": -10.0,
                        "2024010112": -2.0,
                        "2024020112": 1.0,
                    },
                    "WS50M": {
                        "2024010100": 5.0,
                        "2024010112": 7.0,
                        "2024020112": 9.0,
                    },
                }
            }
        }


class _FakeSession:
    def __init__(self) -> None:
        self.last_params: dict[str, object] | None = None

    def get(self, _url: str, *, params: dict[str, object], timeout: float):
        assert timeout > 0
        self.last_params = params
        return _FakeResponse()


def test_nasa_power_is_a_separate_monthly_check_not_an_hourly_merge() -> None:
    session = _FakeSession()

    monthly = fetch_nasa_power_monthly_check(
        AnnualWeatherConfig(), session=session
    )

    assert monthly.columns.tolist() == [
        "month",
        "nasa_solar_kwh_m2_day",
        "nasa_temperature_c",
        "nasa_wind_speed_50m_m_s",
    ]
    assert monthly["month"].tolist() == ["2024-01", "2024-02"]
    assert session.last_params is not None
    assert session.last_params["time-standard"] == "UTC"
    assert session.last_params["start"] == "20240101"
    assert session.last_params["end"] == "20241231"


def test_pinned_nasa_response_can_be_parsed_without_network(tmp_path: Path) -> None:
    raw = tmp_path / "nasa.json"
    raw.write_text(json.dumps(_FakeResponse().json()), encoding="utf-8")

    monthly = load_nasa_power_monthly_check(raw)

    assert list(monthly["month"]) == ["2024-01", "2024-02"]
    assert monthly["nasa_solar_kwh_m2_day"].tolist() == pytest.approx(
        [0.002, 0.004]
    )


def test_monthly_cross_check_keeps_era5_100m_and_nasa_50m_wind_distinct() -> None:
    annual = transform_era5_hourly(
        _raw_era5_utc_frame(), AnnualWeatherConfig(), pv_converter=_pv_converter
    )
    months = pd.date_range("2024-01-01", "2024-12-01", freq="MS").strftime("%Y-%m")
    nasa = pd.DataFrame(
        {
            "month": months,
            "nasa_solar_kwh_m2_day": np.full(12, 24.0),
            "nasa_temperature_c": np.zeros(12),
            "nasa_wind_speed_50m_m_s": np.full(12, 4.0),
        }
    )

    comparison = compare_nasa_power_monthly(annual, nasa)

    assert len(comparison) == 12
    assert comparison["era5_solar_kwh_m2_day"].eq(24.0).all()
    assert comparison["wind_speed_height_unadjusted_difference_m_s"].eq(1.0).all()
