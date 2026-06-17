from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import get_default_planning_cost_params
from zero_carbon_park.planning.pareto import run_cost_carbon_pareto_analysis
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_capacity_planning_model_accepts_annual_carbon_cap():
    workbook = load_input_workbook(_workbook_path())
    typical_days = [
        (
            config,
            generate_typical_day_workbook(workbook, config),
        )
        for config in get_default_typical_days()
    ]

    model = build_capacity_planning_model(
        typical_days=typical_days,
        cost_params=get_default_planning_cost_params(),
        annual_carbon_emission_cap_kg=1.0e9,
    )

    assert hasattr(model, "annual_carbon_emission_cap_kg")
    assert hasattr(model, "annual_carbon_cap_constraint")


def test_run_cost_carbon_pareto_analysis_exports_expected_files(tmp_path: Path):
    outputs = run_cost_carbon_pareto_analysis(
        _workbook_path(),
        tmp_path,
        carbon_cap_ratios=[1.0, 0.9],
    )

    expected_keys = {
        "pareto_summary_csv",
        "pareto_summary_excel",
        "pareto_capacity_results_csv",
        "pareto_capacity_results_excel",
        "pareto_hourly_results_csv",
        "cost_carbon_pareto_curve_png",
        "capacity_mix_pareto_png",
        "renewable_consumption_pareto_png",
        "conclusion_md",
    }
    assert expected_keys.issubset(outputs)
    for key in expected_keys:
        assert outputs[key].exists(), key
        assert outputs[key].stat().st_size > 0, key

    summary = pd.read_csv(outputs["pareto_summary_csv"], encoding="utf-8-sig")
    capacity = pd.read_csv(outputs["pareto_capacity_results_csv"], encoding="utf-8-sig")

    assert len(summary) == 2
    assert set(summary["carbon_cap_ratio"]) == {1.0, 0.9}
    assert summary["status"].eq("optimal").all()
    assert summary["annual_total_cost_cny"].gt(0).all()
    assert summary["carbon_reduction_vs_baseline_pct"].ge(-1e-9).all()
    assert set(capacity["case_id"]) == set(summary["case_id"])
