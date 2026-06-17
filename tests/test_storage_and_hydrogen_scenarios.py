from pathlib import Path

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.scenarios.runner import run_scenario, run_scenarios


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_s2_battery_storage_solves_with_soc_bounds_and_no_simultaneous_charge_discharge():
    workbook = load_input_workbook(_workbook_path())

    result = run_scenario(workbook, "S2")
    hourly = result.hourly_results

    assert result.status == "optimal"
    assert result.summary["max_power_balance_residual_kw"] <= 1e-5
    assert result.summary["battery_soc_min_kwh"] >= -1e-5
    assert result.summary["battery_soc_max_kwh"] <= 10000 + 1e-5
    assert abs(result.summary["battery_terminal_delta_kwh"]) <= 1e-5
    assert (
        hourly["battery_charge_kw"] * hourly["battery_discharge_kw"]
    ).abs().max() <= 1e-5
    assert hourly["battery_soc_kwh"].between(-1e-5, 10000 + 1e-5).all()


def test_s3_hydrogen_system_solves_with_hydrogen_balance_and_storage_bounds():
    workbook = load_input_workbook(_workbook_path())

    result = run_scenario(workbook, "S3")
    hourly = result.hourly_results

    assert result.status == "optimal"
    assert result.summary["max_power_balance_residual_kw"] <= 1e-5
    assert result.summary["max_hydrogen_balance_residual_kg"] <= 1e-5
    assert result.summary["h2_storage_min_kg"] >= -1e-5
    assert result.summary["h2_storage_max_kg"] <= 1000 + 1e-5
    assert result.summary["h2_production_kg"] >= result.summary["hydrogen_load_kg"] - 300
    assert hourly["h2_storage_kg"].between(-1e-5, 1000 + 1e-5).all()


def test_run_scenarios_exports_s0_to_s3(tmp_path: Path):
    workbook = load_input_workbook(_workbook_path())

    outputs = run_scenarios(workbook, ["S0", "S1", "S2", "S3"], tmp_path)

    assert outputs["summary_csv"].exists()
    assert outputs["hourly_csv"].exists()
    assert outputs["summary_csv"].stat().st_size > 0
    assert outputs["hourly_csv"].stat().st_size > 0
