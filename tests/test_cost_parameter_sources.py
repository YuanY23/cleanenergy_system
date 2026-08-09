from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pathlib import Path

from zero_carbon_park.config import StudyConfig
from zero_carbon_park.data.sources import load_assumptions
from zero_carbon_park.planning.cost_params import (
    CarbonFactors,
    NaturalGasTariff,
    get_default_planning_cost_params,
    get_technology_parameter_table,
    mengxi_tou_band,
    mengxi_tou_multiplier,
)


@pytest.mark.parametrize(
    ("timestamp", "band", "multiplier"),
    [
        ("2024-01-01 03:00", "valley", 0.79),
        ("2024-01-01 04:00", "flat", 1.00),
        ("2024-01-01 10:00", "valley", 0.79),
        ("2024-01-01 15:00", "flat", 1.00),
        ("2024-01-01 17:00", "peak", 1.48),
        ("2024-01-01 21:00", "flat", 1.00),
        ("2024-07-01 05:00", "peak", 1.48),
        ("2024-07-01 10:00", "valley", 0.47),
        ("2024-07-01 18:00", "peak", 1.48 * 1.20),
        ("2024-07-01 20:00", "peak", 1.48),
    ],
)
def test_mengxi_tou_boundaries(timestamp: str, band: str, multiplier: float) -> None:
    local = pd.Timestamp(timestamp, tz="Asia/Shanghai")
    assert mengxi_tou_band(local) == band
    assert mengxi_tou_multiplier(local) == pytest.approx(multiplier)


def test_policy_prices_and_carbon_factors_remain_separate() -> None:
    params = get_default_planning_cost_params()
    assert params.grid_transmission_cny_per_kwh == pytest.approx(0.0520)
    assert params.grid_demand_charge_cny_per_kw_month == pytest.approx(31.2)
    assert params.grid_line_loss_rate == pytest.approx(0.0281)
    assert params.natural_gas_price_cny_per_m3 == pytest.approx(2.952)

    carbon = CarbonFactors()
    assert carbon.location_based_kg_per_kwh == pytest.approx(0.6479)
    assert carbon.zero_carbon_method_kg_per_kwh == pytest.approx(0.8325)
    assert carbon.location_source_id != carbon.zero_carbon_source_id


def test_natural_gas_price_rejects_dates_outside_policy_interval() -> None:
    tariff = NaturalGasTariff()
    assert tariff.price_for(date(2026, 8, 9)) == pytest.approx(2.952)
    with pytest.raises(ValueError, match="outside the published applicability"):
        tariff.price_for(date(2026, 11, 1))


def test_cost_ranges_have_complete_provenance_and_valid_bounds() -> None:
    table = get_technology_parameter_table()
    assert table
    for parameter in table:
        assert parameter.source_id
        assert parameter.unit
        assert parameter.low <= parameter.base <= parameter.high
        assert parameter.lifetime_years > 0
        assert parameter.fixed_om_fraction >= 0
        assert parameter.efficiency > 0

    by_technology = {parameter.technology: parameter for parameter in table}
    # International reference costs retain the declared 7.20 CNY/USD base
    # conversion; localisation uncertainty belongs in low/high sensitivity.
    assert by_technology["pv"].base == pytest.approx(691.0 * 7.20)
    assert by_technology["onshore_wind"].base == pytest.approx(1041.0 * 7.20)
    assert by_technology["battery_energy"].base == pytest.approx(192.0 * 7.20)
    assert by_technology["electrolyzer"].base == pytest.approx(900.0 * 7.20)
    assumptions = {
        item.field_name
        for item in load_assumptions(Path("data/metadata/assumptions.yaml"))
    }
    for technology in ("hydrogen_storage", "fuel_cell", "heat_pump"):
        assert by_technology[technology].source_id == "data/metadata/assumptions.yaml"
        assert f"{technology}_capex_cny_per_kw" in assumptions or (
            technology == "hydrogen_storage"
            and "hydrogen_storage_capex_cny_per_kg" in assumptions
        )


def test_capacity_envelope_matches_450_mw_public_scale() -> None:
    study = StudyConfig()
    bounds = study.capacity_bounds
    assert study.park_peak_electric_load_mw == pytest.approx(450.0)
    assert bounds.grid_connection_mw[1] >= 600.0
    assert bounds.wind_mw[1] >= 1500.0
    assert bounds.pv_mw[1] >= 1500.0
