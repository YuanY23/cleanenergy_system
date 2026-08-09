"""Run-scoped, non-interactive engineering report artifacts.

This module deliberately receives every table from its caller.  It never scans
legacy output directories and never selects a historical scenario implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from zero_carbon_park.reporting.plots import (
    plot_annual_duration_curves,
    plot_annual_storage_states,
    plot_cost_carbon_reliability_tradeoff,
    plot_extreme_week_dispatch,
    plot_monthly_operating_carbon,
    plot_outage_duration_reliability,
    plot_portfolio_capacity_and_cost,
    plot_representative_period_errors,
    plot_sensitivity_tornado,
)


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LEGACY_SCENARIO = re.compile(r"^S[0-5]$", re.IGNORECASE)
_SOURCE_CATEGORIES = {"公开事实", "模型结果", "工程假设"}


@dataclass
class EngineeringReportInputs:
    """Explicit latest-run tables consumed by the static reporting layer."""

    annual_inputs: pd.DataFrame
    representative_diagnostics: pd.DataFrame
    portfolio_summary: pd.DataFrame
    portfolio_capacity: pd.DataFrame
    replay_hourly: pd.DataFrame
    reliability_summary: pd.DataFrame
    sensitivity_summary: pd.DataFrame
    source_notes: pd.DataFrame


def generate_static_engineering_outputs(
    *,
    output_root: str | Path,
    run_id: str,
    inputs: EngineeringReportInputs,
) -> dict[str, Path]:
    """Generate nine static figures, a technical report and an artifact index."""

    _validate_run_id(run_id)
    _validate_inputs(inputs, run_id)
    run_dir = Path(output_root).resolve() / run_id
    report_dir = run_dir / "reporting"
    try:
        report_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(
            f"reporting output already exists and is immutable: {report_dir}"
        ) from exc
    source_note = f"数据来源：仅使用本次运行显式输入；run_id={run_id}；口径详见技术报告。"

    outputs: dict[str, Path] = {
        "duration_curve_png": plot_annual_duration_curves(
            inputs.annual_inputs,
            report_dir / "01_8784h_duration_curves.png",
            source_note=source_note,
        ),
        "representative_error_png": plot_representative_period_errors(
            inputs.representative_diagnostics,
            report_dir / "02_representative_period_errors.png",
            source_note=source_note,
        ),
        "portfolio_capacity_cost_png": plot_portfolio_capacity_and_cost(
            inputs.portfolio_summary,
            inputs.portfolio_capacity,
            report_dir / "03_portfolio_capacity_cost.png",
            source_note=source_note,
        ),
        "monthly_carbon_png": plot_monthly_operating_carbon(
            inputs.replay_hourly,
            report_dir / "04_monthly_operating_carbon.png",
            source_note=source_note,
        ),
        "storage_state_png": plot_annual_storage_states(
            inputs.replay_hourly,
            report_dir / "05_annual_storage_states.png",
            source_note=source_note,
        ),
        "extreme_week_dispatch_png": plot_extreme_week_dispatch(
            inputs.replay_hourly,
            report_dir / "06_extreme_week_dispatch.png",
            source_note=source_note,
        ),
        "outage_reliability_png": plot_outage_duration_reliability(
            inputs.reliability_summary,
            report_dir / "07_outage_duration_reliability.png",
            source_note=source_note,
        ),
        "tradeoff_bubble_png": plot_cost_carbon_reliability_tradeoff(
            inputs.portfolio_summary,
            report_dir / "08_cost_carbon_reliability_tradeoff.png",
            source_note=source_note,
        ),
        "sensitivity_tornado_png": plot_sensitivity_tornado(
            inputs.sensitivity_summary,
            report_dir / "09_sensitivity_tornado.png",
            source_note=source_note,
        ),
    }
    report_path = report_dir / "zero_carbon_park_technical_report.md"
    report_path.write_text(_build_technical_report(run_id, inputs), encoding="utf-8")
    outputs["technical_report_md"] = report_path

    index_path = report_dir / "results_index.csv"
    _build_results_index(run_dir, run_id, outputs).to_csv(
        index_path, index=False, encoding="utf-8-sig"
    )
    outputs["results_index_csv"] = index_path
    return outputs


def _validate_run_id(run_id: str) -> None:
    if not _SAFE_RUN_ID.fullmatch(run_id) or ".." in run_id:
        raise ValueError("run_id must be a safe run identifier")


def _validate_inputs(inputs: EngineeringReportInputs, run_id: str) -> None:
    frames = {
        "annual_inputs": inputs.annual_inputs,
        "representative_diagnostics": inputs.representative_diagnostics,
        "portfolio_summary": inputs.portfolio_summary,
        "portfolio_capacity": inputs.portfolio_capacity,
        "replay_hourly": inputs.replay_hourly,
        "reliability_summary": inputs.reliability_summary,
        "sensitivity_summary": inputs.sensitivity_summary,
        "source_notes": inputs.source_notes,
    }
    for label, frame in frames.items():
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{label} must be a pandas DataFrame")
        if frame.empty:
            raise ValueError(f"{label} cannot be empty")
    source_columns = {"category", "item", "statement", "source"}
    missing = source_columns - set(inputs.source_notes.columns)
    if missing:
        raise ValueError(f"source_notes missing columns: {sorted(missing)}")
    unknown_categories = set(inputs.source_notes["category"]) - _SOURCE_CATEGORIES
    if unknown_categories:
        raise ValueError(
            "source_notes category must distinguish 公开事实/模型结果/工程假设: "
            f"{sorted(unknown_categories)}"
        )
    model_sources = inputs.source_notes.loc[
        inputs.source_notes["category"].eq("模型结果"), "source"
    ].astype(str)
    if model_sources.empty or not model_sources.eq(run_id).all():
        raise ValueError("模型结果 source_notes must reference current run_id")
    if "portfolio_id" in inputs.portfolio_summary:
        legacy = {
            str(value)
            for value in inputs.portfolio_summary["portfolio_id"]
            if _LEGACY_SCENARIO.fullmatch(str(value))
        }
        if legacy:
            raise ValueError(f"legacy scenario labels are not valid portfolios: {sorted(legacy)}")


def _build_technical_report(run_id: str, inputs: EngineeringReportInputs) -> str:
    portfolio_columns = [
        column
        for column in (
            "portfolio_id",
            "portfolio_name",
            "annual_total_cost_cny",
            "zero_carbon_total_kgco2",
            "critical_load_supply_ratio",
            "hydrogen_supply_ratio",
            "minimum_island_survival_hours",
        )
        if column in inputs.portfolio_summary
    ]
    reliability_columns = [
        column
        for column in (
            "portfolio_id",
            "duration_hours",
            "critical_load_supply_ratio",
            "ens_total_kwh",
            "hydrogen_supply_ratio",
            "unserved_hydrogen_kg",
        )
        if column in inputs.reliability_summary
    ]
    sources = inputs.source_notes[["category", "item", "statement", "source"]]
    cost_value = float(inputs.portfolio_summary["annual_total_cost_cny"].iloc[0])
    carbon_boundary = (
        "位置法与零碳园区核算方法分别列示；本报告不以外送电自动抵扣运行排放。"
    )
    return f"""# 零碳工业园区综合能源系统规划与韧性评估技术报告

运行标识：`{run_id}`

## 1. 工程问题与研究边界

本次研究面向零碳工业园区电—热—氢—储综合能源系统，采用全年逐时输入、代表日容量规划、固定容量全年回放和孤网停电事件评估形成闭环。成果为可审计的静态工程图表与表格，不包含交互式展示系统。

本报告只消费调用方显式传入的本次运行表，不扫描历史输出目录。输入时序共 {len(inputs.annual_inputs):,} 小时；若用于正式结论，应由上游质量门确认其为 2024 年完整 8,784 小时数据。{carbon_boundary}

## 2. 数据来源与口径分层

{_markdown_table(sources)}

## 3. 规划方案结果

下列成本、碳排与可靠性指标直接来自传入的模型结果表，报告层不重复计算。首个方案年化总成本为 {cost_value:,.0f} 元/年。

{_markdown_table(inputs.portfolio_summary[portfolio_columns])}

容量结果按设备原始工程单位展示，避免将 kW、kWh 和 kg 混为同一容量口径；相关图见 `03_portfolio_capacity_cost.png`。

## 4. 全年回放与能碳表现

全年回放用于检查固定规划容量在连续时序下的可运行性、储能跨时段状态和月度运行碳排。图表直接采用回放表中的储能状态和两套碳核算结果；绘图层不重新套用排放因子。

## 5. 孤网保供可靠性

可靠性结果属于确定性设计事件压力测试，不使用概率型可靠性术语替代。关键负荷供能率与未供能量 ENS 均来自传入的事件汇总表。

{_markdown_table(inputs.reliability_summary[reliability_columns])}

## 6. 敏感性与决策解释

敏感性龙卷风采用调用方已计算的相对基准成本影响。成本—碳排—可靠性气泡图用于比较经济型、低碳型与韧性型工程方案，不改变任何输入指标值。

## 7. 结论使用限制

- 公开事实、模型结果和工程假设已在来源表中分栏，不应相互替代。
- 正式简历与面试材料只能引用通过上游数据、求解、回放和可靠性质量门的本次运行数字。
- 确定性孤网事件结果用于工程方案对标，不构成认证或概率风险承诺。
"""


def _markdown_table(frame: pd.DataFrame) -> str:
    formatted = frame.copy()
    for column in formatted:
        formatted[column] = formatted[column].map(_format_cell)
    header = "| " + " | ".join(map(str, formatted.columns)) + " |"
    separator = "| " + " | ".join("---" for _ in formatted.columns) + " |"
    rows = [
        "| " + " | ".join(str(row[column]) for column in formatted.columns) + " |"
        for _, row in formatted.iterrows()
    ]
    return "\n".join([header, separator, *rows])


def _format_cell(value: object) -> str:
    if pd.isna(value):
        return "—"
    if isinstance(value, float):
        return f"{value:,.6g}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _build_results_index(
    run_dir: Path,
    run_id: str,
    outputs: dict[str, Path],
) -> pd.DataFrame:
    descriptions = {
        "duration_curve_png": "8784小时负荷与资源持续曲线",
        "representative_error_png": "代表日重构误差",
        "portfolio_capacity_cost_png": "三类工程方案容量与成本",
        "monthly_carbon_png": "月度运行碳排",
        "storage_state_png": "全年电池与储氢状态",
        "extreme_week_dispatch_png": "极端周调度",
        "outage_reliability_png": "停电时长—供能率与ENS",
        "tradeoff_bubble_png": "成本—碳排—可靠性权衡",
        "sensitivity_tornado_png": "敏感性龙卷风",
        "technical_report_md": "静态工程技术报告",
    }
    rows = []
    for key, path in outputs.items():
        resolved = path.resolve()
        if not resolved.is_relative_to(run_dir.resolve()):
            raise ValueError(f"artifact escaped run directory: {path}")
        rows.append(
            {
                "run_id": run_id,
                "artifact_key": key,
                "category": "figure" if path.suffix.lower() == ".png" else "report",
                "description": descriptions[key],
                "relative_path": resolved.relative_to(run_dir.resolve()).as_posix(),
                "bytes": resolved.stat().st_size,
            }
        )
    return pd.DataFrame(rows)


__all__ = ["EngineeringReportInputs", "generate_static_engineering_outputs"]
