"""多典型日加权年化统计模块。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from zero_carbon_park.reporting.export import export_annual_conclusion
from zero_carbon_park.reporting.plots import (
    plot_annual_carbon_by_typical_day,
    plot_annual_cost_breakdown,
    plot_annual_energy_by_typical_day,
)
from zero_carbon_park.typical_days.runner import run_typical_day_scenarios


WEIGHTED_COLUMNS = {
    "total_cost_cny": "annual_total_cost_cny",
    "grid_cost_cny": "annual_grid_cost_cny",
    "gas_cost_cny": "annual_gas_cost_cny",
    "carbon_cost_cny": "annual_carbon_cost_cny",
    "grid_purchase_kwh": "annual_grid_purchase_kwh",
    "renewable_available_kwh": "annual_renewable_available_kwh",
    "renewable_used_kwh": "annual_renewable_used_kwh",
    "renewable_curtailment_kwh": "annual_renewable_curtailment_kwh",
    "carbon_emission_kg": "annual_carbon_emission_kg",
    "h2_production_kg": "annual_h2_production_kg",
    "h2_external_supply_kg": "annual_h2_external_supply_kg",
    "fuel_cell_generation_kwh": "annual_fuel_cell_generation_kwh",
    "heat_pump_heat_kwh": "annual_heat_pump_heat_kwh",
    "gas_boiler_heat_kwh": "annual_gas_boiler_heat_kwh",
    "battery_charge_kwh": "annual_battery_charge_kwh",
    "battery_discharge_kwh": "annual_battery_discharge_kwh",
}


def annualize_typical_day_results(
    summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把多典型日汇总结果按代表天数加权为年度指标。"""

    required = {"typical_day_id", "typical_day_name", "weight_days"}
    missing = required - set(summary.columns)
    if missing:
        raise ValueError(f"典型日汇总表缺少字段: {sorted(missing)}")

    contribution = summary.copy()
    for source_column in WEIGHTED_COLUMNS:
        if source_column in contribution.columns:
            contribution[f"weighted_{source_column}"] = (
                contribution[source_column] * contribution["weight_days"]
            )

    annual_row: dict[str, float] = {
        "annual_weight_days": float(contribution["weight_days"].sum())
    }
    for source_column, annual_column in WEIGHTED_COLUMNS.items():
        weighted_column = f"weighted_{source_column}"
        if weighted_column in contribution.columns:
            annual_row[annual_column] = float(contribution[weighted_column].sum())

    renewable_available = annual_row.get("annual_renewable_available_kwh", 0.0)
    renewable_used = annual_row.get("annual_renewable_used_kwh", 0.0)
    annual_row["annual_renewable_consumption_rate"] = (
        renewable_used / renewable_available if renewable_available > 0 else 0.0
    )

    annual_summary = pd.DataFrame([annual_row])
    return annual_summary, contribution


def run_annualized_typical_days(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
    scenario_id: str = "S5",
) -> dict[str, Path]:
    """运行多典型日并导出加权年化结果。"""

    typical_outputs = run_typical_day_scenarios(workbook_path, output_root, scenario_id)
    typical_summary = pd.read_csv(
        typical_outputs["summary_csv"],
        encoding="utf-8-sig",
    )
    annual_summary, contribution = annualize_typical_day_results(typical_summary)

    output_dir = Path(output_root) / "results" / "v2_annualized"
    output_dir.mkdir(parents=True, exist_ok=True)

    annual_summary_csv = output_dir / "annual_summary.csv"
    annual_summary_excel = output_dir / "annual_summary.xlsx"
    contribution_csv = output_dir / "typical_day_contribution.csv"
    contribution_excel = output_dir / "typical_day_contribution.xlsx"

    annual_summary.to_csv(annual_summary_csv, index=False, encoding="utf-8-sig")
    annual_summary.to_excel(annual_summary_excel, index=False)
    contribution.to_csv(contribution_csv, index=False, encoding="utf-8-sig")
    contribution.to_excel(contribution_excel, index=False)

    cost_png = plot_annual_cost_breakdown(
        annual_summary,
        output_dir / "annual_cost_breakdown.png",
    )
    carbon_png = plot_annual_carbon_by_typical_day(
        contribution,
        output_dir / "annual_carbon_by_typical_day.png",
    )
    energy_png = plot_annual_energy_by_typical_day(
        contribution,
        output_dir / "annual_energy_by_typical_day.png",
    )
    conclusion_md = export_annual_conclusion(
        annual_summary,
        contribution,
        output_dir / "annual_conclusion.md",
    )

    return {
        "typical_day_summary_csv": typical_outputs["summary_csv"],
        "annual_summary_csv": annual_summary_csv,
        "annual_summary_excel": annual_summary_excel,
        "typical_day_contribution_csv": contribution_csv,
        "typical_day_contribution_excel": contribution_excel,
        "annual_cost_breakdown_png": cost_png,
        "annual_carbon_by_typical_day_png": carbon_png,
        "annual_energy_by_typical_day_png": energy_png,
        "annual_conclusion_md": conclusion_md,
    }
