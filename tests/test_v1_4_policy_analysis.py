from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.scenarios.sensitivity import (
    SensitivityCase,
    apply_sensitivity_case,
    get_v1_4_sensitivity_studies,
    run_v1_4_sensitivity_analysis,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_v1_4_studies_match_plan_case_ids():
    studies = get_v1_4_sensitivity_studies()

    assert set(studies) == {
        "h2_sale_price_sensitivity",
        "carbon_cap_sensitivity",
        "renewable_consumption_constraint_sensitivity",
    }
    assert [case.case_id for case in studies["h2_sale_price_sensitivity"].cases] == [
        "HSAL0",
        "HSAL1",
        "HSAL2",
        "HSAL3",
        "HSAL4",
    ]
    assert [case.case_id for case in studies["carbon_cap_sensitivity"].cases] == [
        "CAP0",
        "CAP1",
        "CAP2",
        "CAP3",
        "CAP4",
    ]
    assert [
        case.case_id
        for case in studies["renewable_consumption_constraint_sensitivity"].cases
    ] == ["RC0", "RC1", "RC2", "RC3"]


def test_apply_h2_sale_price_enables_sale_revenue_parameters():
    workbook = load_input_workbook(_workbook_path())

    changed = apply_sensitivity_case(
        workbook,
        SensitivityCase(
            case_id="HSAL_TEST",
            label="测试售氢",
            changes={"h2_sale_price_cny_per_kg": 30.0},
        ),
    )
    economic = changed.economic_params.set_index("parameter")["value"]

    assert economic["h2_sale_price"] == 30.0
    assert economic["h2_sale_enabled"] == 1.0


def test_run_v1_4_sensitivity_analysis_exports_expected_groups(tmp_path: Path):
    outputs = run_v1_4_sensitivity_analysis(_workbook_path(), tmp_path)

    assert set(outputs) == {
        "h2_sale_price_sensitivity",
        "carbon_cap_sensitivity",
        "renewable_consumption_constraint_sensitivity",
    }
    for paths in outputs.values():
        assert paths["summary_csv"].exists()
        assert paths["hourly_csv"].exists()
        assert paths["cost_png"].exists()
        assert paths["conclusion_md"].exists()

    assert (tmp_path / "results" / "v1_4_index.md").exists()


def test_v1_4_outputs_include_new_policy_metrics(tmp_path: Path):
    outputs = run_v1_4_sensitivity_analysis(_workbook_path(), tmp_path)

    sale_summary = pd.read_csv(outputs["h2_sale_price_sensitivity"]["summary_csv"])
    carbon_summary = pd.read_csv(outputs["carbon_cap_sensitivity"]["summary_csv"])
    renewable_summary = pd.read_csv(
        outputs["renewable_consumption_constraint_sensitivity"]["summary_csv"]
    )

    assert "h2_sale_kg" in sale_summary.columns
    assert "h2_sale_revenue_cny" in sale_summary.columns
    assert sale_summary.loc[sale_summary["scenario_id"] == "HSAL4", "h2_sale_kg"].iloc[0] >= 0
    assert "carbon_cap_excess_kg" in carbon_summary.columns
    assert "carbon_emission_cap_kg" in carbon_summary.columns
    assert "renewable_consumption_rate" in renewable_summary.columns
    assert renewable_summary["status"].eq("optimal").all()
