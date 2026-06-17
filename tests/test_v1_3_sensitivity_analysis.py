from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.scenarios.sensitivity import (
    SensitivityCase,
    apply_sensitivity_case,
    get_v1_3_sensitivity_studies,
    run_v1_3_sensitivity_analysis,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_v1_3_studies_match_plan_case_ids():
    studies = get_v1_3_sensitivity_studies()

    assert set(studies) == {
        "electrolyzer_capacity_sensitivity",
        "h2_storage_capacity_sensitivity",
        "fuel_cell_capacity_sensitivity",
    }
    assert [case.case_id for case in studies["electrolyzer_capacity_sensitivity"].cases] == [
        "EL0",
        "EL1",
        "EL2",
        "EL3",
        "EL4",
    ]
    assert [case.case_id for case in studies["h2_storage_capacity_sensitivity"].cases] == [
        "HS0",
        "HS1",
        "HS2",
        "HS3",
        "HS4",
    ]
    assert [case.case_id for case in studies["fuel_cell_capacity_sensitivity"].cases] == [
        "FC0",
        "FC1",
        "FC2",
        "FC3",
        "FC4",
    ]


def test_apply_device_capacity_scales_only_target_parameters():
    workbook = load_input_workbook(_workbook_path())

    changed = apply_sensitivity_case(
        workbook,
        SensitivityCase(
            case_id="DEVICE_TEST",
            label="测试设备容量倍率",
            changes={
                "electrolyzer_power_scale": 1.5,
                "h2_storage_capacity_scale": 2.0,
                "fuel_cell_power_scale": 0.5,
            },
        ),
    )

    original = workbook.device_params.set_index("parameter")["value"]
    updated = changed.device_params.set_index("parameter")["value"]

    assert updated["electrolyzer_power_kW"] == original["electrolyzer_power_kW"] * 1.5
    assert updated["h2_storage_capacity_kg"] == original["h2_storage_capacity_kg"] * 2.0
    assert updated["h2_storage_initial_kg"] == original["h2_storage_initial_kg"]
    assert updated["fuel_cell_power_kW"] == original["fuel_cell_power_kW"] * 0.5
    pd.testing.assert_series_equal(
        workbook.device_params.set_index("parameter")["value"],
        original,
        check_names=False,
    )


def test_run_v1_3_sensitivity_analysis_exports_expected_groups(tmp_path: Path):
    outputs = run_v1_3_sensitivity_analysis(_workbook_path(), tmp_path)

    assert set(outputs) == {
        "electrolyzer_capacity_sensitivity",
        "h2_storage_capacity_sensitivity",
        "fuel_cell_capacity_sensitivity",
    }
    for paths in outputs.values():
        assert paths["summary_csv"].exists()
        assert paths["hourly_csv"].exists()
        assert paths["cost_png"].exists()
        assert paths["conclusion_md"].exists()

    assert (tmp_path / "results" / "v1_3_index.md").exists()
