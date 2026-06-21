"""固定容量不确定性压力测试。"""

from __future__ import annotations

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
)
from zero_carbon_park.uncertainty.generator import generate_uncertainty_workbook


CAPACITY_VARIABLES = [
    "wind_capacity_kw",
    "pv_capacity_kw",
    "battery_power_capacity_kw",
    "battery_energy_capacity_kwh",
    "electrolyzer_power_capacity_kw",
    "h2_storage_capacity_kg",
    "fuel_cell_power_capacity_kw",
    "heat_pump_power_capacity_kw",
]


def run_uncertainty_stress_test(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
    uncertainty_case_ids: list[str] | None = None,
    enforce_green_power_share: bool = True,
) -> dict[str, Path]:
    """固定容量规划结果，运行不确定性压力测试。"""

    workbook = load_input_workbook(workbook_path)
    if not enforce_green_power_share:
        workbook = _with_green_power_share(workbook, 0.0)
    cost_params = get_default_planning_cost_params()
    typical_configs = get_default_typical_days()

    baseline_typical_days = [
        (config, generate_typical_day_workbook(workbook, config))
        for config in typical_configs
    ]
    baseline_model = build_capacity_planning_model(baseline_typical_days, cost_params)
    baseline_status = solve_model(baseline_model)
    baseline_results = extract_capacity_planning_results(baseline_model, baseline_status)
    reference_capacity = baseline_results["capacity"].copy()
    fixed_capacity = _capacity_dict(reference_capacity)

    cases = _select_cases(uncertainty_case_ids)
    summary_frames = []
    operation_frames = []
    hourly_frames = []

    for case in cases:
        stressed_typical_days = []
        for config in typical_configs:
            day_workbook = generate_typical_day_workbook(workbook, config)
            stressed_workbook = generate_uncertainty_workbook(day_workbook, case)
            stressed_typical_days.append((config, stressed_workbook))

        model = build_capacity_planning_model(stressed_typical_days, cost_params)
        _fix_capacity_variables(model, fixed_capacity)
        status = solve_model(model)
        results = extract_capacity_planning_results(model, status)

        summary = results["summary"].copy()
        summary.insert(0, "uncertainty_case_id", case.case_id)
        summary.insert(1, "uncertainty_case_name", case.name)
        summary.insert(2, "probability", case.probability)
        summary_frames.append(summary)

        operation = results["typical_day_operation"].copy()
        operation.insert(0, "uncertainty_case_id", case.case_id)
        operation.insert(1, "uncertainty_case_name", case.name)
        operation_frames.append(operation)

        hourly = results["hourly"].copy()
        hourly.insert(0, "uncertainty_case_id", case.case_id)
        hourly.insert(1, "uncertainty_case_name", case.name)
        hourly_frames.append(hourly)

    summary = pd.concat(summary_frames, ignore_index=True)
    operation = pd.concat(operation_frames, ignore_index=True)
    hourly = pd.concat(hourly_frames, ignore_index=True)
    summary = _add_normal_deltas(summary)

    output_dir = Path(output_root) / "results" / "v4_uncertainty_stress_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = _export_tables(summary, operation, hourly, reference_capacity, output_dir)
    paths.update(_export_plots(summary, output_dir))
    paths["conclusion_md"] = _export_conclusion(summary, output_dir / "conclusion.md")
    return paths


def _with_green_power_share(workbook: InputWorkbook, value: float) -> InputWorkbook:
    economic = workbook.economic_params.copy(deep=True)
    mask = economic["parameter"] == "green_power_min_share"
    if mask.any():
        economic.loc[mask, "value"] = value
    else:
        economic = pd.concat(
            [
                economic,
                pd.DataFrame(
                    [
                        {
                            "category": "政策约束",
                            "parameter": "green_power_min_share",
                            "value": value,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    return InputWorkbook(
        timeseries=workbook.timeseries,
        device_params=workbook.device_params,
        economic_params=economic,
        scenarios=workbook.scenarios,
    )


def _select_cases(case_ids: list[str] | None) -> list[UncertaintyCase]:
    cases = get_default_uncertainty_cases()
    if case_ids is None:
        return cases
    selected = [case for case in cases if case.case_id in set(case_ids)]
    if len(selected) != len(case_ids):
        found = {case.case_id for case in selected}
        missing = [case_id for case_id in case_ids if case_id not in found]
        raise ValueError(f"未知不确定性场景：{missing}")
    return selected


def _capacity_dict(capacity: pd.DataFrame) -> dict[str, float]:
    return {
        row["capacity_variable"]: float(row["capacity_value"])
        for _, row in capacity.iterrows()
    }


def _fix_capacity_variables(model, capacity: dict[str, float]) -> None:
    for variable_name in CAPACITY_VARIABLES:
        getattr(model, variable_name).fix(capacity[variable_name])


def _add_normal_deltas(summary: pd.DataFrame) -> pd.DataFrame:
    summary = summary.copy()
    if "NORMAL" in set(summary["uncertainty_case_id"]):
        normal = summary[summary["uncertainty_case_id"] == "NORMAL"].iloc[0]
    else:
        normal = summary.iloc[0]

    normal_cost = float(normal["annual_total_cost_cny"])
    normal_carbon = float(normal["annual_carbon_emission_kg"])
    summary["cost_increase_vs_normal_pct"] = (
        (summary["annual_total_cost_cny"] - normal_cost) / normal_cost * 100.0
    )
    summary["carbon_increase_vs_normal_pct"] = (
        (summary["annual_carbon_emission_kg"] - normal_carbon)
        / normal_carbon
        * 100.0
    )
    return summary


def _export_tables(
    summary: pd.DataFrame,
    operation: pd.DataFrame,
    hourly: pd.DataFrame,
    reference_capacity: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    summary_csv = output_dir / "stress_summary.csv"
    summary_excel = output_dir / "stress_summary.xlsx"
    operation_csv = output_dir / "stress_typical_day_operation.csv"
    hourly_csv = output_dir / "stress_hourly_results.csv"
    capacity_csv = output_dir / "reference_capacity.csv"

    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary.to_excel(summary_excel, index=False)
    operation.to_csv(operation_csv, index=False, encoding="utf-8-sig")
    hourly.to_csv(hourly_csv, index=False, encoding="utf-8-sig")
    reference_capacity.to_csv(capacity_csv, index=False, encoding="utf-8-sig")
    return {
        "stress_summary_csv": summary_csv,
        "stress_summary_excel": summary_excel,
        "stress_typical_day_operation_csv": operation_csv,
        "stress_hourly_results_csv": hourly_csv,
        "reference_capacity_csv": capacity_csv,
    }


def _export_plots(summary: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    _configure_font()
    paths = {
        "stress_cost_carbon_png": output_dir / "stress_cost_carbon.png",
        "stress_external_h2_png": output_dir / "stress_external_h2.png",
    }

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.bar(
        summary["uncertainty_case_id"],
        summary["annual_total_cost_cny"],
        alpha=0.75,
        label="年度总成本",
    )
    ax1.set_ylabel("年度总成本/元")
    ax1.tick_params(axis="x", labelrotation=30)
    ax2 = ax1.twinx()
    ax2.plot(
        summary["uncertainty_case_id"],
        summary["annual_carbon_emission_kg"],
        marker="o",
        color="tab:red",
        label="年度碳排放",
    )
    ax2.set_ylabel("年度碳排放/kgCO2")
    ax1.set_title("不确定性压力场景成本与碳排放")
    ax1.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["stress_cost_carbon_png"], dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(
        summary["uncertainty_case_id"],
        summary["annual_h2_external_supply_kg"],
    )
    ax.set_title("不确定性压力场景外部补氢量")
    ax.set_xlabel("不确定性场景")
    ax.set_ylabel("年度外部补氢量/kg")
    ax.tick_params(axis="x", labelrotation=30)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(paths["stress_external_h2_png"], dpi=150)
    plt.close(fig)
    return paths


def _export_conclusion(summary: pd.DataFrame, output_path: Path) -> Path:
    worst_cost = summary.loc[summary["annual_total_cost_cny"].idxmax()]
    worst_carbon = summary.loc[summary["annual_carbon_emission_kg"].idxmax()]
    worst_h2 = summary.loc[summary["annual_h2_external_supply_kg"].idxmax()]

    text = f"""# 不确定性压力测试结论

## 1. 分析范围

本次压力测试先使用多典型日容量规划模型得到基准最优容量，然后固定该容量，在不同风光和负荷扰动场景下重新运行调度。该分析用于检验当前容量配置面对预测误差时的成本、碳排放和供氢压力。

## 2. 关键结果

- 场景数量：{len(summary)} 个。
- 年度总成本最高场景：{worst_cost['uncertainty_case_id']}，成本为 {worst_cost['annual_total_cost_cny']:.2f} 元。
- 年度碳排放最高场景：{worst_carbon['uncertainty_case_id']}，碳排放为 {worst_carbon['annual_carbon_emission_kg']:.2f} kgCO2。
- 年度外部补氢最高场景：{worst_h2['uncertainty_case_id']}，外部补氢量为 {worst_h2['annual_h2_external_supply_kg']:.2f} kg。

## 3. 说明

压力测试不是重新优化容量，而是评估当前容量规划方案在不确定性下的承压能力。如果某些场景出现明显成本增加、碳排放上升或外部补氢增加，说明后续随机优化或鲁棒优化应重点提高这些场景下的灵活性和保供能力。
"""
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _configure_font() -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
