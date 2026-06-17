"""模型参数定义模块。"""

from __future__ import annotations

import pandas as pd


DEFAULT_PARAMETERS = {
    # 数据包未直接给出天然气低位热值，这里先采用常用工程近似值。
    # 后续如果有更精确燃气组分数据，可以在参数表中增加同名字段覆盖它。
    "gas_lhv_kwh_per_m3": 9.8,
}


def parameter_frame_to_dict(data: pd.DataFrame) -> dict[str, float]:
    """把参数表转换为 {参数名: 参数值} 字典。

    data: 来自数据包标准化后的 device_params 或 economic_params。
    """

    # 先放入默认补充参数，避免模型阶段缺少必要工程换算量。
    parameters = dict(DEFAULT_PARAMETERS)

    # 遍历每一行，把 Excel 中的“符号/字段”和“基准值”转换成模型参数。
    for row in data.itertuples(index=False):
        parameters[str(row.parameter)] = float(row.value)

    return parameters
