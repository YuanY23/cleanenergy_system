"""多典型日输入数据生成模块。"""

from __future__ import annotations

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.typical_days.definitions import TypicalDayConfig


def generate_typical_day_workbook(
    workbook: InputWorkbook,
    config: TypicalDayConfig,
) -> InputWorkbook:
    """按典型日缩放系数生成新的输入数据对象。

    该函数不会修改原始 workbook，而是复制时间序列和参数表后返回新对象。
    """

    timeseries = workbook.timeseries.copy(deep=True)

    # 按季节假设缩放风光、负荷、价格和排放因子。
    timeseries["pv_available_kw"] = timeseries["pv_available_kw"] * config.pv_scale
    timeseries["wind_available_kw"] = (
        timeseries["wind_available_kw"] * config.wind_scale
    )
    timeseries["electric_load_kw"] = (
        timeseries["electric_load_kw"] * config.electric_load_scale
    )
    timeseries["heat_load_kw"] = (
        timeseries["heat_load_kw"] * config.heat_load_scale
    )
    timeseries["hydrogen_load_kg"] = (
        timeseries["hydrogen_load_kg"] * config.hydrogen_load_scale
    )
    timeseries["electricity_price_cny_per_kwh"] = (
        timeseries["electricity_price_cny_per_kwh"] * config.electricity_price_scale
    )
    timeseries["gas_price_cny_per_m3"] = (
        timeseries["gas_price_cny_per_m3"] * config.gas_price_scale
    )
    timeseries["grid_emission_kgco2_per_kwh"] = (
        timeseries["grid_emission_kgco2_per_kwh"] * config.grid_emission_scale
    )
    timeseries["carbon_price_cny_per_tco2"] = (
        timeseries["carbon_price_cny_per_tco2"] * config.carbon_price_scale
    )

    return InputWorkbook(
        timeseries=timeseries,
        device_params=workbook.device_params.copy(deep=True),
        economic_params=workbook.economic_params.copy(deep=True),
        scenarios=workbook.scenarios.copy(deep=True),
    )
