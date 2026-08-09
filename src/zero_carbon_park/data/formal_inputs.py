"""Construct the formal annual model workbook from validated fresh weather."""

from __future__ import annotations

from datetime import date

import pandas as pd

from zero_carbon_park.config import StudyConfig
from zero_carbon_park.data.generator import generate_annual_loads
from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.planning.cost_params import (
    CarbonFactors,
    GridTariff,
    NaturalGasTariff,
    mengxi_tou_band,
)
from zero_carbon_park.typical_days.definitions import (
    RepresentativePeriodResult,
    TypicalDayConfig,
)


NATURAL_GAS_LHV_MJ_PER_M3 = 38.931
NATURAL_GAS_CARBON_CONTENT_T_C_PER_TJ = 15.3
NATURAL_GAS_OXIDATION_RATE = 0.99
NATURAL_GAS_FACTOR_KGCO2_PER_M3 = (
    NATURAL_GAS_LHV_MJ_PER_M3
    * 1.0e-6
    * NATURAL_GAS_CARBON_CONTENT_T_C_PER_TJ
    * NATURAL_GAS_OXIDATION_RATE
    * (44.0 / 12.0)
    * 1_000.0
)
CRITICAL_LOAD_SHARE = 0.30
IMPORTANT_LOAD_SHARE = 0.40
INTERRUPTIBLE_LOAD_SHARE = 0.30


def build_annual_model_workbook(
    weather: pd.DataFrame,
    *,
    study: StudyConfig | None = None,
    grid_tariff: GridTariff | None = None,
    gas_tariff: NaturalGasTariff | None = None,
    gas_price_date: date = date(2026, 8, 9),
    carbon_factors: CarbonFactors | None = None,
) -> InputWorkbook:
    """Build all model columns without reading the historical Excel workbook."""

    selected_study = study or StudyConfig()
    selected_grid = grid_tariff or GridTariff()
    selected_gas = gas_tariff or NaturalGasTariff()
    selected_carbon = carbon_factors or CarbonFactors()
    loads = generate_annual_loads(weather, selected_study.load)
    weather_frame = weather.copy()
    weather_frame["timestamp_local"] = pd.to_datetime(
        weather_frame["timestamp_local"], errors="raise"
    )
    columns = [
        "timestamp_local",
        "pv_cf",
        "wind_cf_calibrated",
        "air_temperature_c",
    ]
    missing = set(columns) - set(weather_frame.columns)
    if missing:
        raise ValueError(f"formal weather missing columns: {sorted(missing)}")
    timeseries = weather_frame.loc[:, columns].merge(
        loads.drop(columns="air_temperature_c"),
        on="timestamp_local",
        how="inner",
        validate="one_to_one",
    )
    if len(timeseries) != selected_study.expected_hours:
        raise ValueError("formal model input must retain all 8784 weather hours")
    timeseries.insert(0, "hour", range(len(timeseries)))
    timeseries["wind_cf"] = timeseries["wind_cf_calibrated"]
    timeseries["critical_load_kw"] = (
        timeseries["electric_load_kw"] * CRITICAL_LOAD_SHARE
    )
    timeseries["important_load_kw"] = (
        timeseries["electric_load_kw"] * IMPORTANT_LOAD_SHARE
    )
    timeseries["interruptible_load_kw"] = (
        timeseries["electric_load_kw"] * INTERRUPTIBLE_LOAD_SHARE
    )
    timeseries["tou_period"] = timeseries["timestamp_local"].map(
        mengxi_tou_band
    )
    timeseries["electricity_price_cny_per_kwh"] = timeseries[
        "timestamp_local"
    ].map(selected_grid.hourly_energy_price)
    timeseries["grid_sell_price_cny_per_kwh"] = 0.0
    timeseries["gas_price_cny_per_m3"] = selected_gas.price_for(gas_price_date)
    timeseries["grid_emission_kgco2_per_kwh"] = (
        selected_carbon.location_based_kg_per_kwh
    )
    timeseries["carbon_price_cny_per_tco2"] = 0.0

    return InputWorkbook(
        timeseries=timeseries,
        device_params=_parameter_frame(
            {
                "heat_pump_COP": 3.0,
                "gas_boiler_heat_kW": 300_000.0,
                "gas_boiler_eff": 0.90,
                "gas_lhv_kwh_per_m3": NATURAL_GAS_LHV_MJ_PER_M3 / 3.6,
                "battery_eta_ch": 0.95,
                "battery_eta_dis": 0.95,
                "electrolyzer_kWh_per_kgH2": 55.0,
                "fuel_cell_kWh_per_kgH2": 18.0,
                "electrolyzer_min_load_rate": 0.10,
                "fuel_cell_min_load_rate": 0.10,
                "h2_storage_loss_rate_per_hour": 0.0001,
                "h2_storage_charge_rate_per_hour": 1.0,
                "h2_storage_discharge_rate_per_hour": 1.0,
                "electrolyzer_ramp_rate_per_hour": 0.50,
                "fuel_cell_ramp_rate_per_hour": 0.50,
            }
        ),
        economic_params=_parameter_frame(
            {
                "gas_emission_factor": NATURAL_GAS_FACTOR_KGCO2_PER_M3,
                "curtail_penalty": 0.01,
                "battery_om": 0.01,
                "electrolyzer_om": 0.02,
                "fuel_cell_om": 0.03,
                "h2_external_supply_cost": 1000.0,
                "critical_load_shed_penalty_cny_per_kwh": 100_000.0,
                "important_load_shed_penalty_cny_per_kwh": 10_000.0,
                "interruptible_load_shed_penalty_cny_per_kwh": 1_000.0,
                "hydrogen_unserved_penalty_cny_per_kg": 100_000.0,
            }
        ),
        scenarios=pd.DataFrame(),
    )


def build_representative_workbooks(
    annual_workbook: InputWorkbook,
    result: RepresentativePeriodResult,
) -> list[tuple[TypicalDayConfig, InputWorkbook]]:
    """Slice full model columns for each selected real representative date."""

    timestamps = pd.to_datetime(
        annual_workbook.timeseries["timestamp_local"], errors="raise"
    )
    workbooks: list[tuple[TypicalDayConfig, InputWorkbook]] = []
    for row in result.representative_days.itertuples(index=False):
        selected = annual_workbook.timeseries.loc[
            timestamps.dt.date == row.representative_date
        ].reset_index(drop=True)
        if len(selected) != 24:
            raise ValueError(f"representative date is incomplete: {row.representative_date}")
        config = TypicalDayConfig(
            day_id=str(row.representative_id),
            name=f"真实代表日 {row.representative_date}",
            weight_days=int(row.weight_days),
            pv_scale=1.0,
            wind_scale=1.0,
            electric_load_scale=1.0,
            heat_load_scale=1.0,
            hydrogen_load_scale=1.0,
            electricity_price_scale=1.0,
            gas_price_scale=1.0,
            grid_emission_scale=1.0,
            carbon_price_scale=1.0,
        )
        workbooks.append(
            (
                config,
                InputWorkbook(
                    timeseries=selected,
                    device_params=annual_workbook.device_params,
                    economic_params=annual_workbook.economic_params,
                    scenarios=annual_workbook.scenarios,
                ),
            )
        )
    return workbooks


def capacity_upper_bounds_kw(study: StudyConfig | None = None) -> dict[str, float]:
    selected = study or StudyConfig()
    bounds = selected.capacity_bounds
    return {
        "wind_capacity_kw": bounds.wind_mw[1] * 1000.0,
        "pv_capacity_kw": bounds.pv_mw[1] * 1000.0,
        "battery_power_capacity_kw": bounds.battery_power_mw[1] * 1000.0,
        "battery_energy_capacity_kwh": bounds.battery_energy_mwh[1] * 1000.0,
        "electrolyzer_power_capacity_kw": bounds.electrolyzer_mw[1] * 1000.0,
        "h2_storage_capacity_kg": bounds.hydrogen_storage_kg[1],
        "fuel_cell_power_capacity_kw": bounds.fuel_cell_mw[1] * 1000.0,
        "heat_pump_power_capacity_kw": bounds.heat_pump_mw[1] * 1000.0,
    }


def _parameter_frame(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"parameter": name, "value": value} for name, value in values.items()]
    )


__all__ = [
    "NATURAL_GAS_CARBON_CONTENT_T_C_PER_TJ",
    "NATURAL_GAS_FACTOR_KGCO2_PER_M3",
    "NATURAL_GAS_LHV_MJ_PER_M3",
    "NATURAL_GAS_OXIDATION_RATE",
    "build_annual_model_workbook",
    "build_representative_workbooks",
    "capacity_upper_bounds_kw",
]
