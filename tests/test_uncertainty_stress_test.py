from pathlib import Path

import pandas as pd
import pytest

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.uncertainty.definitions import get_default_uncertainty_cases
from zero_carbon_park.uncertainty.generator import generate_uncertainty_workbook
from zero_carbon_park.uncertainty.stress_test import run_uncertainty_stress_test


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_default_uncertainty_cases_cover_normal_and_stress_cases():
    cases = get_default_uncertainty_cases()
    case_ids = {case.case_id for case in cases}
    probabilities = sum(case.probability for case in cases)

    assert case_ids == {
        "NORMAL",
        "PV_LOW",
        "WIND_LOW",
        "LOAD_HIGH",
        "H2_HIGH",
        "EXTREME",
    }
    assert abs(probabilities - 1.0) < 1e-9


def test_generate_uncertainty_workbook_scales_selected_columns_without_mutating_original():
    workbook = load_input_workbook(_workbook_path())
    original = workbook.timeseries.copy(deep=True)
    extreme = [
        case for case in get_default_uncertainty_cases() if case.case_id == "EXTREME"
    ][0]

    stressed = generate_uncertainty_workbook(workbook, extreme)

    assert workbook.timeseries.equals(original)
    assert stressed.timeseries["pv_available_kw"].sum() == (
        original["pv_available_kw"].sum() * extreme.pv_scale
    )
    assert stressed.timeseries["wind_available_kw"].sum() == (
        original["wind_available_kw"].sum() * extreme.wind_scale
    )
    assert stressed.timeseries["electric_load_kw"].sum() == pytest.approx(
        original["electric_load_kw"].sum() * extreme.electric_load_scale
    )
    assert stressed.timeseries["hydrogen_load_kg"].sum() == pytest.approx(
        original["hydrogen_load_kg"].sum() * extreme.hydrogen_load_scale
    )


def test_run_uncertainty_stress_test_exports_expected_files(tmp_path: Path):
    outputs = run_uncertainty_stress_test(
        _workbook_path(),
        tmp_path,
        uncertainty_case_ids=["NORMAL", "EXTREME"],
    )

    expected_keys = {
        "stress_summary_csv",
        "stress_summary_excel",
        "stress_typical_day_operation_csv",
        "stress_hourly_results_csv",
        "reference_capacity_csv",
        "stress_cost_carbon_png",
        "stress_external_h2_png",
        "conclusion_md",
    }
    assert expected_keys.issubset(outputs)
    for key in expected_keys:
        assert outputs[key].exists(), key
        assert outputs[key].stat().st_size > 0, key

    summary = pd.read_csv(outputs["stress_summary_csv"], encoding="utf-8-sig")
    assert set(summary["uncertainty_case_id"]) == {"NORMAL", "EXTREME"}
    assert summary["status"].eq("optimal").all()
    assert summary["annual_total_cost_cny"].gt(0).all()
    assert "cost_increase_vs_normal_pct" in summary.columns
    assert "carbon_increase_vs_normal_pct" in summary.columns
