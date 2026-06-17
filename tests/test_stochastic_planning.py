from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.uncertainty.stochastic_planning import (
    build_stochastic_typical_days,
    run_stochastic_capacity_planning,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_build_stochastic_typical_days_combines_typical_days_and_uncertainty_weights():
    workbook = load_input_workbook(_workbook_path())
    stochastic_days = build_stochastic_typical_days(workbook)
    day_ids = [config.day_id for config, _ in stochastic_days]
    total_weight = sum(config.weight_days for config, _ in stochastic_days)

    assert len(stochastic_days) == 18
    assert abs(total_weight - 365.0) < 1e-9
    assert "TD_SUMMER__NORMAL" in day_ids
    assert "TD_WINTER__EXTREME" in day_ids


def test_run_stochastic_capacity_planning_exports_expected_files(tmp_path: Path):
    outputs = run_stochastic_capacity_planning(_workbook_path(), tmp_path)

    expected_keys = {
        "stochastic_summary_csv",
        "stochastic_summary_excel",
        "stochastic_capacity_result_csv",
        "stochastic_capacity_result_excel",
        "stochastic_typical_uncertainty_operation_csv",
        "stochastic_hourly_results_csv",
        "stochastic_capacity_mix_png",
        "stochastic_cost_breakdown_png",
        "stochastic_uncertainty_cost_png",
        "conclusion_md",
    }
    assert expected_keys.issubset(outputs)
    for key in expected_keys:
        assert outputs[key].exists(), key
        assert outputs[key].stat().st_size > 0, key

    summary = pd.read_csv(outputs["stochastic_summary_csv"], encoding="utf-8-sig")
    capacity = pd.read_csv(
        outputs["stochastic_capacity_result_csv"],
        encoding="utf-8-sig",
    )
    operation = pd.read_csv(
        outputs["stochastic_typical_uncertainty_operation_csv"],
        encoding="utf-8-sig",
    )

    assert summary.loc[0, "status"] == "optimal"
    assert summary.loc[0, "annual_total_cost_cny"] > 0
    assert capacity["capacity_value"].ge(-1e-7).all()
    assert {"typical_day_id", "uncertainty_case_id"}.issubset(operation.columns)
    assert set(operation["uncertainty_case_id"]) == {
        "NORMAL",
        "PV_LOW",
        "WIND_LOW",
        "LOAD_HIGH",
        "H2_HIGH",
        "EXTREME",
    }
