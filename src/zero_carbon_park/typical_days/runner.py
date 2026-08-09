"""多典型日批量运行模块。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.reporting.plots import (
    plot_battery_soc,
    plot_device_outputs,
    plot_h2_storage,
)
from zero_carbon_park.scenarios.runner import run_scenario
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.definitions import RepresentativePeriodResult
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


def run_typical_day_scenarios(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
    scenario_id: str = "S5",
) -> dict[str, Path]:
    """运行默认三个典型日的同一场景并导出结果。

    参数:
        workbook_path: 原始 Excel 数据包路径。
        output_root: 输出根目录。
        scenario_id: 要运行的基础场景，第一版默认使用完整低碳调度 S5。
    """

    workbook = load_input_workbook(workbook_path)
    result_root = Path(output_root) / "results" / "v2_typical_days"
    result_root.mkdir(parents=True, exist_ok=True)

    summary_frames: list[pd.DataFrame] = []
    hourly_frames: list[pd.DataFrame] = []

    for config in get_default_typical_days():
        day_workbook = generate_typical_day_workbook(workbook, config)
        day_dir = result_root / config.day_id
        day_dir.mkdir(parents=True, exist_ok=True)

        _export_input_timeseries(day_workbook.timeseries, day_dir)

        result = run_scenario(day_workbook, scenario_id)
        summary = _summary_with_typical_day_metadata(result.summary, config)
        hourly = _hourly_with_typical_day_metadata(result.hourly_results, config)

        _export_day_results(summary, hourly, day_dir)
        plot_device_outputs(hourly, day_dir / "device_outputs.png")
        plot_battery_soc(hourly, day_dir / "battery_soc.png")
        plot_h2_storage(hourly, day_dir / "h2_storage.png")

        summary_frames.append(summary)
        hourly_frames.append(hourly)

    combined_summary = pd.concat(summary_frames, ignore_index=True)
    combined_hourly = pd.concat(hourly_frames, ignore_index=True)

    summary_csv = result_root / "typical_day_summary.csv"
    summary_excel = result_root / "typical_day_summary.xlsx"
    hourly_csv = result_root / "typical_day_hourly_results.csv"
    hourly_excel = result_root / "typical_day_hourly_results.xlsx"

    combined_summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    combined_summary.to_excel(summary_excel, index=False)
    combined_hourly.to_csv(hourly_csv, index=False, encoding="utf-8-sig")
    combined_hourly.to_excel(hourly_excel, index=False)

    return {
        "summary_csv": summary_csv,
        "summary_excel": summary_excel,
        "hourly_csv": hourly_csv,
        "hourly_excel": hourly_excel,
    }


def _export_input_timeseries(timeseries: pd.DataFrame, output_dir: Path) -> None:
    """导出单个典型日的输入曲线，便于人工复查。"""

    timeseries.to_csv(output_dir / "input_timeseries.csv", index=False, encoding="utf-8-sig")
    timeseries.to_excel(output_dir / "input_timeseries.xlsx", index=False)


def _summary_with_typical_day_metadata(summary: dict, config) -> pd.DataFrame:
    """给单日汇总结果补充典型日元数据。"""

    return pd.DataFrame(
        [
            {
                "typical_day_id": config.day_id,
                "typical_day_name": config.name,
                "weight_days": config.weight_days,
                **summary,
            }
        ]
    )


def _hourly_with_typical_day_metadata(
    hourly: pd.DataFrame,
    config,
) -> pd.DataFrame:
    """给逐小时结果补充典型日元数据。"""

    changed = hourly.copy()
    changed.insert(0, "weight_days", config.weight_days)
    changed.insert(0, "typical_day_name", config.name)
    changed.insert(0, "typical_day_id", config.day_id)
    return changed


def _export_day_results(
    summary: pd.DataFrame,
    hourly: pd.DataFrame,
    output_dir: Path,
) -> None:
    """导出单个典型日的汇总表和逐时表。"""

    summary.to_csv(output_dir / "scenario_summary.csv", index=False, encoding="utf-8-sig")
    summary.to_excel(output_dir / "scenario_summary.xlsx", index=False)
    hourly.to_csv(
        output_dir / "scenario_hourly_results.csv",
        index=False,
        encoding="utf-8-sig",
    )
    hourly.to_excel(output_dir / "scenario_hourly_results.xlsx", index=False)


def write_representative_period_artifacts(
    result: RepresentativePeriodResult,
    diagnostics: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write the complete clustering audit trail into one run-scoped folder."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "representative_days": root / "representative_days.csv",
        "representative_hourly": root / "representative_hourly.csv",
        "day_mapping": root / "day_mapping.csv",
        "transition_counts": root / "transition_counts.csv",
        "chronology_links": root / "chronology_links.csv",
        "normalization": root / "normalization.csv",
        "diagnostics": root / "compression_diagnostics.csv",
        "metadata": root / "representative_period_metadata.json",
    }
    result.representative_days.to_csv(
        paths["representative_days"], index=False, encoding="utf-8-sig"
    )
    result.representative_hourly.to_csv(
        paths["representative_hourly"], index=False, encoding="utf-8-sig"
    )
    result.day_mapping.to_csv(paths["day_mapping"], index=False, encoding="utf-8-sig")
    result.transition_counts.to_csv(paths["transition_counts"], encoding="utf-8-sig")
    result.chronology_links.to_csv(
        paths["chronology_links"], index=False, encoding="utf-8-sig"
    )
    result.normalization.to_csv(
        paths["normalization"], index=False, encoding="utf-8-sig"
    )
    diagnostics.to_csv(paths["diagnostics"], index=False, encoding="utf-8-sig")
    metadata = {
        "method": "deterministic_fixed-extreme_k-medoids",
        "k": result.k,
        "seed": result.seed,
        "feature_columns": list(result.feature_columns),
        "weight_days_total": int(result.representative_days["weight_days"].sum()),
        "chronology_link_count": len(result.chronology_links),
        "extreme_days": result.extreme_days,
    }
    paths["metadata"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return paths
