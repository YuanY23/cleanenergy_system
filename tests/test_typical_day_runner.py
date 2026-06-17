from pathlib import Path

import pandas as pd

from zero_carbon_park.typical_days.runner import run_typical_day_scenarios


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_run_typical_day_scenarios_exports_expected_outputs(tmp_path: Path):
    outputs = run_typical_day_scenarios(_workbook_path(), tmp_path)

    assert outputs["summary_csv"].exists()
    summary = pd.read_csv(outputs["summary_csv"], encoding="utf-8-sig")
    assert set(summary["typical_day_id"]) == {
        "TD_SUMMER",
        "TD_WINTER",
        "TD_TRANSITION",
    }
    assert summary["status"].eq("optimal").all()
    assert summary["weight_days"].sum() == 365

    result_root = tmp_path / "results" / "v2_typical_days"
    for typical_day_id in ["TD_SUMMER", "TD_WINTER", "TD_TRANSITION"]:
        day_dir = result_root / typical_day_id
        assert (day_dir / "input_timeseries.csv").exists()
        assert (day_dir / "scenario_summary.csv").exists()
        assert (day_dir / "scenario_hourly_results.csv").exists()
        assert (day_dir / "device_outputs.png").exists()
        assert (day_dir / "battery_soc.png").exists()
        assert (day_dir / "h2_storage.png").exists()


def test_typical_day_outputs_are_different_across_seasons(tmp_path: Path):
    outputs = run_typical_day_scenarios(_workbook_path(), tmp_path)
    summary = pd.read_csv(outputs["summary_csv"], encoding="utf-8-sig")

    by_id = summary.set_index("typical_day_id")

    assert by_id.loc["TD_WINTER", "heat_pump_heat_kwh"] > by_id.loc[
        "TD_SUMMER", "heat_pump_heat_kwh"
    ]
    assert by_id.loc["TD_WINTER", "carbon_emission_kg"] != by_id.loc[
        "TD_SUMMER", "carbon_emission_kg"
    ]
