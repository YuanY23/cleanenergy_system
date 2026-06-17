from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.uncertainty.robust_planning import (
    build_robust_typical_days,
    run_robust_capacity_planning,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_build_robust_typical_days_keeps_each_uncertainty_case_annualized():
    workbook = load_input_workbook(_workbook_path())
    robust_days = build_robust_typical_days(workbook)
    day_ids = [config.day_id for config, _ in robust_days]

    assert len(robust_days) == 18
    assert "TD_SUMMER__NORMAL" in day_ids
    assert "TD_WINTER__EXTREME" in day_ids

    weights_by_case = {}
    for config, _ in robust_days:
        weights_by_case.setdefault(config.uncertainty_case_id, 0.0)
        weights_by_case[config.uncertainty_case_id] += config.weight_days

    assert set(weights_by_case) == {
        "NORMAL",
        "PV_LOW",
        "WIND_LOW",
        "LOAD_HIGH",
        "H2_HIGH",
        "EXTREME",
    }
    assert all(abs(weight - 365.0) < 1e-9 for weight in weights_by_case.values())


def test_run_robust_capacity_planning_exports_worst_case_results(tmp_path: Path):
    outputs = run_robust_capacity_planning(_workbook_path(), tmp_path)

    expected_keys = {
        "robust_summary_csv",
        "robust_summary_excel",
        "robust_capacity_result_csv",
        "robust_capacity_result_excel",
        "robust_uncertainty_operation_csv",
        "robust_hourly_results_csv",
        "robust_capacity_mix_png",
        "robust_worst_case_cost_png",
        "robust_uncertainty_carbon_png",
        "conclusion_md",
    }
    assert expected_keys.issubset(outputs)
    for key in expected_keys:
        assert outputs[key].exists(), key
        assert outputs[key].stat().st_size > 0, key

    summary = pd.read_csv(outputs["robust_summary_csv"], encoding="utf-8-sig")
    capacity = pd.read_csv(outputs["robust_capacity_result_csv"], encoding="utf-8-sig")
    operation = pd.read_csv(
        outputs["robust_uncertainty_operation_csv"],
        encoding="utf-8-sig",
    )

    assert summary.loc[0, "status"] == "optimal"
    assert summary.loc[0, "robust_day_count"] == 18
    assert summary.loc[0, "worst_case_total_cost_cny"] > 0
    assert summary.loc[0, "worst_case_id"] in set(operation["uncertainty_case_id"])
    assert capacity["capacity_value"].ge(-1e-7).all()
    assert set(operation["uncertainty_case_id"]) == {
        "NORMAL",
        "PV_LOW",
        "WIND_LOW",
        "LOAD_HIGH",
        "H2_HIGH",
        "EXTREME",
    }
