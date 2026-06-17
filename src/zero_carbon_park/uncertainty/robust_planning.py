"""最坏情形鲁棒容量规划。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib
import pandas as pd
from pyomo.environ import Constraint, Expression, NonNegativeReals, Objective, Set, Var, minimize, value

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
)
from zero_carbon_park.uncertainty.generator import generate_uncertainty_workbook


@dataclass(frozen=True)
class RobustDayConfig:
    """典型日与不确定性场景组合后的鲁棒规划配置。"""

    day_id: str
    name: str
    weight_days: float
    typical_day_id: str
    uncertainty_case_id: str
    uncertainty_case_name: str


def build_robust_typical_days(
    workbook: InputWorkbook,
    uncertainty_cases: list[UncertaintyCase] | None = None,
) -> list[tuple[RobustDayConfig, InputWorkbook]]:
    """构建每个不确定性场景都覆盖完整 365 天的鲁棒规划输入。"""

    cases = uncertainty_cases or get_default_uncertainty_cases()
    robust_days = []
    for typical_config in get_default_typical_days():
        typical_workbook = generate_typical_day_workbook(workbook, typical_config)
        for case in cases:
            robust_workbook = generate_uncertainty_workbook(typical_workbook, case)
            robust_config = RobustDayConfig(
                day_id=f"{typical_config.day_id}__{case.case_id}",
                name=f"{typical_config.name}-{case.name}",
                weight_days=typical_config.weight_days,
                typical_day_id=typical_config.day_id,
                uncertainty_case_id=case.case_id,
                uncertainty_case_name=case.name,
            )
            robust_days.append((robust_config, robust_workbook))
    return robust_days


def run_robust_capacity_planning(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, Path]:
    """运行最坏情形鲁棒容量规划。"""

    workbook = load_input_workbook(workbook_path)
    robust_days = build_robust_typical_days(workbook)
    model = build_capacity_planning_model(
        robust_days,
        get_default_planning_cost_params(),
    )
    _add_worst_case_objective(model, robust_days)

    status = solve_model(model)
    results = extract_capacity_planning_results(model, status)
    operation = _split_robust_operation(results["typical_day_operation"])
    hourly = _split_robust_operation(results["hourly"])
    case_results = _build_uncertainty_case_results(model, operation)
    summary = _build_robust_summary(model, status, robust_days, case_results)

    output_dir = Path(output_root) / "results" / "v4_robust_planning"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = _export_tables(
        summary,
        results["capacity"],
        case_results,
        operation,
        hourly,
        output_dir,
    )
    paths.update(_export_plots(results["capacity"], case_results, output_dir))
    paths["conclusion_md"] = _export_conclusion(
        summary,
        results["capacity"],
        case_results,
        output_dir / "conclusion.md",
    )
    return paths


def _add_worst_case_objective(model, robust_days) -> None:
    """用最坏场景年度总成本替换原容量规划目标函数。"""

    case_day_ids = {}
    for config, _ in robust_days:
        case_day_ids.setdefault(config.uncertainty_case_id, []).append(config.day_id)
    case_ids = list(case_day_ids)

    model.annual_total_cost.deactivate()
    model.U = Set(initialize=case_ids, ordered=True)
    model.worst_case_total_cost = Var(domain=NonNegativeReals)

    def daily_operation_cost(m, d):
        return sum(
            m.grid_buy[d, t] * m.grid_price[d, t]
            + m.gas_consumption[d, t] * m.gas_price[d, t]
            + (m.pv_curtail[d, t] + m.wind_curtail[d, t]) * m.curtail_penalty
            + m.carbon_emission[d, t] * m.carbon_price[d, t]
            + (m.battery_charge[d, t] + m.battery_discharge[d, t]) * m.battery_om
            + m.h2_production[d, t] * m.electrolyzer_om
            + m.h2_external_supply[d, t] * m.h2_external_supply_cost
            + m.fuel_cell_power[d, t] * m.fuel_cell_om
            for t in m.T
        )

    def robust_case_operation_cost_rule(m, u):
        return sum(m.weight_days[d] * daily_operation_cost(m, d) for d in case_day_ids[u])

    model.robust_case_operation_cost = Expression(
        model.U,
        rule=robust_case_operation_cost_rule,
    )

    def robust_case_total_cost_rule(m, u):
        return m.annualized_investment_cost + m.robust_case_operation_cost[u]

    model.robust_case_total_cost = Expression(model.U, rule=robust_case_total_cost_rule)

    def worst_case_cost_rule(m, u):
        return m.worst_case_total_cost >= m.robust_case_total_cost[u]

    model.worst_case_cost_constraint = Constraint(model.U, rule=worst_case_cost_rule)
    model.robust_objective = Objective(expr=model.worst_case_total_cost, sense=minimize)


def _split_robust_operation(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    split = result["typical_day_id"].str.split("__", n=1, expand=True)
    result["robust_day_id"] = result["typical_day_id"]
    result["typical_day_id"] = split[0]
    result["uncertainty_case_id"] = split[1]
    front = ["robust_day_id", "typical_day_id", "uncertainty_case_id"]
    remaining = [column for column in result.columns if column not in front]
    return result[front + remaining]


def _build_uncertainty_case_results(model, operation: pd.DataFrame) -> pd.DataFrame:
    rows = []
    investment_cost = float(value(model.annualized_investment_cost))
    for case_id, group in operation.groupby("uncertainty_case_id", sort=False):
        annual_operation_cost = float(group["weighted_total_cost_cny"].sum())
        annual_renewable_available = float(
            (group["renewable_available_kwh"] * group["weight_days"]).sum()
        )
        annual_renewable_used = float(
            (group["renewable_used_kwh"] * group["weight_days"]).sum()
        )
        rows.append(
            {
                "uncertainty_case_id": case_id,
                "annual_operation_cost_cny": annual_operation_cost,
                "annualized_investment_cost_cny": investment_cost,
                "annual_total_cost_cny": annual_operation_cost + investment_cost,
                "annual_grid_purchase_kwh": float(
                    group["weighted_grid_purchase_kwh"].sum()
                ),
                "annual_carbon_emission_kg": float(
                    group["weighted_carbon_emission_kg"].sum()
                ),
                "annual_renewable_available_kwh": annual_renewable_available,
                "annual_renewable_used_kwh": annual_renewable_used,
                "annual_renewable_consumption_rate": (
                    annual_renewable_used / annual_renewable_available
                    if annual_renewable_available > 0
                    else 0.0
                ),
                "annual_h2_external_supply_kg": float(
                    (group["h2_external_supply_kg"] * group["weight_days"]).sum()
                ),
            }
        )
    result = pd.DataFrame(rows)
    result["is_worst_case"] = (
        result["annual_total_cost_cny"] == result["annual_total_cost_cny"].max()
    )
    return result


def _build_robust_summary(
    model,
    status: str,
    robust_days,
    case_results: pd.DataFrame,
) -> pd.DataFrame:
    worst = case_results.sort_values("annual_total_cost_cny", ascending=False).iloc[0]
    normal = case_results[case_results["uncertainty_case_id"] == "NORMAL"].iloc[0]
    return pd.DataFrame(
        [
            {
                "robust_day_count": len(robust_days),
                "uncertainty_case_count": case_results["uncertainty_case_id"].nunique(),
                "status": status,
                "worst_case_id": worst["uncertainty_case_id"],
                "worst_case_total_cost_cny": float(worst["annual_total_cost_cny"]),
                "worst_case_operation_cost_cny": float(
                    worst["annual_operation_cost_cny"]
                ),
                "annualized_investment_cost_cny": float(
                    value(model.annualized_investment_cost)
                ),
                "normal_case_total_cost_cny": float(normal["annual_total_cost_cny"]),
                "worst_case_carbon_emission_kg": float(
                    worst["annual_carbon_emission_kg"]
                ),
                "worst_case_grid_purchase_kwh": float(
                    worst["annual_grid_purchase_kwh"]
                ),
                "worst_case_renewable_consumption_rate": float(
                    worst["annual_renewable_consumption_rate"]
                ),
                "worst_case_h2_external_supply_kg": float(
                    worst["annual_h2_external_supply_kg"]
                ),
            }
        ]
    )


def _export_tables(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    case_results: pd.DataFrame,
    operation: pd.DataFrame,
    hourly: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    summary_csv = output_dir / "robust_summary.csv"
    summary_excel = output_dir / "robust_summary.xlsx"
    capacity_csv = output_dir / "robust_capacity_result.csv"
    capacity_excel = output_dir / "robust_capacity_result.xlsx"
    case_csv = output_dir / "robust_uncertainty_case_results.csv"
    operation_csv = output_dir / "robust_uncertainty_operation.csv"
    hourly_csv = output_dir / "robust_hourly_results.csv"

    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary.to_excel(summary_excel, index=False)
    capacity.to_csv(capacity_csv, index=False, encoding="utf-8-sig")
    capacity.to_excel(capacity_excel, index=False)
    case_results.to_csv(case_csv, index=False, encoding="utf-8-sig")
    operation.to_csv(operation_csv, index=False, encoding="utf-8-sig")
    hourly.to_csv(hourly_csv, index=False, encoding="utf-8-sig")

    return {
        "robust_summary_csv": summary_csv,
        "robust_summary_excel": summary_excel,
        "robust_capacity_result_csv": capacity_csv,
        "robust_capacity_result_excel": capacity_excel,
        "robust_uncertainty_case_results_csv": case_csv,
        "robust_uncertainty_operation_csv": operation_csv,
        "robust_hourly_results_csv": hourly_csv,
    }


def _export_plots(
    capacity: pd.DataFrame,
    case_results: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    _configure_font()
    paths = {
        "robust_capacity_mix_png": output_dir / "robust_capacity_mix.png",
        "robust_worst_case_cost_png": output_dir / "robust_worst_case_cost.png",
        "robust_uncertainty_carbon_png": output_dir / "robust_uncertainty_carbon.png",
    }

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(capacity["capacity_variable"], capacity["capacity_value"])
    ax.set_title("鲁棒容量规划最优容量")
    ax.set_ylabel("容量")
    ax.tick_params(axis="x", labelrotation=40)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["robust_capacity_mix_png"], dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = [
        "#d55e00" if is_worst else "#0072b2"
        for is_worst in case_results["is_worst_case"]
    ]
    ax.bar(
        case_results["uncertainty_case_id"],
        case_results["annual_total_cost_cny"],
        color=colors,
    )
    ax.set_title("鲁棒规划各不确定性场景年度总成本")
    ax.set_xlabel("不确定性场景")
    ax.set_ylabel("年度总成本/元")
    ax.tick_params(axis="x", labelrotation=30)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["robust_worst_case_cost_png"], dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(
        case_results["uncertainty_case_id"],
        case_results["annual_carbon_emission_kg"],
    )
    ax.set_title("鲁棒规划各不确定性场景年度碳排放")
    ax.set_xlabel("不确定性场景")
    ax.set_ylabel("年度碳排放/kgCO2")
    ax.tick_params(axis="x", labelrotation=30)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["robust_uncertainty_carbon_png"], dpi=150)
    plt.close(fig)

    return paths


def _export_conclusion(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    case_results: pd.DataFrame,
    output_path: Path,
) -> Path:
    row = summary.iloc[0]
    cap = capacity.set_index("capacity_variable")["capacity_value"]
    cases = case_results.sort_values("annual_total_cost_cny", ascending=False)
    worst = cases.iloc[0]
    normal = case_results[case_results["uncertainty_case_id"] == "NORMAL"].iloc[0]

    text = f"""# 最坏情形鲁棒容量规划结论

## 1. 分析范围

本次鲁棒规划将夏季、冬季、过渡季三个典型日与六个不确定性场景组合，共 {int(row['robust_day_count'])} 个运行场景。每一个不确定性场景均按 365 天年化，容量变量在所有场景中共享，目标函数最小化最坏场景年度总成本。

## 2. 年度结果

- 求解状态：{row['status']}
- 最坏场景：{row['worst_case_id']}
- 最坏场景年度总成本：{row['worst_case_total_cost_cny']:.2f} 元
- 正常场景年度总成本：{row['normal_case_total_cost_cny']:.2f} 元
- 年化投资成本：{row['annualized_investment_cost_cny']:.2f} 元
- 最坏场景年度碳排放：{row['worst_case_carbon_emission_kg']:.2f} kgCO2
- 最坏场景新能源消纳率：{row['worst_case_renewable_consumption_rate']:.2%}
- 最坏场景外部补氢量：{row['worst_case_h2_external_supply_kg']:.2f} kg

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

最坏情形为 {worst['uncertainty_case_id']}，年度总成本高于正常场景 {worst['annual_total_cost_cny'] - normal['annual_total_cost_cny']:.2f} 元。该结果反映了鲁棒规划的核心作用：牺牲部分正常场景经济性，换取极端或不利场景下更可控的年度成本上界。
"""
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _configure_font() -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
