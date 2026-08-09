"""命令行入口模块。"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from zero_carbon_park.config import (
    ManifestValidationError,
    VerifiedRunManifest,
    load_verified_manifest,
)
from zero_carbon_park.data.loader import export_processed_inputs, load_input_workbook
from zero_carbon_park.planning.pareto import run_cost_carbon_pareto_analysis
from zero_carbon_park.planning.runner import run_capacity_planning
from zero_carbon_park.planning.sensitivity import run_investment_sensitivity_analysis
from zero_carbon_park.reporting.export import export_project_conclusions
from zero_carbon_park.reporting.plots import (
    plot_battery_soc,
    plot_device_outputs,
    plot_h2_storage,
    plot_input_curves,
    plot_scenario_comparisons,
)
from zero_carbon_park.scenarios.runner import run_scenarios
from zero_carbon_park.typical_days.annualization import run_annualized_typical_days
from zero_carbon_park.typical_days.runner import run_typical_day_scenarios
from zero_carbon_park.uncertainty.stress_test import run_uncertainty_stress_test
from zero_carbon_park.uncertainty.stochastic_planning import (
    run_stochastic_capacity_planning,
)
from zero_carbon_park.uncertainty.robust_planning import run_robust_capacity_planning


DEFAULT_SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5"]


def resolve_declared_workbook(
    manifest_path: str | Path, *, repo_root: str | Path
) -> tuple[VerifiedRunManifest, Path]:
    """Resolve the legacy model workbook through a verified formal-run manifest.

    This is the compatibility bridge used while the annual-data entry point is
    introduced.  It deliberately uses one logical key and never scans the
    repository for similarly named workbooks.
    """

    verified = load_verified_manifest(manifest_path, repo_root=repo_root)
    try:
        workbook_path = verified.input_paths["model_workbook"]
    except KeyError as exc:
        raise ManifestValidationError(
            "formal manifest must declare the logical input 'model_workbook'"
        ) from exc
    if workbook_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ManifestValidationError(
            f"model_workbook must be an Excel workbook: {workbook_path}"
        )
    return verified, workbook_path


def run_full_pipeline(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, Path]:
    """运行第一版完整流程。

    流程包括：
    1. 读取 Excel 数据包。
    2. 导出标准化输入数据。
    3. 批量运行 S0-S5。
    4. 绘制输入曲线、设备出力、SOC、储氢和场景对比图。
    5. 生成项目结论初稿。
    """

    workbook_file = Path(workbook_path)
    output_dir = Path(output_root)

    processed_dir = output_dir / "processed_inputs"
    run_dir = output_dir / "runs" / "first_version"
    figure_dir = output_dir / "figures"
    docs_dir = output_dir / "docs"

    # 读取源数据包，得到标准化后的数据对象。
    workbook = load_input_workbook(workbook_file)

    # 导出模型可用的输入表，便于后续检查和复现。
    export_processed_inputs(workbook_file, processed_dir)

    # 批量运行 S0-S5 场景，并输出逐时结果与汇总结果。
    scenario_paths = run_scenarios(workbook, DEFAULT_SCENARIOS, run_dir)
    summary = pd.read_csv(scenario_paths["summary_csv"])
    hourly = pd.read_csv(scenario_paths["hourly_csv"])

    figure_dir.mkdir(parents=True, exist_ok=True)
    input_curves_png = plot_input_curves(
        workbook.timeseries, figure_dir / "input_curves.png"
    )
    device_outputs_png = plot_device_outputs(
        hourly, figure_dir / "device_outputs_s5.png"
    )
    battery_soc_png = plot_battery_soc(hourly, figure_dir / "battery_soc.png")
    h2_storage_png = plot_h2_storage(hourly, figure_dir / "h2_storage.png")
    comparison_paths = plot_scenario_comparisons(summary, figure_dir)

    conclusion_md = export_project_conclusions(
        summary, docs_dir / "project_conclusions.md"
    )

    return {
        "processed_dir": processed_dir,
        "run_dir": run_dir,
        "figure_dir": figure_dir,
        "conclusion_md": conclusion_md,
        "input_curves_png": input_curves_png,
        "device_outputs_png": device_outputs_png,
        "battery_soc_png": battery_soc_png,
        "h2_storage_png": h2_storage_png,
        "scenario_cost_png": comparison_paths["scenario_cost_png"],
        "scenario_carbon_png": comparison_paths["scenario_carbon_png"],
        "scenario_renewable_png": comparison_paths["scenario_renewable_png"],
        "summary_csv": scenario_paths["summary_csv"],
        "hourly_csv": scenario_paths["hourly_csv"],
    }


def main() -> None:
    """命令行入口。"""

    parser = argparse.ArgumentParser(description="运行零碳园区综合能源系统分析流程。")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--manifest",
        help="正式运行清单路径；输入将先校验来源ID和SHA256。",
    )
    input_group.add_argument(
        "--workbook",
        help="兼容旧流程的显式 Excel 路径（不属于正式基准）。",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="项目根目录，供正式清单解析相对路径。",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出目录；正式运行默认写入清单所在的独立运行目录。",
    )
    parser.add_argument(
        "--run-typical-days",
        action="store_true",
        help="运行 v2.1 多典型日 S5 调度。",
    )
    parser.add_argument(
        "--run-annualization",
        action="store_true",
        help="运行 v2.2 多典型日加权年化分析。",
    )
    parser.add_argument(
        "--run-capacity-planning",
        action="store_true",
        help="运行 v2.3 多典型日容量规划优化。",
    )
    parser.add_argument(
        "--run-investment-sensitivity",
        action="store_true",
        help="运行 v3.1 设备投资参数敏感性分析。",
    )
    parser.add_argument(
        "--run-pareto-analysis",
        action="store_true",
        help="运行 v3.2 成本-碳排放 Pareto 分析。",
    )
    parser.add_argument(
        "--run-uncertainty-stress-test",
        action="store_true",
        help="运行 v4.1 固定容量不确定性压力测试。",
    )
    parser.add_argument(
        "--run-stochastic-planning",
        action="store_true",
        help="运行 v4.2 场景概率加权随机容量规划。",
    )
    parser.add_argument(
        "--run-robust-planning",
        action="store_true",
        help="运行 v4.3 最坏情形鲁棒容量规划。",
    )
    args = parser.parse_args()

    if args.manifest:
        verified_manifest, workbook_path = resolve_declared_workbook(
            args.manifest, repo_root=args.repo_root
        )
        output_root = Path(args.output) if args.output else verified_manifest.manifest_path.parent
        print(f"verified_run_id: {verified_manifest.run_id}")
        for excluded_path in verified_manifest.excluded_history_paths:
            print(f"excluded_history: {excluded_path}")
    else:
        workbook_path = Path(args.workbook)
        output_root = Path(args.output or "outputs")
        print("legacy_input_mode: results are not eligible for the formal baseline")

    if args.run_robust_planning:
        outputs = run_robust_capacity_planning(workbook_path, output_root)
    elif args.run_stochastic_planning:
        outputs = run_stochastic_capacity_planning(workbook_path, output_root)
    elif args.run_uncertainty_stress_test:
        outputs = run_uncertainty_stress_test(workbook_path, output_root)
    elif args.run_pareto_analysis:
        outputs = run_cost_carbon_pareto_analysis(workbook_path, output_root)
    elif args.run_investment_sensitivity:
        outputs = run_investment_sensitivity_analysis(workbook_path, output_root)
    elif args.run_capacity_planning:
        outputs = run_capacity_planning(workbook_path, output_root)
    elif args.run_annualization:
        outputs = run_annualized_typical_days(workbook_path, output_root)
    elif args.run_typical_days:
        outputs = run_typical_day_scenarios(workbook_path, output_root)
    else:
        outputs = run_full_pipeline(workbook_path, output_root)
    for name, path in outputs.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
