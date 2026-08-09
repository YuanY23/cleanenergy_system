from __future__ import annotations

import pandas as pd
import pytest

from zero_carbon_park.config import LoadReconstructionConfig
from zero_carbon_park.data.generator import generate_annual_loads


def _weather() -> pd.DataFrame:
    local = pd.date_range(
        "2024-01-01 00:00", periods=8784, freq="h", tz="Asia/Shanghai"
    )
    day_of_year = local.dayofyear.to_numpy()
    hour = local.hour.to_numpy()
    temperature = (
        8.0
        + 18.0 * pd.Series(day_of_year).map(lambda day: __import__("math").sin(2 * __import__("math").pi * (day - 105) / 366)).to_numpy()
        + 3.0 * pd.Series(hour).map(lambda value: __import__("math").sin(2 * __import__("math").pi * (value - 8) / 24)).to_numpy()
    )
    return pd.DataFrame(
        {
            "timestamp_local": local,
            "air_temperature_c": temperature,
        }
    )


def test_electric_load_hits_public_scale_and_declared_peak() -> None:
    config = LoadReconstructionConfig()
    result = generate_annual_loads(_weather(), config)

    annual_mwh = result["electric_load_kw"].sum() / 1000.0
    assert annual_mwh == pytest.approx(config.annual_electricity_mwh, rel=0.01)
    assert result["electric_load_kw"].max() == pytest.approx(
        config.peak_electric_load_mw * 1000.0, rel=1e-6
    )
    electric_components = [
        "electric_baseload_kw",
        "electric_workday_kw",
        "electric_shift_kw",
        "electric_temperature_kw",
    ]
    assert result[electric_components].sum(axis=1).equals(
        result["electric_load_kw"]
    )


def test_loads_are_non_negative_and_heat_rises_as_temperature_falls() -> None:
    result = generate_annual_loads(_weather(), LoadReconstructionConfig())

    load_columns = [column for column in result if column.endswith(("_kw", "_kg"))]
    assert result[load_columns].ge(0).all().all()
    cold = result.nsmallest(200, "air_temperature_c")["heat_load_kw"].mean()
    warm = result.nlargest(200, "air_temperature_c")["heat_load_kw"].mean()
    assert cold > warm


def test_hydrogen_daily_target_and_scale_sensitivities_are_configured() -> None:
    config = LoadReconstructionConfig()
    result = generate_annual_loads(_weather(), config)

    assert result["hydrogen_load_kg"].sum() == pytest.approx(
        config.daily_hydrogen_demand_kg * 366.0
    )
    assert config.load_scale_sensitivities == (0.5, 1.0, 1.5)


def test_inconsistent_annual_energy_and_peak_are_rejected() -> None:
    impossible = LoadReconstructionConfig(
        annual_electricity_mwh=5_000_000.0,
        peak_electric_load_mw=450.0,
    )
    with pytest.raises(ValueError, match="annual electric energy"):
        generate_annual_loads(_weather(), impossible)
