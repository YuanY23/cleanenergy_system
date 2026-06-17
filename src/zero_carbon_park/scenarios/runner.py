"""场景运行模块。"""

from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import InputWorkbook
from zero_carbon_park.optimization.builder import build_minimal_milp_model
from zero_carbon_park.optimization.results import (
    ScenarioResult,
    extract_minimal_results,
)
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.scenarios.definitions import get_minimal_scenario_config


def run_scenario(workbook: InputWorkbook, scenario_id: str) -> ScenarioResult:
    """运行单个 Plan C 最小 MILP 场景。"""

    # 根据场景编号取得设备开关配置。
    scenario = get_minimal_scenario_config(scenario_id)

    # 使用标准化后的数据表构建 Pyomo 模型。
    model = build_minimal_milp_model(
        timeseries=workbook.timeseries,
        device_params=workbook.device_params,
        economic_params=workbook.economic_params,
        scenario=scenario,
    )

    # 调用 HiGHS 求解器求解模型。
    status = solve_model(model)

    # 将 Pyomo 变量值提取成 DataFrame 和汇总字典。
    return extract_minimal_results(model, scenario.scenario_id, status)


def run_scenarios(
    workbook: InputWorkbook, scenario_ids: list[str], output_dir: str | Path
) -> dict[str, Path]:
    """批量运行场景，并导出逐时结果和汇总结果。"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = [run_scenario(workbook, scenario_id) for scenario_id in scenario_ids]

    # 汇总表是一行一个场景。
    summary = pd.DataFrame([result.summary for result in results])

    # 逐时表是所有场景的 24 小时结果拼接。
    hourly = pd.concat(
        [result.hourly_results for result in results],
        ignore_index=True,
    )

    summary_csv = output_path / "scenario_summary.csv"
    summary_excel = output_path / "scenario_summary.xlsx"
    hourly_csv = output_path / "scenario_hourly_results.csv"
    hourly_excel = output_path / "scenario_hourly_results.xlsx"

    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary.to_excel(summary_excel, index=False)
    hourly.to_csv(hourly_csv, index=False, encoding="utf-8-sig")
    hourly.to_excel(hourly_excel, index=False)

    return {
        "summary_csv": summary_csv,
        "summary_excel": summary_excel,
        "hourly_csv": hourly_csv,
        "hourly_excel": hourly_excel,
    }
