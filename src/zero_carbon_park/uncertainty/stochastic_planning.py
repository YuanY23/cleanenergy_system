"""场景概率加权随机容量规划。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zero_carbon_park.data.loader import InputWorkbook, load_input_workbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import get_default_planning_cost_params
from zero_carbon_park.planning.results import extract_capacity_planning_results
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook
from zero_carbon_park.uncertainty.definitions import (
    UncertaintyCase,
    get_default_uncertainty_cases,
    select_uncertainty_cases,
)
from zero_carbon_park.uncertainty.generator import generate_uncertainty_workbook


@dataclass(frozen=True)
class StochasticDayConfig:
    """典型日与不确定性场景组合后的配置。"""

    day_id: str
    name: str
    weight_days: float
    typical_day_id: str
    uncertainty_case_id: str
    uncertainty_case_name: str
    uncertainty_probability: float


def build_stochastic_typical_days(
    workbook: InputWorkbook,
    uncertainty_cases: list[UncertaintyCase] | None = None,
) -> list[tuple[StochasticDayConfig, InputWorkbook]]:
    """构建“典型日 × 不确定性场景”的随机规划输入。"""

    cases = uncertainty_cases or get_default_uncertainty_cases()
    probability_sum = sum(case.probability for case in cases)
    if probability_sum <= 0:
        raise ValueError("不确定性场景概率之和必须大于 0")
    stochastic_days = []
    for typical_config in get_default_typical_days():
        typical_workbook = generate_typical_day_workbook(workbook, typical_config)
        for case in cases:
            normalized_probability = case.probability / probability_sum
            stochastic_workbook = generate_uncertainty_workbook(typical_workbook, case)
            stochastic_config = StochasticDayConfig(
                day_id=f"{typical_config.day_id}__{case.case_id}",
                name=f"{typical_config.name}-{case.name}",
                weight_days=typical_config.weight_days * normalized_probability,
                typical_day_id=typical_config.day_id,
                uncertainty_case_id=case.case_id,
                uncertainty_case_name=case.name,
                uncertainty_probability=normalized_probability,
            )
            stochastic_days.append((stochastic_config, stochastic_workbook))
    return stochastic_days


def run_stochastic_capacity_planning(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
    uncertainty_case_ids: list[str] | None = None,
) -> dict[str, Path]:
    """运行场景概率加权随机容量规划。"""

    workbook = load_input_workbook(workbook_path)
    uncertainty_cases = select_uncertainty_cases(uncertainty_case_ids)
    stochastic_days = build_stochastic_typical_days(workbook, uncertainty_cases)
    model = build_capacity_planning_model(
        stochastic_days,
        get_default_planning_cost_params(),
    )
    status = solve_model(model)
    results = extract_capacity_planning_results(model, status)

    operation = _split_stochastic_operation(results["typical_day_operation"])
    hourly = _split_stochastic_operation(results["hourly"])
    summary = results["summary"].copy()
    summary.insert(0, "stochastic_day_count", len(stochastic_days))
    summary.insert(1, "uncertainty_case_count", len(uncertainty_cases))

    output_dir = Path(output_root) / "results" / "v4_stochastic_planning"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = _export_tables(summary, results["capacity"], operation, hourly, output_dir)
    paths.update(_export_plots(summary, results["capacity"], operation, output_dir))
    paths["conclusion_md"] = _export_conclusion(
        summary,
        results["capacity"],
        operation,
        output_dir / "conclusion.md",
    )
    return paths


def _split_stochastic_operation(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    split = result["typical_day_id"].str.split("__", n=1, expand=True)
    result["stochastic_day_id"] = result["typical_day_id"]
    result["typical_day_id"] = split[0]
    result["uncertainty_case_id"] = split[1]
    front = ["stochastic_day_id", "typical_day_id", "uncertainty_case_id"]
    remaining = [column for column in result.columns if column not in front]
    return result[front + remaining]


def _export_tables(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    operation: pd.DataFrame,
    hourly: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    summary_csv = output_dir / "stochastic_summary.csv"
    summary_excel = output_dir / "stochastic_summary.xlsx"
    capacity_csv = output_dir / "stochastic_capacity_result.csv"
    capacity_excel = output_dir / "stochastic_capacity_result.xlsx"
    operation_csv = output_dir / "stochastic_typical_uncertainty_operation.csv"
    hourly_csv = output_dir / "stochastic_hourly_results.csv"

    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary.to_excel(summary_excel, index=False)
    capacity.to_csv(capacity_csv, index=False, encoding="utf-8-sig")
    capacity.to_excel(capacity_excel, index=False)
    operation.to_csv(operation_csv, index=False, encoding="utf-8-sig")
    hourly.to_csv(hourly_csv, index=False, encoding="utf-8-sig")

    return {
        "stochastic_summary_csv": summary_csv,
        "stochastic_summary_excel": summary_excel,
        "stochastic_capacity_result_csv": capacity_csv,
        "stochastic_capacity_result_excel": capacity_excel,
        "stochastic_typical_uncertainty_operation_csv": operation_csv,
        "stochastic_hourly_results_csv": hourly_csv,
    }


def _export_plots(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    operation: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    _configure_font()
    paths = {
        "stochastic_capacity_mix_png": output_dir / "stochastic_capacity_mix.png",
        "stochastic_cost_breakdown_png": output_dir / "stochastic_cost_breakdown.png",
        "stochastic_uncertainty_cost_png": output_dir / "stochastic_uncertainty_cost.png",
    }

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(capacity["capacity_variable"], capacity["capacity_value"])
    ax.set_title("随机容量规划最优容量")
    ax.set_ylabel("容量")
    ax.tick_params(axis="x", labelrotation=40)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["stochastic_capacity_mix_png"], dpi=150)
    plt.close(fig)

    row = summary.iloc[0]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(
        ["年度运行成本", "年化投资成本"],
        [
            float(row["annual_operation_cost_cny"]),
            float(row["annualized_investment_cost_cny"]),
        ],
    )
    ax.set_title("随机容量规划年度成本构成")
    ax.set_ylabel("成本/元")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["stochastic_cost_breakdown_png"], dpi=150)
    plt.close(fig)

    grouped = (
        operation.groupby("uncertainty_case_id")["weighted_total_cost_cny"]
        .sum()
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(grouped["uncertainty_case_id"], grouped["weighted_total_cost_cny"])
    ax.set_title("不确定性场景期望成本贡献")
    ax.set_xlabel("不确定性场景")
    ax.set_ylabel("加权年度运行成本/元")
    ax.tick_params(axis="x", labelrotation=30)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["stochastic_uncertainty_cost_png"], dpi=150)
    plt.close(fig)
    return paths


def _export_conclusion(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    operation: pd.DataFrame,
    output_path: Path,
) -> Path:
    row = summary.iloc[0]
    cap = capacity.set_index("capacity_variable")["capacity_value"]
    contribution = (
        operation.groupby("uncertainty_case_id")["weighted_total_cost_cny"]
        .sum()
        .sort_values(ascending=False)
    )
    top_case = contribution.index[0]
    top_cost = contribution.iloc[0]

    text = f"""# 场景概率加权随机容量规划结论

## 1. 分析范围

本次随机规划将夏季、冬季、过渡季三个典型日与六个不确定性场景组合，共 {int(row['stochastic_day_count'])} 个加权运行场景。容量变量在所有场景中共享，运行变量按场景展开，目标函数最小化年化投资成本与概率加权年度运行成本之和。

## 2. 年度结果

- 求解状态：{row['status']}
- 年度运行成本：{row['annual_operation_cost_cny']:.2f} 元
- 年化投资成本：{row['annualized_investment_cost_cny']:.2f} 元
- 年度总成本：{row['annual_total_cost_cny']:.2f} 元
- 年度碳排放：{row['annual_carbon_emission_kg']:.2f} kgCO2
- 新能源消纳率：{row['annual_renewable_consumption_rate']:.2%}
- 外部补氢量：{row['annual_h2_external_supply_kg']:.2f} kg

## 3. 最优容量

- 风电装机：{cap['wind_capacity_kw']:.2f} kW
- 光伏装机：{cap['pv_capacity_kw']:.2f} kW
- 电池功率：{cap['battery_power_capacity_kw']:.2f} kW
- 电池容量：{cap['battery_energy_capacity_kwh']:.2f} kWh
- 电解槽功率：{cap['electrolyzer_power_capacity_kw']:.2f} kW
- 储氢容量：{cap['h2_storage_capacity_kg']:.2f} kg
- 燃料电池功率：{cap['fuel_cell_power_capacity_kw']:.2f} kW
- 热泵功率：{cap['heat_pump_power_capacity_kw']:.2f} kW

## 4. 说明

加权运行成本贡献最高的不确定性场景为 {top_case}，贡献约 {top_cost:.2f} 元。该结果说明随机规划已经开始把预测误差纳入容量决策，相比确定性容量规划更适合评估平均意义下的工程运行表现。
"""
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _configure_font() -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
