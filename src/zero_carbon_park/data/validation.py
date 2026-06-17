"""输入数据校验模块。"""

import pandas as pd


REQUIRED_TIMESERIES_COLUMNS = {
    "hour",
    "pv_cf",
    "wind_cf",
    "pv_available_kw",
    "wind_available_kw",
    "electric_load_kw",
    "heat_load_kw",
    "hydrogen_load_kg",
    "tou_period",
    "electricity_price_cny_per_kwh",
    "gas_price_cny_per_m3",
    "grid_emission_kgco2_per_kwh",
    "carbon_price_cny_per_tco2",
}

NON_NEGATIVE_TIMESERIES_COLUMNS = {
    "pv_cf",
    "wind_cf",
    "pv_available_kw",
    "wind_available_kw",
    "electric_load_kw",
    "heat_load_kw",
    "hydrogen_load_kg",
    "electricity_price_cny_per_kwh",
    "gas_price_cny_per_m3",
    "grid_emission_kgco2_per_kwh",
    "carbon_price_cny_per_tco2",
}

REQUIRED_PARAMETER_COLUMNS = {
    "category",
    "name_cn",
    "parameter",
    "unit",
    "value",
    "sensitivity_range",
    "source_attribute",
    "source_url",
    "description",
}


def validate_timeseries(data: pd.DataFrame, expected_hours: int = 24) -> None:
    """校验 24 小时时间序列是否满足模型输入要求。"""

    missing = REQUIRED_TIMESERIES_COLUMNS - set(data.columns)
    if missing:
        raise ValueError(f"时间序列表缺少字段: {sorted(missing)}")

    if len(data) != expected_hours:
        raise ValueError(f"时间序列应为 {expected_hours} 行，实际为 {len(data)} 行")

    expected_hour_values = list(range(expected_hours))
    actual_hour_values = data["hour"].astype(int).tolist()
    if actual_hour_values != expected_hour_values:
        raise ValueError("hour 字段必须从 0 连续排列到 expected_hours - 1")

    if data[list(REQUIRED_TIMESERIES_COLUMNS)].isna().any().any():
        raise ValueError("时间序列表存在缺失值")

    negative_columns = [
        column
        for column in NON_NEGATIVE_TIMESERIES_COLUMNS
        if (data[column] < 0).any()
    ]
    if negative_columns:
        raise ValueError(f"时间序列表存在负值字段: {negative_columns}")


def validate_parameter_table(data: pd.DataFrame) -> None:
    """校验参数表是否包含模型需要的字段和值。"""

    missing = REQUIRED_PARAMETER_COLUMNS - set(data.columns)
    if missing:
        raise ValueError(f"参数表缺少字段: {sorted(missing)}")

    if data.empty:
        raise ValueError("参数表不能为空")

    if data["parameter"].isna().any():
        raise ValueError("参数表 parameter 字段存在缺失值")

    if data["value"].isna().any():
        missing_values = data.loc[data["value"].isna(), "parameter"].tolist()
        raise ValueError(f"参数表存在无法转为数值的基准值: {missing_values}")
