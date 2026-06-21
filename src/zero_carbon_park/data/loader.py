"""输入数据读取模块。

本模块负责把 Excel 数据包转换成模型更容易使用的标准表。
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class InputWorkbook:
    """Excel 数据包读取后的标准化结果。"""

    timeseries: pd.DataFrame
    device_params: pd.DataFrame
    economic_params: pd.DataFrame
    scenarios: pd.DataFrame


TIMESERIES_COLUMNS = {
    "hour": "hour",
    "pv_cf": "pv_cf",
    "wind_cf": "wind_cf",
    "pv_available_kW": "pv_available_kw",
    "wind_available_kW": "wind_available_kw",
    "electric_load_kW": "electric_load_kw",
    "heat_load_kW": "heat_load_kw",
    "h2_load_kg": "hydrogen_load_kg",
    "tou_period": "tou_period",
    "electricity_price_yuan_per_kWh": "electricity_price_cny_per_kwh",
    "gas_price_yuan_per_m3": "gas_price_cny_per_m3",
    "grid_emission_kgCO2_per_kWh": "grid_emission_kgco2_per_kwh",
    "carbon_price_yuan_per_tCO2": "carbon_price_cny_per_tco2",
}

OPTIONAL_TIMESERIES_COLUMNS = [
    "heat_pump_cop",
    "heat_pump_available_ratio",
    "electrolyzer_kwh_per_kg",
    "fuel_cell_kwh_per_kg",
]

PARAMETER_COLUMNS = {
    "类别": "category",
    "参数": "name_cn",
    "符号/字段": "parameter",
    "单位": "unit",
    "基准值": "value",
    "敏感性范围": "sensitivity_range",
    "来源属性": "source_attribute",
    "来源URL": "source_url",
    "用途/备注": "description",
}

SCENARIO_COLUMNS = {
    "场景编号": "scenario_id",
    "场景名称": "scenario_name",
    "启用技术/机制": "enabled_items",
    "关键设置": "key_settings",
    "主要观察指标": "main_metrics",
    "作用": "purpose",
}

ECONOMIC_CATEGORIES = {
    "能源价格",
    "碳价",
    "碳排放",
    "惩罚成本",
    "运维成本",
    "政策约束",
}


def load_input_workbook(path: str | Path) -> InputWorkbook:
    """读取用户提供的 Excel 数据包。

    参数:
        path: Excel 数据包路径。

    返回:
        标准化后的时间序列、设备参数、经济参数和场景表。
    """

    workbook_path = Path(path)

    # 读取 24 小时时间序列，并删除说明列，避免模型阶段混入文本字段。
    timeseries = pd.read_excel(workbook_path, sheet_name=3)
    timeseries = timeseries.rename(columns=TIMESERIES_COLUMNS)
    timeseries_columns = list(TIMESERIES_COLUMNS.values()) + [
        column for column in OPTIONAL_TIMESERIES_COLUMNS if column in timeseries.columns
    ]
    timeseries = timeseries[timeseries_columns]
    timeseries["hour"] = timeseries["hour"].astype(int)

    # 读取参数总表，并统一字段名。
    params = pd.read_excel(workbook_path, sheet_name=4)
    params = params.rename(columns=PARAMETER_COLUMNS)
    params = params[list(PARAMETER_COLUMNS.values())]

    # 基准值统一转成数值，便于后续模型直接构造参数字典。
    params["value"] = pd.to_numeric(params["value"], errors="coerce")

    # 经济参数和设备参数分开保存，模型阶段更清晰。
    economic_params = params[params["category"].isin(ECONOMIC_CATEGORIES)].reset_index(
        drop=True
    )
    device_params = params[~params["category"].isin(ECONOMIC_CATEGORIES)].reset_index(
        drop=True
    )

    # 读取场景设置，并统一字段名。
    scenarios = pd.read_excel(workbook_path, sheet_name=5)
    scenarios = scenarios.rename(columns=SCENARIO_COLUMNS)
    scenarios = scenarios[list(SCENARIO_COLUMNS.values())]

    return InputWorkbook(
        timeseries=timeseries,
        device_params=device_params,
        economic_params=economic_params,
        scenarios=scenarios,
    )


def export_processed_inputs(
    workbook_path: str | Path, output_dir: str | Path
) -> dict[str, Path]:
    """把 Excel 数据包导出为模型可直接读取的 CSV 和 Excel 文件。"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    workbook = load_input_workbook(workbook_path)
    exports = {
        "timeseries": workbook.timeseries,
        "device_params": workbook.device_params,
        "economic_params": workbook.economic_params,
        "scenarios": workbook.scenarios,
    }

    paths: dict[str, Path] = {}
    for name, frame in exports.items():
        csv_path = output_path / f"{name}.csv"
        excel_path = output_path / f"{name}.xlsx"

        # CSV 用 utf-8-sig，方便 Excel 直接打开中文不乱码。
        frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
        frame.to_excel(excel_path, index=False)

        paths[f"{name}_csv"] = csv_path
        paths[f"{name}_excel"] = excel_path

    return paths
