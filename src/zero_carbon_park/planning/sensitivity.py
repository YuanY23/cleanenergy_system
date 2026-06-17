"""容量规划投资参数敏感性分析。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import (
    PlanningCostParams,
    get_default_planning_cost_params,
)
from zero_carbon_park.planning.results import extract_capacity_planning_results
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


CAPEX_GROUPS = [
    "WIND",
    "PV",
    "BATTERY",
    "ELECTROLYZER",
    "H2_STORAGE",
    "FUEL_CELL",
    "HEAT_PUMP",
]
DEFAULT_CAPEX_MULTIPLIERS = [0.5, 0.75, 1.0, 1.25, 1.5]


@dataclass(frozen=True)
class InvestmentSensitivityCase:
    """单个投资成本敏感性场景。"""

    case_id: str
    capex_group: str
    capex_multiplier: float


def get_default_investment_sensitivity_cases() -> list[InvestmentSensitivityCase]:
    """返回默认投资敏感性场景。"""

    cases = []
    for group in CAPEX_GROUPS:
        for multiplier in DEFAULT_CAPEX_MULTIPLIERS:
            cases.append(
                InvestmentSensitivityCase(
                    case_id=f"{group}_{int(multiplier * 100):03d}",
                    capex_group=group,
                    capex_multiplier=multiplier,
                )
            )
    return cases


def apply_investment_multiplier(
    params: PlanningCostParams,
    capex_group: str,
    multiplier: float,
) -> PlanningCostParams:
    """按设备组缩放投资成本参数。"""

    if multiplier <= 0:
        raise ValueError("投资成本倍率必须大于 0")

    if capex_group == "WIND":
        return replace(
            params,
            wind_capex_cny_per_kw=params.wind_capex_cny_per_kw * multiplier,
        )
    if capex_group == "PV":
        return replace(params, pv_capex_cny_per_kw=params.pv_capex_cny_per_kw * multiplier)
    if capex_group == "BATTERY":
        return replace(
            params,
            battery_power_capex_cny_per_kw=params.battery_power_capex_cny_per_kw
            * multiplier,
            battery_energy_capex_cny_per_kwh=params.battery_energy_capex_cny_per_kwh
            * multiplier,
        )
    if capex_group == "ELECTROLYZER":
        return replace(
            params,
            electrolyzer_capex_cny_per_kw=params.electrolyzer_capex_cny_per_kw
            * multiplier,
        )
    if capex_group == "H2_STORAGE":
        return replace(
            params,
            h2_storage_capex_cny_per_kg=params.h2_storage_capex_cny_per_kg
            * multiplier,
        )
    if capex_group == "FUEL_CELL":
        return replace(
            params,
            fuel_cell_capex_cny_per_kw=params.fuel_cell_capex_cny_per_kw * multiplier,
        )
    if capex_group == "HEAT_PUMP":
        return replace(
            params,
            heat_pump_capex_cny_per_kw=params.heat_pump_capex_cny_per_kw * multiplier,
        )
    raise ValueError(f"未知投资成本组：{capex_group}")


def run_investment_sensitivity_analysis(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
    capex_groups: list[str] | None = None,
    capex_multipliers: list[float] | None = None,
) -> dict[str, Path]:
    """运行容量规划投资成本敏感性分析。"""

    selected_groups = capex_groups or CAPEX_GROUPS
    selected_multipliers = capex_multipliers or DEFAULT_CAPEX_MULTIPLIERS
    cases = [
        case
        for case in get_default_investment_sensitivity_cases()
        if case.capex_group in selected_groups
        and case.capex_multiplier in selected_multipliers
    ]
    if not cases:
        raise ValueError("没有匹配的投资敏感性场景")

    workbook = load_input_workbook(workbook_path)
    typical_days = [
        (config, generate_typical_day_workbook(workbook, config))
        for config in get_default_typical_days()
    ]
    base_params = get_default_planning_cost_params()

    summary_frames = []
    capacity_frames = []
    metadata_rows = []

    for case in cases:
        cost_params = apply_investment_multiplier(
            base_params,
            case.capex_group,
            case.capex_multiplier,
        )
        model = build_capacity_planning_model(typical_days, cost_params)
        status = solve_model(model)
        results = extract_capacity_planning_results(model, status)

        summary = results["summary"].copy()
        summary.insert(0, "case_id", case.case_id)
        summary.insert(1, "capex_group", case.capex_group)
        summary.insert(2, "capex_multiplier", case.capex_multiplier)
        summary_frames.append(summary)

        capacity = results["capacity"].copy()
        capacity.insert(0, "case_id", case.case_id)
        capacity.insert(1, "capex_group", case.capex_group)
        capacity.insert(2, "capex_multiplier", case.capex_multiplier)
        capacity_frames.append(capacity)

        metadata_rows.append(
            {
                "case_id": case.case_id,
                "capex_group": case.capex_group,
                "capex_multiplier": case.capex_multiplier,
                "status": status,
            }
        )

    summary = pd.concat(summary_frames, ignore_index=True)
    capacity = pd.concat(capacity_frames, ignore_index=True)
    metadata = pd.DataFrame(metadata_rows)

    output_dir = Path(output_root) / "results" / "v3_investment_sensitivity"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = _export_tables(summary, capacity, metadata, output_dir)
    paths.update(_export_plots(summary, capacity, output_dir))
    paths["conclusion_md"] = _export_conclusion(summary, capacity, output_dir / "conclusion.md")
    return paths


def _export_tables(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    metadata: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    summary_csv = output_dir / "scenario_summary.csv"
    summary_excel = output_dir / "scenario_summary.xlsx"
    capacity_csv = output_dir / "capacity_results.csv"
    capacity_excel = output_dir / "capacity_results.xlsx"
    metadata_csv = output_dir / "scenario_metadata.csv"

    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary.to_excel(summary_excel, index=False)
    capacity.to_csv(capacity_csv, index=False, encoding="utf-8-sig")
    capacity.to_excel(capacity_excel, index=False)
    metadata.to_csv(metadata_csv, index=False, encoding="utf-8-sig")
    return {
        "scenario_summary_csv": summary_csv,
        "scenario_summary_excel": summary_excel,
        "capacity_results_csv": capacity_csv,
        "capacity_results_excel": capacity_excel,
        "scenario_metadata_csv": metadata_csv,
    }


def _export_plots(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    _configure_font()
    paths = {
        "annual_total_cost_vs_capex_png": output_dir / "annual_total_cost_vs_capex.png",
        "annual_carbon_vs_capex_png": output_dir / "annual_carbon_vs_capex.png",
        "capacity_selection_vs_capex_png": output_dir / "capacity_selection_vs_capex.png",
        "fuel_cell_threshold_png": output_dir / "fuel_cell_threshold.png",
    }
    _line_by_group(
        summary,
        "annual_total_cost_cny",
        "投资成本倍率-年度总成本",
        "年度总成本/元",
        paths["annual_total_cost_vs_capex_png"],
    )
    _line_by_group(
        summary,
        "annual_carbon_emission_kg",
        "投资成本倍率-年度碳排放",
        "年度碳排放/kgCO2",
        paths["annual_carbon_vs_capex_png"],
    )
    pivot_capacity = capacity[
        capacity["capacity_variable"].isin(
            ["wind_capacity_kw", "pv_capacity_kw", "electrolyzer_power_capacity_kw"]
        )
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    for variable_name, data in pivot_capacity.groupby("capacity_variable"):
        grouped = data.groupby("capex_multiplier")["capacity_value"].mean()
        ax.plot(grouped.index, grouped.values, marker="o", label=variable_name)
    ax.set_title("投资成本倍率-关键容量选择")
    ax.set_xlabel("投资成本倍率")
    ax.set_ylabel("容量")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(paths["capacity_selection_vs_capex_png"], dpi=150)
    plt.close(fig)

    fuel_cell = capacity[capacity["capacity_variable"] == "fuel_cell_power_capacity_kw"]
    fig, ax = plt.subplots(figsize=(8, 5))
    for group, data in fuel_cell.groupby("capex_group"):
        ax.plot(data["capex_multiplier"], data["capacity_value"], marker="o", label=group)
    ax.set_title("燃料电池投资敏感性")
    ax.set_xlabel("投资成本倍率")
    ax.set_ylabel("燃料电池容量/kW")
    ax.grid(True, alpha=0.3)
    if ax.get_legend_handles_labels()[0]:
        ax.legend()
    fig.tight_layout()
    fig.savefig(paths["fuel_cell_threshold_png"], dpi=150)
    plt.close(fig)
    return paths


def _line_by_group(
    summary: pd.DataFrame,
    value_column: str,
    title: str,
    ylabel: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for group, data in summary.groupby("capex_group"):
        ordered = data.sort_values("capex_multiplier")
        ax.plot(
            ordered["capex_multiplier"],
            ordered[value_column],
            marker="o",
            label=group,
        )
    ax.set_title(title)
    ax.set_xlabel("投资成本倍率")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _export_conclusion(
    summary: pd.DataFrame,
    capacity: pd.DataFrame,
    output_path: Path,
) -> Path:
    best = summary.loc[summary["annual_total_cost_cny"].idxmin()]
    fuel_cell = capacity[capacity["capacity_variable"] == "fuel_cell_power_capacity_kw"]
    max_fc = fuel_cell["capacity_value"].max() if not fuel_cell.empty else 0.0
    text = f"""# 设备投资参数敏感性分析结论

## 1. 分析范围

本次分析在多典型日容量规划模型基础上，对设备投资成本进行单因素敏感性测试。每个场景仅改变一个设备组的投资成本倍率，其余运行参数和设备寿命保持不变。

## 2. 关键结果

- 场景数量：{len(summary)} 个。
- 最低年度总成本场景：{best['case_id']}。
- 该场景年度总成本：{best['annual_total_cost_cny']:.2f} 元。
- 该场景年度碳排放：{best['annual_carbon_emission_kg']:.2f} kgCO2。
- 分析范围内燃料电池最大选择容量：{max_fc:.2f} kW。

## 3. 说明

投资敏感性结果用于判断容量规划结论对设备造价假设的依赖程度。若某类设备投资成本变化导致最优容量大幅变化，说明该设备经济性结论对成本参数较敏感，后续应优先校准其工程报价。
"""
    output_path.write_text(text, encoding="utf-8")
    return output_path


def _configure_font() -> None:
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
