from pathlib import Path

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.scenarios.runner import run_scenario, run_scenarios


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_s0_and_s1_minimal_milp_solve_with_small_balance_residuals():
    workbook = load_input_workbook(_workbook_path())

    s0 = run_scenario(workbook, "S0")
    s1 = run_scenario(workbook, "S1")

    assert s0.status == "optimal"
    assert s1.status == "optimal"
    assert len(s0.hourly_results) == 24
    assert len(s1.hourly_results) == 24
    assert s0.summary["max_power_balance_residual_kw"] <= 1e-5
    assert s1.summary["max_power_balance_residual_kw"] <= 1e-5
    assert s0.summary["max_heat_balance_residual_kw"] <= 1e-5
    assert s1.summary["max_heat_balance_residual_kw"] <= 1e-5
    assert s1.summary["grid_purchase_kwh"] < s0.summary["grid_purchase_kwh"]
    assert s1.summary["carbon_emission_kg"] < s0.summary["carbon_emission_kg"]


def test_s0_disables_renewables_and_heat_pump():
    workbook = load_input_workbook(_workbook_path())

    result = run_scenario(workbook, "S0")
    hourly = result.hourly_results

    assert hourly["pv_used_kw"].sum() == 0
    assert hourly["wind_used_kw"].sum() == 0
    assert hourly["heat_pump_power_kw"].sum() == 0
    assert hourly["grid_buy_kw"].sum() == hourly["electric_load_kw"].sum()


def test_run_scenarios_exports_hourly_and_summary_files(tmp_path: Path):
    workbook = load_input_workbook(_workbook_path())

    outputs = run_scenarios(workbook, ["S0", "S1"], tmp_path)

    assert outputs["summary_csv"].exists()
    assert outputs["summary_excel"].exists()
    assert outputs["hourly_csv"].exists()
    assert outputs["hourly_excel"].exists()
    assert outputs["summary_csv"].stat().st_size > 0
    assert outputs["hourly_csv"].stat().st_size > 0
