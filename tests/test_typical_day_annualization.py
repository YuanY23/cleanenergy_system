from pathlib import Path

import pandas as pd

from zero_carbon_park.typical_days.annualization import (
    annualize_typical_day_results,
    run_annualized_typical_days,
)


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*.xlsx"))
    assert matches, "测试需要项目根目录下的 Excel 数据包"
    return matches[0]


def test_annualize_typical_day_results_uses_weighted_totals_not_average():
    summary = pd.DataFrame(
        [
            {
                "typical_day_id": "A",
                "typical_day_name": "A日",
                "weight_days": 100,
                "total_cost_cny": 10.0,
                "grid_purchase_kwh": 20.0,
                "carbon_emission_kg": 30.0,
                "renewable_available_kwh": 100.0,
                "renewable_used_kwh": 50.0,
                "heat_pump_heat_kwh": 5.0,
                "h2_production_kg": 2.0,
            },
            {
                "typical_day_id": "B",
                "typical_day_name": "B日",
                "weight_days": 200,
                "total_cost_cny": 20.0,
                "grid_purchase_kwh": 30.0,
                "carbon_emission_kg": 40.0,
                "renewable_available_kwh": 300.0,
                "renewable_used_kwh": 150.0,
                "heat_pump_heat_kwh": 6.0,
                "h2_production_kg": 3.0,
            },
        ]
    )

    annual_summary, contribution = annualize_typical_day_results(summary)

    annual = annual_summary.iloc[0]
    assert annual["annual_weight_days"] == 300
    assert annual["annual_total_cost_cny"] == 5000.0
    assert annual["annual_grid_purchase_kwh"] == 8000.0
    assert annual["annual_carbon_emission_kg"] == 11000.0
    assert annual["annual_renewable_available_kwh"] == 70000.0
    assert annual["annual_renewable_used_kwh"] == 35000.0
    assert annual["annual_renewable_consumption_rate"] == 0.5
    assert len(contribution) == 2
    assert "weighted_total_cost_cny" in contribution.columns


def test_run_annualized_typical_days_exports_expected_files(tmp_path: Path):
    outputs = run_annualized_typical_days(_workbook_path(), tmp_path)

    expected_keys = {
        "annual_summary_csv",
        "annual_summary_excel",
        "typical_day_contribution_csv",
        "typical_day_contribution_excel",
        "annual_cost_breakdown_png",
        "annual_carbon_by_typical_day_png",
        "annual_energy_by_typical_day_png",
        "annual_conclusion_md",
    }
    assert expected_keys.issubset(outputs)
    for key in expected_keys:
        assert outputs[key].exists(), key
        assert outputs[key].stat().st_size > 0, key

    annual = pd.read_csv(outputs["annual_summary_csv"], encoding="utf-8-sig")
    contribution = pd.read_csv(
        outputs["typical_day_contribution_csv"],
        encoding="utf-8-sig",
    )

    assert len(annual) == 1
    assert len(contribution) == 3
    assert annual.loc[0, "annual_weight_days"] == 365
    assert contribution["typical_day_id"].nunique() == 3
