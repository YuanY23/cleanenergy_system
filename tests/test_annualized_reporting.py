from pathlib import Path

import pandas as pd

from zero_carbon_park.reporting.export import export_annual_conclusion
from zero_carbon_park.reporting.plots import (
    plot_annual_carbon_by_typical_day,
    plot_annual_cost_breakdown,
    plot_annual_energy_by_typical_day,
)


def test_annualized_reporting_exports_figures_and_conclusion(tmp_path: Path):
    annual_summary = pd.DataFrame(
        [
            {
                "annual_total_cost_cny": 1000.0,
                "annual_grid_cost_cny": 300.0,
                "annual_gas_cost_cny": 0.0,
                "annual_carbon_cost_cny": 50.0,
                "annual_carbon_emission_kg": 1200.0,
                "annual_renewable_consumption_rate": 0.95,
                "annual_grid_purchase_kwh": 5000.0,
            }
        ]
    )
    contribution = pd.DataFrame(
        [
            {
                "typical_day_id": "TD_A",
                "typical_day_name": "A日",
                "weighted_total_cost_cny": 600.0,
                "weighted_carbon_emission_kg": 700.0,
                "weighted_grid_purchase_kwh": 2000.0,
                "weighted_heat_pump_heat_kwh": 3000.0,
                "weighted_h2_production_kg": 100.0,
            },
            {
                "typical_day_id": "TD_B",
                "typical_day_name": "B日",
                "weighted_total_cost_cny": 400.0,
                "weighted_carbon_emission_kg": 500.0,
                "weighted_grid_purchase_kwh": 3000.0,
                "weighted_heat_pump_heat_kwh": 2000.0,
                "weighted_h2_production_kg": 80.0,
            },
        ]
    )

    paths = [
        plot_annual_cost_breakdown(
            annual_summary,
            tmp_path / "annual_cost_breakdown.png",
        ),
        plot_annual_carbon_by_typical_day(
            contribution,
            tmp_path / "annual_carbon_by_typical_day.png",
        ),
        plot_annual_energy_by_typical_day(
            contribution,
            tmp_path / "annual_energy_by_typical_day.png",
        ),
        export_annual_conclusion(
            annual_summary,
            contribution,
            tmp_path / "annual_conclusion.md",
        ),
    ]

    for path in paths:
        assert Path(path).exists()
        assert Path(path).stat().st_size > 0

    conclusion = (tmp_path / "annual_conclusion.md").read_text(encoding="utf-8")
    assert "多典型日加权年化结果" in conclusion
    assert "年度总运行成本" in conclusion


def test_annualized_typical_day_plots_accept_empty_contribution(tmp_path: Path):
    empty_contribution = pd.DataFrame(
        columns=[
            "typical_day_id",
            "weighted_carbon_emission_kg",
            "weighted_grid_purchase_kwh",
            "weighted_heat_pump_heat_kwh",
            "weighted_h2_production_kg",
        ]
    )

    paths = [
        plot_annual_carbon_by_typical_day(
            empty_contribution,
            tmp_path / "empty_carbon.png",
        ),
        plot_annual_energy_by_typical_day(
            empty_contribution,
            tmp_path / "empty_energy.png",
        ),
    ]

    for path in paths:
        assert Path(path).exists()
        assert Path(path).stat().st_size > 0
