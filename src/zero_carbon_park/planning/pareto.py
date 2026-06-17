"""容量规划成本-碳排放 Pareto 分析。"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import get_default_planning_cost_params
from zero_carbon_park.planning.results import extract_capacity_planning_results
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


DEFAULT_CARBON_CAP_RATIOS = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4]


def run_cost_carbon_pareto_analysis(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
    carbon_cap_ratios: list[float] | None = None,
) -> dict[str, Path]:
    """运行成本-碳排放 Pareto 分析。"""

    ratios = carbon_cap_ratios or DEFAULT_CARBON_CAP_RATIOS
    if any(ratio <= 0 for ratio in ratios):
        raise ValueError("碳排放上限比例必须大于 0")

    workbook = load_input_workbook(workbook_path)
    typical_days = [
        (config, generate_typical_day_workbook(workbook, config))
        for config in get_default_typical_days()
    ]
    cost_params = get_default_planning_cost_params()

    baseline_model = build_capacity_planning_model(typical_days, cost_params)
    baseline_status = solve_model(baseline_model)
    baseline_results = extract_capacity_planning_results(baseline_model, baseline_status)
    baseline_summary = baseline_results["summary"].iloc[0]
    baseline_carbon = float(baseline_summary["annual_carbon_emission_kg"])
    baseline_cost = float(baseline_summary["annual_total_cost_cny"])

    summary_frames = []
    capacity_frames = []
    hourly_frames = []

    for ratio in ratios:
        case_id = f"CARBON_CAP_{int(ratio * 100):03d}"
        carbon_cap = baseline_carbon * ratio
        model = build_capacity_planning_model(
            typical_days,
            cost_params,
            annual_carbon_emission_cap_kg=carbon_cap,
        )
        status = solve_model(model)
        results = extract_capacity_planning_results(model, status)

        summary = results["summary"].copy()
        summary.insert(0, "case_id", case_id)
        summary.insert(1, "carbon_cap_ratio", ratio)
        summary.insert(2, "annual_carbon_cap_kg", carbon_cap)
        actual_carbon = summary.loc[0, "annual_carbon_emission_kg"]
        actual_cost = summary.loc[0, "annual_total_cost_cny"]
        summary["cost_increase_vs_baseline_pct"] = (
            (actual_cost - baseline_cost) / baseline_cost * 100.0
        )
        summary["carbon_reduction_vs_baseline_pct"] = (
            (baseline_carbon - actual_carbon) / baseline_carbon * 100.0
        )
        summary_frames.append(summary)

        capacity = results["capacity"].copy()
        capacity.insert(0, "case_id", case_id)
        capacity.insert(1, "carbon_cap_ratio", ratio)
        capacity_frames.append(capacity)

        hourly = results["hourly"].copy()
        hourly.insert(0, "case_id", case_id)
        hourly.insert(1, "carbon_cap_ratio", ratio)
        hourly_frames.append(hourly)

    summary = pd.concat(summary_frames, ignore_index=True)
    capacity = pd.concat(capacity_frames, ignore_index=True)
    hourly = pd.concat(hourly_frames, ignore_index=True)

    output_dir = Path(output_root) / "results" / "v3_pareto_cost_carbon"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _export_tables(summary, capacity, hourly, output_dir)
    paths.update(_export_plots(summary, capacity, output_dir))
    paths["conclusion_md"] = _export_conclusion(summary, output_dir / "conclusion.md")
    return paths


def _export_tables(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    hourly: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    summary_csv = output_dir / "pareto_summary.csv"
    summary_excel = output_dir / "pareto_summary.xlsx"
    capacity_csv = output_dir / "pareto_capacity_results.csv"
    capacity_excel = output_dir / "pareto_capacity_results.xlsx"
    hourly_csv = output_dir / "pareto_hourly_results.csv"

    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary.to_excel(summary_excel, index=False)
    capacity.to_csv(capacity_csv, index=False, encoding="utf-8-sig")
    capacity.to_excel(capacity_excel, index=False)
    hourly.to_csv(hourly_csv, index=False, encoding="utf-8-sig")
    return {
        "pareto_summary_csv": summary_csv,
        "pareto_summary_excel": summary_excel,
        "pareto_capacity_results_csv": capacity_csv,
        "pareto_capacity_results_excel": capacity_excel,
        "pareto_hourly_results_csv": hourly_csv,
    }


def _export_plots(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    _configure_font()
    paths = {
        "cost_carbon_pareto_curve_png": output_dir / "cost_carbon_pareto_curve.png",
        "capacity_mix_pareto_png": output_dir / "capacity_mix_pareto.png",
        "renewable_consumption_pareto_png": output_dir
        / "renewable_consumption_pareto.png",
    }

    ordered = summary.sort_values("annual_carbon_emission_kg")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(
        ordered["annual_carbon_emission_kg"],
        ordered["annual_total_cost_cny"],
        marker="o",
    )
    for _, row in ordered.iterrows():
        ax.annotate(
            f"{row['carbon_cap_ratio']:.0%}",
            (row["annual_carbon_emission_kg"], row["annual_total_cost_cny"]),
            textcoords="offset points",
            xytext=(5, 5),
        )
    ax.set_title("成本-碳排放 Pareto 曲线")
    ax.set_xlabel("年度碳排放/kgCO2")
    ax.set_ylabel("年度总成本/元")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["cost_carbon_pareto_curve_png"], dpi=150)
    plt.close(fig)

    selected = capacity[
        capacity["capacity_variable"].isin(
            [
                "wind_capacity_kw",
                "pv_capacity_kw",
                "battery_energy_capacity_kwh",
                "electrolyzer_power_capacity_kw",
                "heat_pump_power_capacity_kw",
            ]
        )
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    for variable_name, data in selected.groupby("capacity_variable"):
        ordered_data = data.sort_values("carbon_cap_ratio", ascending=False)
        ax.plot(
            ordered_data["carbon_cap_ratio"],
            ordered_data["capacity_value"],
            marker="o",
            label=variable_name,
        )
    ax.set_title("碳约束强度-容量配置变化")
    ax.set_xlabel("碳排放上限比例")
    ax.set_ylabel("容量")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(paths["capacity_mix_pareto_png"], dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    sorted_summary = summary.sort_values("carbon_cap_ratio", ascending=False)
    ax.plot(
        sorted_summary["carbon_cap_ratio"],
        sorted_summary["annual_renewable_consumption_rate"],
        marker="o",
    )
    ax.set_title("碳约束强度-新能源消纳率")
    ax.set_xlabel("碳排放上限比例")
    ax.set_ylabel("新能源消纳率")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["renewable_consumption_pareto_png"], dpi=150)
    plt.close(fig)
    return paths


def _export_conclusion(summary: pd.DataFrame, output_path: Path) -> Path:
    feasible = summary[summary["status"] == "optimal"].copy()
    strongest = feasible.sort_values("carbon_cap_ratio").iloc[0]
    baseline = feasible.sort_values("carbon_cap_ratio", ascending=False).iloc[0]
    text = f"""# 成本-碳排放 Pareto 分析结论

## 1. 分析范围

本次分析采用 epsilon-constraint 方法，以年度总成本最小为主目标，并设置年度碳排放上限，观察不同低碳目标下的成本和容量配置变化。

## 2. 关键结果

- 基准碳约束比例：{baseline['carbon_cap_ratio']:.0%}
- 基准年度总成本：{baseline['annual_total_cost_cny']:.2f} 元
- 基准年度碳排放：{baseline['annual_carbon_emission_kg']:.2f} kgCO2
- 最严格可行碳约束比例：{strongest['carbon_cap_ratio']:.0%}
- 最严格可行场景年度总成本：{strongest['annual_total_cost_cny']:.2f} 元
- 最严格可行场景年度碳排放：{strongest['annual_carbon_emission_kg']:.2f} kgCO2
- 相对基准成本增幅：{strongest['cost_increase_vs_baseline_pct']:.2f}%
- 相对基准减排比例：{strongest['carbon_reduction_vs_baseline_pct']:.2f}%

## 3. 说明

Pareto 曲线用于展示成本和碳排放之间的权衡关系。如果碳约束持续收紧后成本快速上升，说明系统已接近当前资源和设备参数下的低碳经济边界，需要通过更多低碳电源、灵活性资源或工程约束优化继续降低减排成本。
"""
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _configure_font() -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
