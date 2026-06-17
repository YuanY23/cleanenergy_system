"""不确定性场景输入数据生成。"""

from __future__ import annotations

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.uncertainty.definitions import UncertaintyCase


def generate_uncertainty_workbook(
    workbook: InputWorkbook,
    case: UncertaintyCase,
) -> InputWorkbook:
    """按不确定性场景缩放输入数据，不修改原始 workbook。"""

    timeseries = workbook.timeseries.copy(deep=True)

    for column in ["pv_available_kw", "pv_cf"]:
        if column in timeseries:
            timeseries[column] = timeseries[column] * case.pv_scale
    for column in ["wind_available_kw", "wind_cf"]:
        if column in timeseries:
            timeseries[column] = timeseries[column] * case.wind_scale

    timeseries["electric_load_kw"] = (
        timeseries["electric_load_kw"] * case.electric_load_scale
    )
    timeseries["heat_load_kw"] = timeseries["heat_load_kw"] * case.heat_load_scale
    timeseries["hydrogen_load_kg"] = (
        timeseries["hydrogen_load_kg"] * case.hydrogen_load_scale
    )

    return InputWorkbook(
        timeseries=timeseries,
        device_params=workbook.device_params.copy(deep=True),
        economic_params=workbook.economic_params.copy(deep=True),
        scenarios=workbook.scenarios.copy(deep=True),
    )

