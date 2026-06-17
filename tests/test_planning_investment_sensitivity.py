from pathlib import Path

import pandas as pd

from zero_carbon_park.planning.cost_params import get_default_planning_cost_params
from zero_carbon_park.planning.sensitivity import (
    apply_investment_multiplier,
    get_default_investment_sensitivity_cases,
    run_investment_sensitivity_analysis,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_default_investment_sensitivity_cases_cover_all_device_groups():
    cases = get_default_investment_sensitivity_cases()
    groups = {case.capex_group for case in cases}
    multipliers = {case.capex_multiplier for case in cases}

    assert groups == {
        "WIND",
        "PV",
        "BATTERY",
        "ELECTROLYZER",
        "H2_STORAGE",
        "FUEL_CELL",
        "HEAT_PUMP",
    }
    assert multipliers == {0.5, 0.75, 1.0, 1.25, 1.5}
    assert len(cases) == 35


def test_apply_investment_multiplier_scales_only_target_cost_fields():
    params = get_default_planning_cost_params()

    battery = apply_investment_multiplier(params, "BATTERY", 0.5)
    assert battery.battery_power_capex_cny_per_kw == (
        params.battery_power_capex_cny_per_kw * 0.5
    )
    assert battery.battery_energy_capex_cny_per_kwh == (
        params.battery_energy_capex_cny_per_kwh * 0.5
    )
    assert battery.wind_capex_cny_per_kw == params.wind_capex_cny_per_kw

    fuel_cell = apply_investment_multiplier(params, "FUEL_CELL", 0.75)
    assert fuel_cell.fuel_cell_capex_cny_per_kw == (
        params.fuel_cell_capex_cny_per_kw * 0.75
    )
    assert fuel_cell.electrolyzer_capex_cny_per_kw == (
        params.electrolyzer_capex_cny_per_kw
    )


def test_run_investment_sensitivity_exports_expected_files(tmp_path: Path):
    outputs = run_investment_sensitivity_analysis(
        _workbook_path(),
        tmp_path,
        capex_groups=["FUEL_CELL"],
        capex_multipliers=[0.5, 1.0],
    )

    expected_keys = {
        "scenario_summary_csv",
        "scenario_summary_excel",
        "capacity_results_csv",
        "capacity_results_excel",
        "scenario_metadata_csv",
        "annual_total_cost_vs_capex_png",
        "annual_carbon_vs_capex_png",
        "capacity_selection_vs_capex_png",
        "fuel_cell_threshold_png",
        "conclusion_md",
    }
    assert expected_keys.issubset(outputs)
    for key in expected_keys:
        assert outputs[key].exists(), key
        assert outputs[key].stat().st_size > 0, key

    summary = pd.read_csv(outputs["scenario_summary_csv"], encoding="utf-8-sig")
    capacity = pd.read_csv(outputs["capacity_results_csv"], encoding="utf-8-sig")

    assert len(summary) == 2
    assert summary["status"].eq("optimal").all()
    assert set(summary["capex_group"]) == {"FUEL_CELL"}
    assert set(summary["capex_multiplier"]) == {0.5, 1.0}
    assert summary["annual_total_cost_cny"].gt(0).all()
    assert set(capacity["case_id"]) == set(summary["case_id"])
