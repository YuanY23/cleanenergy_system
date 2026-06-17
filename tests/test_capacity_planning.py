from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import (
    capital_recovery_factor,
    get_default_planning_cost_params,
)
from zero_carbon_park.planning.runner import run_capacity_planning
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_capital_recovery_factor_and_default_cost_params_are_positive():
    crf = capital_recovery_factor(rate=0.08, years=20)
    params = get_default_planning_cost_params()

    assert crf > 0
    assert params.discount_rate == 0.08
    assert params.wind_capex_cny_per_kw > 0
    assert params.pv_capex_cny_per_kw > 0
    assert params.battery_power_capex_cny_per_kw > 0
    assert params.battery_energy_capex_cny_per_kwh > 0
    assert params.electrolyzer_capex_cny_per_kw > 0
    assert params.h2_storage_capex_cny_per_kg > 0
    assert params.fuel_cell_capex_cny_per_kw > 0
    assert params.heat_pump_capex_cny_per_kw > 0


def test_capacity_planning_model_contains_capacity_variables():
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
    )

    for variable_name in [
        "wind_capacity_kw",
        "pv_capacity_kw",
        "battery_power_capacity_kw",
        "battery_energy_capacity_kwh",
        "electrolyzer_power_capacity_kw",
        "h2_storage_capacity_kg",
        "fuel_cell_power_capacity_kw",
        "heat_pump_power_capacity_kw",
    ]:
        assert hasattr(model, variable_name)


def test_run_capacity_planning_exports_expected_files(tmp_path: Path):
    outputs = run_capacity_planning(_workbook_path(), tmp_path)

    expected_keys = {
        "planning_summary_csv",
        "planning_summary_excel",
        "planning_capacity_result_csv",
        "planning_capacity_result_excel",
        "planning_typical_day_operation_csv",
        "planning_typical_day_operation_excel",
        "planning_hourly_results_csv",
        "capacity_mix_png",
        "annual_cost_breakdown_png",
        "annual_carbon_by_typical_day_png",
        "planning_conclusion_md",
    }
    assert expected_keys.issubset(outputs)
    for key in expected_keys:
        assert outputs[key].exists(), key
        assert outputs[key].stat().st_size > 0, key

    summary = pd.read_csv(outputs["planning_summary_csv"], encoding="utf-8-sig")
    capacity = pd.read_csv(outputs["planning_capacity_result_csv"], encoding="utf-8-sig")

    assert summary.loc[0, "status"] == "optimal"
    assert summary.loc[0, "annual_total_cost_cny"] > 0
    assert summary.loc[0, "annual_total_cost_cny"] == (
        summary.loc[0, "annual_operation_cost_cny"]
        + summary.loc[0, "annualized_investment_cost_cny"]
    )
    assert capacity["capacity_value"].ge(0).all()
