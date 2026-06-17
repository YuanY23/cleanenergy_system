from pathlib import Path

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.scenarios.runner import run_scenario, run_scenarios


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_s4_fuel_cell_solves_and_preserves_power_hydrogen_balances():
    workbook = load_input_workbook(_workbook_path())

    result = run_scenario(workbook, "S4")
    hourly = result.hourly_results

    assert result.status == "optimal"
    assert result.summary["max_power_balance_residual_kw"] <= 1e-5
    assert result.summary["max_hydrogen_balance_residual_kg"] <= 1e-5
    assert result.summary["max_fuel_cell_conversion_residual_kw"] <= 1e-5
    assert "fuel_cell_power_kw" in hourly.columns
    assert "h2_fuel_cell_kg" in hourly.columns
    assert hourly["fuel_cell_power_kw"].ge(-1e-5).all()
    assert hourly["h2_fuel_cell_kg"].ge(-1e-5).all()


def test_s5_carbon_price_adds_carbon_cost_against_s4():
    workbook = load_input_workbook(_workbook_path())

    s4 = run_scenario(workbook, "S4")
    s5 = run_scenario(workbook, "S5")

    assert s4.status == "optimal"
    assert s5.status == "optimal"
    assert s4.summary["carbon_cost_cny"] == 0
    assert s5.summary["carbon_cost_cny"] > 0
    assert s5.summary["total_cost_cny"] > s4.summary["total_cost_cny"]
    assert s5.summary["carbon_emission_kg"] <= s4.summary["carbon_emission_kg"] + 1e-5


def test_run_scenarios_exports_s0_to_s5(tmp_path: Path):
    workbook = load_input_workbook(_workbook_path())

    outputs = run_scenarios(workbook, ["S0", "S1", "S2", "S3", "S4", "S5"], tmp_path)

    assert outputs["summary_csv"].exists()
    assert outputs["hourly_csv"].exists()
    assert outputs["summary_csv"].stat().st_size > 0
    assert outputs["hourly_csv"].stat().st_size > 0
