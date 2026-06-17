from pathlib import Path

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_default_typical_days_match_v2_plan():
    typical_days = get_default_typical_days()

    assert [day.day_id for day in typical_days] == [
        "TD_SUMMER",
        "TD_WINTER",
        "TD_TRANSITION",
    ]
    assert sum(day.weight_days for day in typical_days) == 365


def test_generate_typical_day_workbook_keeps_24_hours_and_original_unchanged():
    workbook = load_input_workbook(_workbook_path())
    original_timeseries = workbook.timeseries.copy(deep=True)

    for config in get_default_typical_days():
        changed = generate_typical_day_workbook(workbook, config)

        assert len(changed.timeseries) == 24
        assert changed.device_params.equals(workbook.device_params)
        assert changed.economic_params.equals(workbook.economic_params)
        assert changed.scenarios.equals(workbook.scenarios)

    assert workbook.timeseries.equals(original_timeseries)


def test_typical_day_heat_loads_reflect_seasonal_design():
    workbook = load_input_workbook(_workbook_path())
    by_id = {config.day_id: config for config in get_default_typical_days()}

    summer = generate_typical_day_workbook(workbook, by_id["TD_SUMMER"])
    winter = generate_typical_day_workbook(workbook, by_id["TD_WINTER"])
    transition = generate_typical_day_workbook(workbook, by_id["TD_TRANSITION"])

    summer_heat = summer.timeseries["heat_load_kw"].sum()
    winter_heat = winter.timeseries["heat_load_kw"].sum()
    transition_heat = transition.timeseries["heat_load_kw"].sum()

    assert winter_heat > transition_heat
    assert summer_heat < transition_heat


def test_typical_day_generation_scales_expected_columns():
    workbook = load_input_workbook(_workbook_path())
    by_id = {config.day_id: config for config in get_default_typical_days()}

    summer = generate_typical_day_workbook(workbook, by_id["TD_SUMMER"])
    winter = generate_typical_day_workbook(workbook, by_id["TD_WINTER"])

    assert summer.timeseries["pv_available_kw"].sum() > workbook.timeseries[
        "pv_available_kw"
    ].sum()
    assert winter.timeseries["pv_available_kw"].sum() < workbook.timeseries[
        "pv_available_kw"
    ].sum()
    assert winter.timeseries["wind_available_kw"].sum() > workbook.timeseries[
        "wind_available_kw"
    ].sum()
