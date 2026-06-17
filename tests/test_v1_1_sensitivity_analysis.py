from pathlib import Path

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.scenarios.sensitivity import (
    SensitivityCase,
    SensitivityStudy,
    apply_sensitivity_case,
    get_v1_1_sensitivity_studies,
    run_sensitivity_study,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_v1_1_studies_match_plan_case_ids():
    studies = get_v1_1_sensitivity_studies()

    assert set(studies) == {
        "carbon_price_sensitivity",
        "renewable_scale_sensitivity",
        "battery_capacity_sensitivity",
        "hydrogen_load_sensitivity",
    }
    assert [case.case_id for case in studies["carbon_price_sensitivity"].cases] == [
        "C0",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
    ]
    assert [case.case_id for case in studies["renewable_scale_sensitivity"].cases] == [
        "R0",
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
    ]
    assert [case.case_id for case in studies["battery_capacity_sensitivity"].cases] == [
        "B0",
        "B1",
        "B2",
        "B3",
        "B4",
        "B5",
    ]
    assert [case.case_id for case in studies["hydrogen_load_sensitivity"].cases] == [
        "H0",
        "H1",
        "H2",
        "H3",
        "H4",
    ]


def test_apply_sensitivity_case_copies_workbook_without_mutating_original():
    workbook = load_input_workbook(_workbook_path())
    original_carbon_price = workbook.timeseries["carbon_price_cny_per_tco2"].copy()

    case = SensitivityCase(
        case_id="C_TEST",
        label="测试碳价",
        changes={"carbon_price_cny_per_tco2": 123.0},
    )
    changed = apply_sensitivity_case(workbook, case)

    assert changed.timeseries["carbon_price_cny_per_tco2"].eq(123.0).all()
    assert workbook.timeseries["carbon_price_cny_per_tco2"].equals(original_carbon_price)


def test_run_sensitivity_study_exports_group_and_case_folders(tmp_path: Path):
    workbook = load_input_workbook(_workbook_path())
    study = SensitivityStudy(
        study_id="test_carbon",
        title="测试碳价敏感性",
        base_scenario_id="S5",
        x_label="碳价/(元/tCO2)",
        x_column="carbon_price_cny_per_tco2",
        cases=[
            SensitivityCase(
                case_id="TC0",
                label="0 元/tCO2",
                changes={"carbon_price_cny_per_tco2": 0.0},
            ),
            SensitivityCase(
                case_id="TC1",
                label="100 元/tCO2",
                changes={"carbon_price_cny_per_tco2": 100.0},
            ),
        ],
    )

    outputs = run_sensitivity_study(workbook, study, tmp_path)

    assert outputs["summary_csv"].exists()
    assert outputs["hourly_csv"].exists()
    assert outputs["cost_png"].exists()
    assert outputs["carbon_png"].exists()
    assert outputs["conclusion_md"].exists()
    assert (tmp_path / "TC0" / "scenario_summary.csv").exists()
    assert (tmp_path / "TC0" / "scenario_hourly_results.csv").exists()
    assert (tmp_path / "TC1" / "scenario_summary.csv").exists()
    assert (tmp_path / "TC1" / "scenario_hourly_results.csv").exists()


def test_high_hydrogen_load_stress_case_uses_external_h2_supply(tmp_path: Path):
    workbook = load_input_workbook(_workbook_path())
    study = SensitivityStudy(
        study_id="test_high_hydrogen",
        title="测试高氢负荷",
        base_scenario_id="S5",
        x_label="氢负荷倍率",
        x_column="hydrogen_load_scale",
        cases=[
            SensitivityCase(
                case_id="TH4",
                label="2.0 倍",
                changes={"hydrogen_load_scale": 2.0},
            ),
        ],
    )

    outputs = run_sensitivity_study(workbook, study, tmp_path)

    summary = outputs["summary_csv"].read_text(encoding="utf-8-sig")
    assert "h2_external_supply_kg" in summary

    summary_frame = __import__("pandas").read_csv(outputs["summary_csv"])
    assert summary_frame.loc[0, "status"] == "optimal"
    assert summary_frame.loc[0, "h2_external_supply_kg"] > 0
