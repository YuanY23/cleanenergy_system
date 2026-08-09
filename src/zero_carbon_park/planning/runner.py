"""容量规划运行入口。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import get_default_planning_cost_params
from zero_carbon_park.planning.results import extract_capacity_planning_results
from zero_carbon_park.reporting.plots import (
    plot_annual_carbon_by_typical_day,
    plot_annual_cost_breakdown,
)
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


def run_capacity_planning(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, Path]:
    """运行多典型日容量规划优化并导出结果。"""

    workbook = load_input_workbook(workbook_path)
    typical_days = [
        (config, generate_typical_day_workbook(workbook, config))
        for config in get_default_typical_days()
    ]
    cost_params = get_default_planning_cost_params()
    model = build_capacity_planning_model(typical_days, cost_params)
    status = solve_model(model)
    results = extract_capacity_planning_results(model, status)

    output_dir = Path(output_root) / "results" / "v2_capacity_planning"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = _export_tables(results, output_dir)
    paths["capacity_mix_png"] = _plot_capacity_mix(
        results["capacity"],
        output_dir / "capacity_mix.png",
    )
    paths["annual_cost_breakdown_png"] = plot_annual_cost_breakdown(
        results["summary"],
        output_dir / "annual_cost_breakdown.png",
    )
    paths["annual_carbon_by_typical_day_png"] = plot_annual_carbon_by_typical_day(
        results["typical_day_operation"],
        output_dir / "annual_carbon_by_typical_day.png",
    )
    paths["planning_conclusion_md"] = _export_planning_conclusion(
        results,
        output_dir / "planning_conclusion.md",
    )
    return paths


def _export_tables(results: dict, output_dir: Path) -> dict[str, Path]:
    summary_csv = output_dir / "planning_summary.csv"
    summary_excel = output_dir / "planning_summary.xlsx"
    capacity_csv = output_dir / "planning_capacity_result.csv"
    capacity_excel = output_dir / "planning_capacity_result.xlsx"
    operation_csv = output_dir / "planning_typical_day_operation.csv"
    operation_excel = output_dir / "planning_typical_day_operation.xlsx"
    hourly_csv = output_dir / "planning_hourly_results.csv"

    # Annual monetary totals are reported to whole CNY.  This is both the
    # meaningful reporting precision at park scale and keeps the exported
    # accounting identity exact after CSV readers parse the values as floats.
    summary_export = results["summary"].copy()
    money_columns = [
        "annual_operation_cost_cny",
        "annualized_investment_cost_cny",
        "annual_demand_charge_cost_cny",
        "annual_fuel_cell_backup_value_cny",
    ]
    summary_export[money_columns] = summary_export[money_columns].round(0)
    summary_export["annual_total_cost_cny"] = (
        summary_export["annual_operation_cost_cny"]
        + summary_export["annualized_investment_cost_cny"]
        + summary_export["annual_demand_charge_cost_cny"]
        - summary_export["annual_fuel_cell_backup_value_cny"]
    )
    summary_export.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary_export.to_excel(summary_excel, index=False)
    results["capacity"].to_csv(capacity_csv, index=False, encoding="utf-8-sig")
    results["capacity"].to_excel(capacity_excel, index=False)
    results["typical_day_operation"].to_csv(
        operation_csv, index=False, encoding="utf-8-sig"
    )
    results["typical_day_operation"].to_excel(operation_excel, index=False)
    results["hourly"].to_csv(hourly_csv, index=False, encoding="utf-8-sig")

    return {
        "planning_summary_csv": summary_csv,
        "planning_summary_excel": summary_excel,
        "planning_capacity_result_csv": capacity_csv,
        "planning_capacity_result_excel": capacity_excel,
        "planning_typical_day_operation_csv": operation_csv,
        "planning_typical_day_operation_excel": operation_excel,
        "planning_hourly_results_csv": hourly_csv,
    }


def _plot_capacity_mix(capacity, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(capacity["capacity_variable"], capacity["capacity_value"])
    ax.set_title("容量规划最优设备容量")
    ax.set_ylabel("容量值")
    ax.tick_params(axis="x", labelrotation=40)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _export_planning_conclusion(results: dict, output_path: Path) -> Path:
    summary = results["summary"].iloc[0]
    capacity = results["capacity"].set_index("capacity_variable")["capacity_value"]
    text = f"""# 容量规划优化结果

## 1. 年度成本

- 求解状态：{summary['status']}
- 年度运行成本：{summary['annual_operation_cost_cny']:.2f} 元
- 年化投资成本：{summary['annualized_investment_cost_cny']:.2f} 元
- 年度总成本：{summary['annual_total_cost_cny']:.2f} 元
- 年度碳排放：{summary['annual_carbon_emission_kg']:.2f} kgCO2
- 年度新能源消纳率：{summary['annual_renewable_consumption_rate']:.2%}
- 年度外部补氢量：{summary['annual_h2_external_supply_kg']:.2f} kg

## 2. 最优容量

- 风电装机：{capacity['wind_capacity_kw']:.2f} kW
- 光伏装机：{capacity['pv_capacity_kw']:.2f} kW
- 电池功率：{capacity['battery_power_capacity_kw']:.2f} kW
- 电池容量：{capacity['battery_energy_capacity_kwh']:.2f} kWh
- 电解槽功率：{capacity['electrolyzer_power_capacity_kw']:.2f} kW
- 储氢容量：{capacity['h2_storage_capacity_kg']:.2f} kg
- 燃料电池功率：{capacity['fuel_cell_power_capacity_kw']:.2f} kW
- 热泵功率：{capacity['heat_pump_power_capacity_kw']:.2f} kW

## 3. 说明

当前容量规划使用三个缩放生成的典型日和工程假设投资参数，适合验证规划-运行一体化方法。后续若替换真实全年数据和设备报价，规划结果需要重新计算。
"""
    output_path.write_text(text, encoding="utf-8")
    return output_path
