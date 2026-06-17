"""v1.1 参数敏感性场景运行模块。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from zero_carbon_park.data.loader import InputWorkbook, load_input_workbook
from zero_carbon_park.optimization.builder import build_minimal_milp_model
from zero_carbon_park.optimization.results import ScenarioResult, extract_minimal_results
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.reporting.plots import (
    plot_battery_soc,
    plot_device_outputs,
    plot_h2_storage,
)
from zero_carbon_park.scenarios.definitions import get_minimal_scenario_config


@dataclass(frozen=True)
class SensitivityCase:
    """单个敏感性场景。"""

    case_id: str
    label: str
    changes: dict[str, float]


@dataclass(frozen=True)
class SensitivityStudy:
    """一组敏感性场景。"""

    study_id: str
    title: str
    base_scenario_id: str
    x_label: str
    x_column: str
    cases: list[SensitivityCase]


def get_v1_1_sensitivity_studies() -> dict[str, SensitivityStudy]:
    """返回 v1.1 计划中的四组参数敏感性场景。"""

    return {
        "carbon_price_sensitivity": SensitivityStudy(
            study_id="carbon_price_sensitivity",
            title="碳价敏感性",
            base_scenario_id="S5",
            x_label="碳价/(元/tCO2)",
            x_column="carbon_price_cny_per_tco2",
            cases=[
                SensitivityCase("C0", "0 元/tCO2", {"carbon_price_cny_per_tco2": 0.0}),
                SensitivityCase("C1", "30 元/tCO2", {"carbon_price_cny_per_tco2": 30.0}),
                SensitivityCase("C2", "60 元/tCO2", {"carbon_price_cny_per_tco2": 60.0}),
                SensitivityCase("C3", "100 元/tCO2", {"carbon_price_cny_per_tco2": 100.0}),
                SensitivityCase("C4", "150 元/tCO2", {"carbon_price_cny_per_tco2": 150.0}),
                SensitivityCase("C5", "200 元/tCO2", {"carbon_price_cny_per_tco2": 200.0}),
            ],
        ),
        "renewable_scale_sensitivity": SensitivityStudy(
            study_id="renewable_scale_sensitivity",
            title="新能源出力比例敏感性",
            base_scenario_id="S5",
            x_label="风光可发功率倍率",
            x_column="renewable_available_scale",
            cases=[
                SensitivityCase("R0", "0.6 倍", {"renewable_available_scale": 0.6}),
                SensitivityCase("R1", "0.8 倍", {"renewable_available_scale": 0.8}),
                SensitivityCase("R2", "1.0 倍", {"renewable_available_scale": 1.0}),
                SensitivityCase("R3", "1.2 倍", {"renewable_available_scale": 1.2}),
                SensitivityCase("R4", "1.5 倍", {"renewable_available_scale": 1.5}),
                SensitivityCase("R5", "2.0 倍", {"renewable_available_scale": 2.0}),
            ],
        ),
        "battery_capacity_sensitivity": SensitivityStudy(
            study_id="battery_capacity_sensitivity",
            title="电池容量敏感性",
            base_scenario_id="S5",
            x_label="电池容量倍率",
            x_column="battery_energy_scale",
            cases=[
                SensitivityCase(
                    "B0",
                    "0.0 倍",
                    {"battery_power_scale": 0.0, "battery_energy_scale": 0.0},
                ),
                SensitivityCase(
                    "B1",
                    "0.5 倍",
                    {"battery_power_scale": 0.5, "battery_energy_scale": 0.5},
                ),
                SensitivityCase(
                    "B2",
                    "1.0 倍",
                    {"battery_power_scale": 1.0, "battery_energy_scale": 1.0},
                ),
                SensitivityCase(
                    "B3",
                    "1.5 倍",
                    {"battery_power_scale": 1.5, "battery_energy_scale": 1.5},
                ),
                SensitivityCase(
                    "B4",
                    "2.0 倍",
                    {"battery_power_scale": 2.0, "battery_energy_scale": 2.0},
                ),
                SensitivityCase(
                    "B5",
                    "3.0 倍",
                    {"battery_power_scale": 3.0, "battery_energy_scale": 3.0},
                ),
            ],
        ),
        "hydrogen_load_sensitivity": SensitivityStudy(
            study_id="hydrogen_load_sensitivity",
            title="氢负荷敏感性",
            base_scenario_id="S5",
            x_label="氢负荷倍率",
            x_column="hydrogen_load_scale",
            cases=[
                SensitivityCase("H0", "0.0 倍", {"hydrogen_load_scale": 0.0}),
                SensitivityCase("H1", "0.5 倍", {"hydrogen_load_scale": 0.5}),
                SensitivityCase("H2", "1.0 倍", {"hydrogen_load_scale": 1.0}),
                SensitivityCase("H3", "1.5 倍", {"hydrogen_load_scale": 1.5}),
                SensitivityCase("H4", "2.0 倍", {"hydrogen_load_scale": 2.0}),
            ],
        ),
    }


def get_v1_2_sensitivity_studies() -> dict[str, SensitivityStudy]:
    """返回 v1.2 计划中的价格与外部排放因子敏感性场景。"""

    return {
        "electricity_price_spread_sensitivity": SensitivityStudy(
            study_id="electricity_price_spread_sensitivity",
            title="电价峰谷差敏感性",
            base_scenario_id="S5",
            x_label="峰谷价差指数",
            x_column="price_spread_index",
            cases=[
                SensitivityCase(
                    "P0",
                    "谷价1.0倍/峰价1.0倍",
                    {
                        "valley_price_scale": 1.0,
                        "peak_price_scale": 1.0,
                        "price_spread_index": 1.0,
                    },
                ),
                SensitivityCase(
                    "P1",
                    "谷价0.9倍/峰价1.1倍",
                    {
                        "valley_price_scale": 0.9,
                        "peak_price_scale": 1.1,
                        "price_spread_index": 1.1 / 0.9,
                    },
                ),
                SensitivityCase(
                    "P2",
                    "谷价0.8倍/峰价1.2倍",
                    {
                        "valley_price_scale": 0.8,
                        "peak_price_scale": 1.2,
                        "price_spread_index": 1.2 / 0.8,
                    },
                ),
                SensitivityCase(
                    "P3",
                    "谷价0.7倍/峰价1.3倍",
                    {
                        "valley_price_scale": 0.7,
                        "peak_price_scale": 1.3,
                        "price_spread_index": 1.3 / 0.7,
                    },
                ),
                SensitivityCase(
                    "P4",
                    "谷价0.6倍/峰价1.5倍",
                    {
                        "valley_price_scale": 0.6,
                        "peak_price_scale": 1.5,
                        "price_spread_index": 1.5 / 0.6,
                    },
                ),
            ],
        ),
        "gas_price_sensitivity": SensitivityStudy(
            study_id="gas_price_sensitivity",
            title="天然气价格敏感性",
            base_scenario_id="S5",
            x_label="天然气价格倍率",
            x_column="gas_price_scale",
            cases=[
                SensitivityCase("G0", "0.8 倍", {"gas_price_scale": 0.8}),
                SensitivityCase("G1", "1.0 倍", {"gas_price_scale": 1.0}),
                SensitivityCase("G2", "1.2 倍", {"gas_price_scale": 1.2}),
                SensitivityCase("G3", "1.5 倍", {"gas_price_scale": 1.5}),
                SensitivityCase("G4", "2.0 倍", {"gas_price_scale": 2.0}),
            ],
        ),
        "grid_emission_factor_sensitivity": SensitivityStudy(
            study_id="grid_emission_factor_sensitivity",
            title="电网排放因子敏感性",
            base_scenario_id="S5",
            x_label="电网排放因子倍率",
            x_column="grid_emission_factor_scale",
            cases=[
                SensitivityCase("E0", "0.4 倍", {"grid_emission_factor_scale": 0.4}),
                SensitivityCase("E1", "0.7 倍", {"grid_emission_factor_scale": 0.7}),
                SensitivityCase("E2", "1.0 倍", {"grid_emission_factor_scale": 1.0}),
                SensitivityCase("E3", "1.2 倍", {"grid_emission_factor_scale": 1.2}),
            ],
        ),
    }


def get_v1_3_sensitivity_studies() -> dict[str, SensitivityStudy]:
    """返回 v1.3 计划中的设备容量组合敏感性场景。"""

    return {
        "electrolyzer_capacity_sensitivity": SensitivityStudy(
            study_id="electrolyzer_capacity_sensitivity",
            title="电解槽容量敏感性",
            base_scenario_id="S5",
            x_label="电解槽功率倍率",
            x_column="electrolyzer_power_scale",
            cases=[
                SensitivityCase("EL0", "0.5 倍", {"electrolyzer_power_scale": 0.5}),
                SensitivityCase("EL1", "1.0 倍", {"electrolyzer_power_scale": 1.0}),
                SensitivityCase("EL2", "1.5 倍", {"electrolyzer_power_scale": 1.5}),
                SensitivityCase("EL3", "2.0 倍", {"electrolyzer_power_scale": 2.0}),
                SensitivityCase("EL4", "3.0 倍", {"electrolyzer_power_scale": 3.0}),
            ],
        ),
        "h2_storage_capacity_sensitivity": SensitivityStudy(
            study_id="h2_storage_capacity_sensitivity",
            title="储氢罐容量敏感性",
            base_scenario_id="S5",
            x_label="储氢罐容量倍率",
            x_column="h2_storage_capacity_scale",
            cases=[
                SensitivityCase("HS0", "0.5 倍", {"h2_storage_capacity_scale": 0.5}),
                SensitivityCase("HS1", "1.0 倍", {"h2_storage_capacity_scale": 1.0}),
                SensitivityCase("HS2", "1.5 倍", {"h2_storage_capacity_scale": 1.5}),
                SensitivityCase("HS3", "2.0 倍", {"h2_storage_capacity_scale": 2.0}),
                SensitivityCase("HS4", "3.0 倍", {"h2_storage_capacity_scale": 3.0}),
            ],
        ),
        "fuel_cell_capacity_sensitivity": SensitivityStudy(
            study_id="fuel_cell_capacity_sensitivity",
            title="燃料电池容量敏感性",
            base_scenario_id="S5",
            x_label="燃料电池容量倍率",
            x_column="fuel_cell_power_scale",
            cases=[
                SensitivityCase("FC0", "0.0 倍", {"fuel_cell_power_scale": 0.0}),
                SensitivityCase("FC1", "0.5 倍", {"fuel_cell_power_scale": 0.5}),
                SensitivityCase("FC2", "1.0 倍", {"fuel_cell_power_scale": 1.0}),
                SensitivityCase("FC3", "1.5 倍", {"fuel_cell_power_scale": 1.5}),
                SensitivityCase("FC4", "2.0 倍", {"fuel_cell_power_scale": 2.0}),
            ],
        ),
    }


def get_v1_4_sensitivity_studies() -> dict[str, SensitivityStudy]:
    """返回 v1.4 计划中的政策约束和售氢收益场景。"""

    return {
        "h2_sale_price_sensitivity": SensitivityStudy(
            study_id="h2_sale_price_sensitivity",
            title="售氢价格敏感性",
            base_scenario_id="S5",
            x_label="售氢价格/(元/kg)",
            x_column="h2_sale_price_cny_per_kg",
            cases=[
                SensitivityCase("HSAL0", "0 元/kg", {"h2_sale_price_cny_per_kg": 0.0}),
                SensitivityCase("HSAL1", "10 元/kg", {"h2_sale_price_cny_per_kg": 10.0}),
                SensitivityCase("HSAL2", "20 元/kg", {"h2_sale_price_cny_per_kg": 20.0}),
                SensitivityCase("HSAL3", "30 元/kg", {"h2_sale_price_cny_per_kg": 30.0}),
                SensitivityCase("HSAL4", "40 元/kg", {"h2_sale_price_cny_per_kg": 40.0}),
            ],
        ),
        "carbon_cap_sensitivity": SensitivityStudy(
            study_id="carbon_cap_sensitivity",
            title="碳排放上限敏感性",
            base_scenario_id="S5",
            x_label="碳排放上限比例",
            x_column="carbon_cap_ratio",
            cases=[
                SensitivityCase("CAP0", "100%", {"carbon_cap_ratio": 1.0}),
                SensitivityCase("CAP1", "90%", {"carbon_cap_ratio": 0.9}),
                SensitivityCase("CAP2", "80%", {"carbon_cap_ratio": 0.8}),
                SensitivityCase("CAP3", "70%", {"carbon_cap_ratio": 0.7}),
                SensitivityCase("CAP4", "60%", {"carbon_cap_ratio": 0.6}),
            ],
        ),
        "renewable_consumption_constraint_sensitivity": SensitivityStudy(
            study_id="renewable_consumption_constraint_sensitivity",
            title="新能源消纳率约束敏感性",
            base_scenario_id="S5",
            x_label="最低新能源消纳率",
            x_column="renewable_min_consumption_rate",
            cases=[
                SensitivityCase("RC0", "90%", {"renewable_min_consumption_rate": 0.90}),
                SensitivityCase("RC1", "95%", {"renewable_min_consumption_rate": 0.95}),
                SensitivityCase("RC2", "98%", {"renewable_min_consumption_rate": 0.98}),
                SensitivityCase("RC3", "99%", {"renewable_min_consumption_rate": 0.99}),
            ],
        ),
    }


def apply_sensitivity_case(
    workbook: InputWorkbook,
    case: SensitivityCase,
) -> InputWorkbook:
    """按场景参数扰动生成新的输入数据，不修改原始 workbook。"""

    # 每个 DataFrame 都复制一份，避免一个场景改动污染其它场景。
    timeseries = workbook.timeseries.copy(deep=True)
    device_params = workbook.device_params.copy(deep=True)
    economic_params = workbook.economic_params.copy(deep=True)
    scenarios = workbook.scenarios.copy(deep=True)

    if "carbon_price_cny_per_tco2" in case.changes:
        # 碳价在当前模型中来自逐时输入表，单位为 元/tCO2。
        carbon_price = case.changes["carbon_price_cny_per_tco2"]
        timeseries["carbon_price_cny_per_tco2"] = carbon_price
        _set_parameter_value(economic_params, "carbon_price", carbon_price)

    if "renewable_available_scale" in case.changes:
        # 新能源倍率同时作用于光伏和风电可发功率。
        scale = case.changes["renewable_available_scale"]
        timeseries["pv_available_kw"] = timeseries["pv_available_kw"] * scale
        timeseries["wind_available_kw"] = timeseries["wind_available_kw"] * scale

    if "battery_power_scale" in case.changes:
        # 电池功率倍率作用于充放电功率上限。
        scale = case.changes["battery_power_scale"]
        _scale_parameter_value(device_params, "battery_power_kW", scale)

    if "battery_energy_scale" in case.changes:
        # 电池容量倍率同时作用于容量和初始 SOC，避免初始 SOC 超过容量。
        scale = case.changes["battery_energy_scale"]
        _scale_parameter_value(device_params, "battery_energy_kWh", scale)
        _scale_parameter_value(device_params, "battery_initial_soc", scale)

    if "hydrogen_load_scale" in case.changes:
        # 氢负荷倍率只改变外部氢需求，不改变设备容量。
        scale = case.changes["hydrogen_load_scale"]
        timeseries["hydrogen_load_kg"] = timeseries["hydrogen_load_kg"] * scale

    if "valley_price_scale" in case.changes or "peak_price_scale" in case.changes:
        # 峰谷价差扰动按价格数值识别：最小电价为谷价，最大电价为峰价，平价不变。
        prices = timeseries["electricity_price_cny_per_kwh"]
        valley_price = prices.min()
        peak_price = prices.max()
        if "valley_price_scale" in case.changes:
            valley_mask = prices == valley_price
            timeseries.loc[valley_mask, "electricity_price_cny_per_kwh"] = (
                timeseries.loc[valley_mask, "electricity_price_cny_per_kwh"]
                * case.changes["valley_price_scale"]
            )
        if "peak_price_scale" in case.changes:
            peak_mask = prices == peak_price
            timeseries.loc[peak_mask, "electricity_price_cny_per_kwh"] = (
                timeseries.loc[peak_mask, "electricity_price_cny_per_kwh"]
                * case.changes["peak_price_scale"]
            )

    if "gas_price_scale" in case.changes:
        # 天然气价格倍率作用于逐时天然气价格和经济参数表中的基准价格。
        scale = case.changes["gas_price_scale"]
        timeseries["gas_price_cny_per_m3"] = timeseries["gas_price_cny_per_m3"] * scale
        _scale_parameter_value(economic_params, "gas_price", scale)

    if "grid_emission_factor_scale" in case.changes:
        # 电网排放因子倍率作用于逐时排放因子和经济参数表中的基准排放因子。
        scale = case.changes["grid_emission_factor_scale"]
        timeseries["grid_emission_kgco2_per_kwh"] = (
            timeseries["grid_emission_kgco2_per_kwh"] * scale
        )
        _scale_parameter_value(economic_params, "grid_emission_factor", scale)

    if "electrolyzer_power_scale" in case.changes:
        # 电解槽容量倍率作用于电解槽最大耗电功率。
        scale = case.changes["electrolyzer_power_scale"]
        _scale_parameter_value(device_params, "electrolyzer_power_kW", scale)

    if "h2_storage_capacity_scale" in case.changes:
        # 储氢罐容量倍率只改变容量，不改变初始储氢量。
        scale = case.changes["h2_storage_capacity_scale"]
        _scale_parameter_value(device_params, "h2_storage_capacity_kg", scale)

    if "fuel_cell_power_scale" in case.changes:
        # 燃料电池容量倍率作用于燃料电池最大发电功率。
        scale = case.changes["fuel_cell_power_scale"]
        _scale_parameter_value(device_params, "fuel_cell_power_kW", scale)

    if "h2_sale_price_cny_per_kg" in case.changes:
        # 售氢场景启用售氢收益；非售氢场景默认 h2_sale_enabled 为 0。
        price = case.changes["h2_sale_price_cny_per_kg"]
        _upsert_parameter_value(economic_params, "h2_sale_price", price)
        _upsert_parameter_value(economic_params, "h2_sale_enabled", 1.0)

    if "carbon_emission_cap_kg" in case.changes:
        # 碳上限场景写入日总碳排放上限，单位 kgCO2。
        _upsert_parameter_value(
            economic_params,
            "carbon_emission_cap_kg",
            case.changes["carbon_emission_cap_kg"],
        )
        _upsert_parameter_value(economic_params, "carbon_cap_excess_penalty", 10000.0)

    if "renewable_min_consumption_rate" in case.changes:
        # 新能源消纳率约束写入经济参数表，模型阶段作为全局参数读取。
        _upsert_parameter_value(
            economic_params,
            "renewable_min_consumption_rate",
            case.changes["renewable_min_consumption_rate"],
        )

    return InputWorkbook(
        timeseries=timeseries,
        device_params=device_params,
        economic_params=economic_params,
        scenarios=scenarios,
    )


def run_sensitivity_study(
    workbook: InputWorkbook,
    study: SensitivityStudy,
    output_dir: str | Path,
) -> dict[str, Path]:
    """运行一组敏感性场景，并按场景分目录导出结果。"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results: list[ScenarioResult] = []
    metadata_rows: list[dict[str, float | str]] = []

    for case in study.cases:
        result = _run_sensitivity_case(workbook, study, case)
        results.append(result)

        case_dir = output_path / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        _export_single_case(result, case, study, case_dir)

        metadata_rows.append(_case_metadata(study, case))

    summary = pd.DataFrame([result.summary for result in results])
    hourly = pd.concat([result.hourly_results for result in results], ignore_index=True)
    metadata = pd.DataFrame(metadata_rows)
    summary = summary.merge(metadata, on="scenario_id", how="left")
    hourly = hourly.merge(metadata, on="scenario_id", how="left")

    summary_csv = output_path / "scenario_summary.csv"
    summary_excel = output_path / "scenario_summary.xlsx"
    hourly_csv = output_path / "scenario_hourly_results.csv"
    hourly_excel = output_path / "scenario_hourly_results.xlsx"
    metadata_csv = output_path / "scenario_metadata.csv"
    metadata_excel = output_path / "scenario_metadata.xlsx"

    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary.to_excel(summary_excel, index=False)
    hourly.to_csv(hourly_csv, index=False, encoding="utf-8-sig")
    hourly.to_excel(hourly_excel, index=False)
    metadata.to_csv(metadata_csv, index=False, encoding="utf-8-sig")
    metadata.to_excel(metadata_excel, index=False)

    figure_paths = _plot_study_comparisons(summary, study, output_path)
    conclusion_md = _export_study_conclusion(summary, study, output_path / "conclusion.md")

    return {
        "summary_csv": summary_csv,
        "summary_excel": summary_excel,
        "hourly_csv": hourly_csv,
        "hourly_excel": hourly_excel,
        "metadata_csv": metadata_csv,
        "metadata_excel": metadata_excel,
        "conclusion_md": conclusion_md,
        **figure_paths,
    }


def run_v1_1_sensitivity_analysis(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, dict[str, Path]]:
    """运行 v1.1 四组参数敏感性分析，结果写入 outputs/results。"""

    workbook = load_input_workbook(workbook_path)
    results_root = Path(output_root) / "results"
    results_root.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, dict[str, Path]] = {}
    for study in get_v1_1_sensitivity_studies().values():
        outputs[study.study_id] = run_sensitivity_study(
            workbook,
            study,
            results_root / study.study_id,
        )

    _export_v1_1_index(outputs, results_root / "v1_1_index.md")
    return outputs


def run_v1_2_sensitivity_analysis(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, dict[str, Path]]:
    """运行 v1.2 三组价格与排放因子敏感性分析，结果写入 outputs/results。"""

    workbook = load_input_workbook(workbook_path)
    results_root = Path(output_root) / "results"
    results_root.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, dict[str, Path]] = {}
    for study in get_v1_2_sensitivity_studies().values():
        outputs[study.study_id] = run_sensitivity_study(
            workbook,
            study,
            results_root / study.study_id,
        )

    _export_index(outputs, results_root / "v1_2_index.md", "v1.2 价格与排放因子敏感性分析输出索引")
    return outputs


def run_v1_3_sensitivity_analysis(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, dict[str, Path]]:
    """运行 v1.3 三组设备容量组合敏感性分析，结果写入 outputs/results。"""

    workbook = load_input_workbook(workbook_path)
    results_root = Path(output_root) / "results"
    results_root.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, dict[str, Path]] = {}
    for study in get_v1_3_sensitivity_studies().values():
        outputs[study.study_id] = run_sensitivity_study(
            workbook,
            study,
            results_root / study.study_id,
        )

    _export_index(outputs, results_root / "v1_3_index.md", "v1.3 设备容量组合敏感性分析输出索引")
    return outputs


def run_v1_4_sensitivity_analysis(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, dict[str, Path]]:
    """运行 v1.4 售氢收益、碳约束和新能源消纳率约束场景。"""

    workbook = load_input_workbook(workbook_path)
    results_root = Path(output_root) / "results"
    results_root.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, dict[str, Path]] = {}
    for study in get_v1_4_sensitivity_studies().values():
        prepared_study = _prepare_carbon_cap_study(workbook, study)
        outputs[prepared_study.study_id] = run_sensitivity_study(
            workbook,
            prepared_study,
            results_root / prepared_study.study_id,
        )

    _export_index(outputs, results_root / "v1_4_index.md", "v1.4 政策约束与售氢收益场景输出索引")
    return outputs


def _prepare_carbon_cap_study(
    workbook: InputWorkbook,
    study: SensitivityStudy,
) -> SensitivityStudy:
    """把碳排放上限比例转换为具体 kgCO2 上限。"""

    if study.study_id != "carbon_cap_sensitivity":
        return study

    baseline = _run_sensitivity_case(
        workbook,
        SensitivityStudy(
            study_id="carbon_cap_baseline",
            title="碳排放上限基准",
            base_scenario_id=study.base_scenario_id,
            x_label="基准",
            x_column="baseline",
            cases=[SensitivityCase("BASE", "基准", {"baseline": 1.0})],
        ),
        SensitivityCase("BASE", "基准", {"baseline": 1.0}),
    )
    baseline_carbon = float(baseline.summary["carbon_emission_kg"])

    prepared_cases = [
        SensitivityCase(
            case.case_id,
            case.label,
            {
                **case.changes,
                "carbon_emission_cap_kg": baseline_carbon
                * float(case.changes["carbon_cap_ratio"]),
            },
        )
        for case in study.cases
    ]
    return SensitivityStudy(
        study_id=study.study_id,
        title=study.title,
        base_scenario_id=study.base_scenario_id,
        x_label=study.x_label,
        x_column=study.x_column,
        cases=prepared_cases,
    )


def _run_sensitivity_case(
    workbook: InputWorkbook,
    study: SensitivityStudy,
    case: SensitivityCase,
) -> ScenarioResult:
    """运行单个敏感性场景。"""

    changed_workbook = apply_sensitivity_case(workbook, case)
    scenario = get_minimal_scenario_config(study.base_scenario_id)
    model = build_minimal_milp_model(
        timeseries=changed_workbook.timeseries,
        device_params=changed_workbook.device_params,
        economic_params=changed_workbook.economic_params,
        scenario=scenario,
    )
    status = solve_model(model)

    # 提取结果时使用敏感性场景编号，便于输出表和图片按 C0/R0/B0/H0 区分。
    return extract_minimal_results(model, case.case_id, status)


def _export_single_case(
    result: ScenarioResult,
    case: SensitivityCase,
    study: SensitivityStudy,
    output_dir: Path,
) -> None:
    """导出单个场景的表格和图表。"""

    summary = pd.DataFrame([{**result.summary, **_case_metadata(study, case)}])
    hourly = result.hourly_results.copy()
    metadata = _case_metadata(study, case)
    for key, value in metadata.items():
        hourly[key] = value

    summary.to_csv(output_dir / "scenario_summary.csv", index=False, encoding="utf-8-sig")
    summary.to_excel(output_dir / "scenario_summary.xlsx", index=False)
    hourly.to_csv(
        output_dir / "scenario_hourly_results.csv",
        index=False,
        encoding="utf-8-sig",
    )
    hourly.to_excel(output_dir / "scenario_hourly_results.xlsx", index=False)
    pd.DataFrame([metadata]).to_csv(
        output_dir / "scenario_metadata.csv",
        index=False,
        encoding="utf-8-sig",
    )

    plot_device_outputs(hourly, output_dir / "device_outputs.png")
    plot_battery_soc(hourly, output_dir / "battery_soc.png")
    plot_h2_storage(hourly, output_dir / "h2_storage.png")
    _export_study_conclusion(summary, study, output_dir / "conclusion.md")


def _case_metadata(
    study: SensitivityStudy,
    case: SensitivityCase,
) -> dict[str, float | str]:
    """生成场景元数据。"""

    return {
        "scenario_id": case.case_id,
        "case_label": case.label,
        "study_id": study.study_id,
        "study_title": study.title,
        "base_scenario_id": study.base_scenario_id,
        "x_label": study.x_label,
        "x_value": _case_x_value(study, case),
    }


def _case_x_value(study: SensitivityStudy, case: SensitivityCase) -> float:
    """取得对比图横轴数值。"""

    return float(case.changes[study.x_column])


def _plot_study_comparisons(
    summary: pd.DataFrame,
    study: SensitivityStudy,
    output_dir: Path,
) -> dict[str, Path]:
    """绘制一组敏感性场景的对比图。"""

    summary = summary.sort_values("x_value")
    renewable_total = summary["renewable_used_kwh"] + summary["renewable_curtailment_kwh"]
    summary = summary.assign(
        renewable_consumption_rate=(
            summary["renewable_used_kwh"] / renewable_total.replace(0, pd.NA)
        ).fillna(0)
    )

    paths = {
        "cost_png": output_dir / "cost_vs_parameter.png",
        "carbon_png": output_dir / "carbon_vs_parameter.png",
        "grid_png": output_dir / "grid_purchase_vs_parameter.png",
        "renewable_png": output_dir / "renewable_consumption_vs_parameter.png",
    }

    _line_plot(summary, study, "total_cost_cny", "系统总成本/元", paths["cost_png"])
    _line_plot(summary, study, "carbon_emission_kg", "碳排放/kgCO2", paths["carbon_png"])
    _line_plot(summary, study, "grid_purchase_kwh", "购电量/kWh", paths["grid_png"])
    _line_plot(
        summary,
        study,
        "renewable_consumption_rate",
        "新能源消纳率",
        paths["renewable_png"],
    )

    if study.study_id == "battery_capacity_sensitivity":
        paths["battery_soc_png"] = output_dir / "battery_soc_max_vs_parameter.png"
        _line_plot(summary, study, "battery_soc_max_kwh", "最大 SOC/kWh", paths["battery_soc_png"])
    if study.study_id == "hydrogen_load_sensitivity":
        paths["h2_production_png"] = output_dir / "h2_production_vs_parameter.png"
        _line_plot(summary, study, "h2_production_kg", "制氢量/kg", paths["h2_production_png"])
    if study.study_id == "electricity_price_spread_sensitivity":
        paths["battery_charge_png"] = output_dir / "battery_charge_vs_parameter.png"
        paths["battery_discharge_png"] = output_dir / "battery_discharge_vs_parameter.png"
        paths["electrolyzer_power_png"] = output_dir / "electrolyzer_power_vs_parameter.png"
        _line_plot(summary, study, "battery_charge_kwh", "电池充电量/kWh", paths["battery_charge_png"])
        _line_plot(
            summary,
            study,
            "battery_discharge_kwh",
            "电池放电量/kWh",
            paths["battery_discharge_png"],
        )
        _line_plot(
            summary,
            study,
            "electrolyzer_power_kwh",
            "电解槽耗电量/kWh",
            paths["electrolyzer_power_png"],
        )
    if study.study_id == "gas_price_sensitivity":
        paths["gas_boiler_heat_png"] = output_dir / "gas_boiler_heat_vs_parameter.png"
        paths["heat_pump_heat_png"] = output_dir / "heat_pump_heat_vs_parameter.png"
        _line_plot(summary, study, "gas_boiler_heat_kwh", "燃气锅炉供热量/kWh", paths["gas_boiler_heat_png"])
        _line_plot(summary, study, "heat_pump_heat_kwh", "热泵供热量/kWh", paths["heat_pump_heat_png"])
    if study.study_id == "grid_emission_factor_sensitivity":
        paths["carbon_cost_png"] = output_dir / "carbon_cost_vs_parameter.png"
        _line_plot(summary, study, "carbon_cost_cny", "碳成本/元", paths["carbon_cost_png"])
    if study.study_id == "electrolyzer_capacity_sensitivity":
        paths["h2_production_png"] = output_dir / "h2_production_vs_parameter.png"
        paths["curtailment_png"] = output_dir / "renewable_curtailment_vs_parameter.png"
        paths["external_h2_png"] = output_dir / "h2_external_supply_vs_parameter.png"
        _line_plot(summary, study, "h2_production_kg", "制氢量/kg", paths["h2_production_png"])
        _line_plot(
            summary,
            study,
            "renewable_curtailment_kwh",
            "弃风弃光量/kWh",
            paths["curtailment_png"],
        )
        _line_plot(
            summary,
            study,
            "h2_external_supply_kg",
            "外部补氢量/kg",
            paths["external_h2_png"],
        )
    if study.study_id == "h2_storage_capacity_sensitivity":
        paths["h2_storage_max_png"] = output_dir / "h2_storage_max_vs_parameter.png"
        paths["h2_production_png"] = output_dir / "h2_production_vs_parameter.png"
        paths["curtailment_png"] = output_dir / "renewable_curtailment_vs_parameter.png"
        _line_plot(summary, study, "h2_storage_max_kg", "最大储氢量/kg", paths["h2_storage_max_png"])
        _line_plot(summary, study, "h2_production_kg", "制氢量/kg", paths["h2_production_png"])
        _line_plot(
            summary,
            study,
            "renewable_curtailment_kwh",
            "弃风弃光量/kWh",
            paths["curtailment_png"],
        )
    if study.study_id == "fuel_cell_capacity_sensitivity":
        paths["fuel_cell_generation_png"] = output_dir / "fuel_cell_generation_vs_parameter.png"
        paths["h2_fuel_cell_png"] = output_dir / "h2_fuel_cell_vs_parameter.png"
        _line_plot(
            summary,
            study,
            "fuel_cell_generation_kwh",
            "燃料电池发电量/kWh",
            paths["fuel_cell_generation_png"],
        )
        _line_plot(summary, study, "h2_fuel_cell_kg", "燃料电池耗氢量/kg", paths["h2_fuel_cell_png"])
    if study.study_id == "h2_sale_price_sensitivity":
        paths["h2_sale_png"] = output_dir / "h2_sale_vs_parameter.png"
        paths["h2_sale_revenue_png"] = output_dir / "h2_sale_revenue_vs_parameter.png"
        paths["electrolyzer_power_png"] = output_dir / "electrolyzer_power_vs_parameter.png"
        _line_plot(summary, study, "h2_sale_kg", "售氢量/kg", paths["h2_sale_png"])
        _line_plot(
            summary,
            study,
            "h2_sale_revenue_cny",
            "售氢收益/元",
            paths["h2_sale_revenue_png"],
        )
        _line_plot(
            summary,
            study,
            "electrolyzer_power_kwh",
            "电解槽耗电量/kWh",
            paths["electrolyzer_power_png"],
        )
    if study.study_id == "carbon_cap_sensitivity":
        paths["carbon_excess_png"] = output_dir / "carbon_cap_excess_vs_parameter.png"
        paths["gas_png"] = output_dir / "gas_consumption_vs_parameter.png"
        _line_plot(summary, study, "carbon_cap_excess_kg", "碳上限超额量/kgCO2", paths["carbon_excess_png"])
        _line_plot(summary, study, "gas_consumption_m3", "天然气消耗量/m3", paths["gas_png"])
    if study.study_id == "renewable_consumption_constraint_sensitivity":
        paths["battery_charge_png"] = output_dir / "battery_charge_vs_parameter.png"
        paths["h2_production_png"] = output_dir / "h2_production_vs_parameter.png"
        _line_plot(summary, study, "battery_charge_kwh", "电池充电量/kWh", paths["battery_charge_png"])
        _line_plot(summary, study, "h2_production_kg", "制氢量/kg", paths["h2_production_png"])

    return paths


def _line_plot(
    summary: pd.DataFrame,
    study: SensitivityStudy,
    y_column: str,
    y_label: str,
    output_path: Path,
) -> None:
    """绘制敏感性折线图。"""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.plot(summary["x_value"], summary[y_column], marker="o")
    for row in summary.itertuples(index=False):
        ax.annotate(
            str(row.scenario_id),
            (float(row.x_value), float(getattr(row, y_column))),
            textcoords="offset points",
            xytext=(0, 7),
            ha="center",
            fontsize=9,
        )
    ax.set_title(f"{study.title}: {y_label}")
    ax.set_xlabel(study.x_label)
    ax.set_ylabel(y_label)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _export_study_conclusion(
    summary: pd.DataFrame,
    study: SensitivityStudy,
    output_path: Path,
) -> Path:
    """导出一组场景的简短结论。"""

    ordered = summary.sort_values("x_value")
    first = ordered.iloc[0]
    last = ordered.iloc[-1]

    cost_change = last["total_cost_cny"] - first["total_cost_cny"]
    carbon_change = last["carbon_emission_kg"] - first["carbon_emission_kg"]
    curtail_change = last["renewable_curtailment_kwh"] - first["renewable_curtailment_kwh"]

    content = f"""# {study.title} 结果简述

## 场景设置

- 基准模型：{study.base_scenario_id}
- 横轴参数：{study.x_label}
- 场景数量：{len(summary)}

## 关键变化

- 从 {first['scenario_id']} 到 {last['scenario_id']}，系统总成本变化 {cost_change:.2f} 元。
- 从 {first['scenario_id']} 到 {last['scenario_id']}，碳排放变化 {carbon_change:.2f} kgCO2。
- 从 {first['scenario_id']} 到 {last['scenario_id']}，弃风弃光量变化 {curtail_change:.2f} kWh。

## 结果文件

- 汇总表：`scenario_summary.csv`
- 逐时表：`scenario_hourly_results.csv`
- 对比图：`cost_vs_parameter.png`、`carbon_vs_parameter.png`、`grid_purchase_vs_parameter.png`、`renewable_consumption_vs_parameter.png`
"""

    output_path.write_text(content, encoding="utf-8")
    return output_path


def _export_v1_1_index(outputs: dict[str, dict[str, Path]], output_path: Path) -> Path:
    """导出 v1.1 总索引，方便从 results 目录查看。"""

    return _export_index(outputs, output_path, "v1.1 参数敏感性分析输出索引")


def _export_index(
    outputs: dict[str, dict[str, Path]],
    output_path: Path,
    title: str,
) -> Path:
    """导出 results 目录下的分析索引。"""

    lines = [f"# {title}", ""]
    for study_id, paths in outputs.items():
        lines.append(f"## {study_id}")
        lines.append("")
        lines.append(f"- 汇总表：`{paths['summary_csv']}`")
        lines.append(f"- 逐时表：`{paths['hourly_csv']}`")
        lines.append(f"- 结论：`{paths['conclusion_md']}`")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _set_parameter_value(data: pd.DataFrame, parameter: str, value: float) -> None:
    """设置参数表中的单个参数值。"""

    mask = data["parameter"] == parameter
    if mask.any():
        data.loc[mask, "value"] = value


def _upsert_parameter_value(data: pd.DataFrame, parameter: str, value: float) -> None:
    """设置参数值；若参数不存在，则补充一行经济参数。"""

    mask = data["parameter"] == parameter
    if mask.any():
        data.loc[mask, "value"] = value
        return

    data.loc[len(data)] = {
        "category": "场景参数",
        "name_cn": parameter,
        "parameter": parameter,
        "unit": "",
        "value": float(value),
        "sensitivity_range": "",
        "source_attribute": "scenario",
        "source_url": "",
        "description": "场景分析自动补充参数",
    }


def _scale_parameter_value(data: pd.DataFrame, parameter: str, scale: float) -> None:
    """按倍率缩放参数表中的单个参数值。"""

    mask = data["parameter"] == parameter
    if not mask.any():
        raise KeyError(f"参数表中缺少参数: {parameter}")
    data.loc[mask, "value"] = data.loc[mask, "value"].astype(float) * scale
