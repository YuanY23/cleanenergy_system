from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from zero_carbon_park.data.formal_inputs import (
    build_annual_model_workbook,
    capacity_upper_bounds_kw,
)


def _weather() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2024-01-01", periods=8784, freq="h", tz="Asia/Shanghai"
    )
    phase = np.arange(8784) * 2 * np.pi / 8784
    return pd.DataFrame(
        {
            "timestamp_local": timestamps,
            "pv_cf": np.clip(np.sin(np.arange(8784) % 24 / 24 * np.pi), 0, 1),
            "wind_cf_calibrated": 0.4 + 0.1 * np.sin(phase),
            "air_temperature_c": 8.0 + 20.0 * np.sin(phase),
        }
    )


def test_formal_inputs_are_8784_hour_source_independent_model_data() -> None:
    workbook = build_annual_model_workbook(_weather())
    timeseries = workbook.timeseries

    assert len(timeseries) == 8784
    assert timeseries["hour"].tolist() == list(range(8784))
    assert timeseries["electric_load_kw"].sum() / 1000 == pytest.approx(3_100_000.0)
    assert timeseries["electric_load_kw"].max() / 1000 == pytest.approx(450.0)
    assert timeseries["heat_load_kw"].sum() / 1000 == pytest.approx(1_150_000.0)
    assert timeseries["heat_load_kw"].max() / 1000 == pytest.approx(270.0)
    tier_sum = timeseries[
        ["critical_load_kw", "important_load_kw", "interruptible_load_kw"]
    ].sum(axis=1)
    assert np.allclose(tier_sum, timeseries["electric_load_kw"])
    assert timeseries["electricity_price_cny_per_kwh"].nunique() > 3
    assert not workbook.device_params.empty
    assert not workbook.economic_params.empty


def test_capacity_bounds_match_the_park_scale_configuration() -> None:
    bounds = capacity_upper_bounds_kw()
    assert bounds["wind_capacity_kw"] == 1_500_000.0
    assert bounds["battery_energy_capacity_kwh"] == 4_800_000.0
    assert bounds["h2_storage_capacity_kg"] == 3_000_000.0
