from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.scenarios.sensitivity import (
    SensitivityCase,
    apply_sensitivity_case,
    get_v1_2_sensitivity_studies,
    run_v1_2_sensitivity_analysis,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_v1_2_studies_match_plan_case_ids():
    studies = get_v1_2_sensitivity_studies()

    assert set(studies) == {
        "electricity_price_spread_sensitivity",
        "gas_price_sensitivity",
        "grid_emission_factor_sensitivity",
    }
    assert [
        case.case_id
        for case in studies["electricity_price_spread_sensitivity"].cases
    ] == ["P0", "P1", "P2", "P3", "P4"]
    assert [case.case_id for case in studies["gas_price_sensitivity"].cases] == [
        "G0",
        "G1",
        "G2",
        "G3",
        "G4",
    ]
    assert [
        case.case_id for case in studies["grid_emission_factor_sensitivity"].cases
    ] == ["E0", "E1", "E2", "E3"]


def test_apply_electricity_price_spread_scales_only_valley_and_peak_prices():
    workbook = load_input_workbook(_workbook_path())
    original_prices = workbook.timeseries["electricity_price_cny_per_kwh"].copy()
    valley_price = original_prices.min()
    peak_price = original_prices.max()

    changed = apply_sensitivity_case(
        workbook,
        SensitivityCase(
            case_id="P_TEST",
            label="测试峰谷价差",
            changes={"valley_price_scale": 0.5, "peak_price_scale": 2.0},
        ),
    )
    changed_prices = changed.timeseries["electricity_price_cny_per_kwh"]

    assert changed_prices[original_prices == valley_price].eq(valley_price * 0.5).all()
    assert changed_prices[original_prices == peak_price].eq(peak_price * 2.0).all()
    assert changed_prices[
        (original_prices != valley_price) & (original_prices != peak_price)
    ].equals(original_prices[(original_prices != valley_price) & (original_prices != peak_price)])
    assert workbook.timeseries["electricity_price_cny_per_kwh"].equals(original_prices)


def test_apply_gas_price_and_grid_emission_factor_scales_inputs():
    workbook = load_input_workbook(_workbook_path())

    gas_changed = apply_sensitivity_case(
        workbook,
        SensitivityCase(
            case_id="G_TEST",
            label="测试天然气价格",
            changes={"gas_price_scale": 1.5},
        ),
    )
    emission_changed = apply_sensitivity_case(
        workbook,
        SensitivityCase(
            case_id="E_TEST",
            label="测试电网排放因子",
            changes={"grid_emission_factor_scale": 0.4},
        ),
    )

    pd.testing.assert_series_equal(
        gas_changed.timeseries["gas_price_cny_per_m3"],
        workbook.timeseries["gas_price_cny_per_m3"] * 1.5,
        check_names=False,
    )
    pd.testing.assert_series_equal(
        emission_changed.timeseries["grid_emission_kgco2_per_kwh"],
        workbook.timeseries["grid_emission_kgco2_per_kwh"] * 0.4,
        check_names=False,
    )


def test_run_v1_2_sensitivity_analysis_exports_expected_groups(tmp_path: Path):
    outputs = run_v1_2_sensitivity_analysis(_workbook_path(), tmp_path)

    assert set(outputs) == {
        "electricity_price_spread_sensitivity",
        "gas_price_sensitivity",
        "grid_emission_factor_sensitivity",
    }
    for paths in outputs.values():
        assert paths["summary_csv"].exists()
        assert paths["hourly_csv"].exists()
        assert paths["cost_png"].exists()
        assert paths["conclusion_md"].exists()

    assert (tmp_path / "results" / "v1_2_index.md").exists()
