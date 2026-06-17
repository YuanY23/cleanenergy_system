"""CSV、Excel 和文字结论导出模块。"""

from pathlib import Path

import pandas as pd


def export_project_conclusions(summary: pd.DataFrame, output_path: str | Path) -> Path:
    """根据场景汇总结果生成项目结论初稿。"""

    conclusion_path = Path(output_path)
    conclusion_path.parent.mkdir(parents=True, exist_ok=True)

    indexed = summary.set_index("scenario_id")
    s0 = indexed.loc["S0"]
    s5 = indexed.loc["S5"]

    grid_reduction = 1 - s5["grid_purchase_kwh"] / s0["grid_purchase_kwh"]
    carbon_reduction = 1 - s5["carbon_emission_kg"] / s0["carbon_emission_kg"]

    text = f"""# 项目结论初稿

## 1. 仿真范围

本项目基于鄂尔多斯零碳园区数据包，完成了 24 小时电-热-氢-储综合能源系统 MILP 优化调度仿真。

已运行场景包括 S0 至 S5：

- S0：传统供能。
- S1：新能源接入。
- S2：新能源 + 电储能。
- S3：新能源 + 电储能 + 制氢储氢。
- S4：完整系统，加入热泵和燃料电池。
- S5：低碳调度，在 S4 基础上加入碳价。

## 2. 关键结果

- S0 系统总成本为 {s0['total_cost_cny']:.2f} 元，购电量为 {s0['grid_purchase_kwh']:.2f} kWh，碳排放为 {s0['carbon_emission_kg']:.2f} kgCO2。
- S5 系统总成本为 {s5['total_cost_cny']:.2f} 元，购电量为 {s5['grid_purchase_kwh']:.2f} kWh，碳排放为 {s5['carbon_emission_kg']:.2f} kgCO2。
- 与 S0 相比，S5 购电量下降约 {grid_reduction:.1%}，碳排放下降约 {carbon_reduction:.1%}。
- S5 碳排放成本为 {s5['carbon_cost_cny']:.2f} 元，说明碳价机制已经进入调度目标函数。

## 3. 当前模型解释

当前模型已经实现风电、光伏、电网、电储能、电解槽、储氢罐、燃料电池、热泵、燃气锅炉和碳排放成本的统一调度。

在当前数据和参数下，燃料电池没有实际出力。这说明电解制氢再发电的路径在当前效率和价格参数下不具备经济优势，但燃料电池变量、转换关系和约束已经接入模型。

## 4. 后续完善方向

下一步可以继续做敏感性分析，包括碳价、氢价、储能容量和新能源渗透率变化；也可以替换更真实的园区负荷、新能源资源和设备参数。
"""

    conclusion_path.write_text(text, encoding="utf-8")
    return conclusion_path


def export_annual_conclusion(
    annual_summary: pd.DataFrame,
    contribution: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """导出多典型日加权年化结论。"""

    conclusion_path = Path(output_path)
    conclusion_path.parent.mkdir(parents=True, exist_ok=True)

    annual = annual_summary.iloc[0]
    max_carbon = contribution.sort_values(
        "weighted_carbon_emission_kg",
        ascending=False,
    ).iloc[0]
    max_cost = contribution.sort_values(
        "weighted_total_cost_cny",
        ascending=False,
    ).iloc[0]

    annual_weight_days = float(annual.get("annual_weight_days", 0.0))

    text = f"""# 多典型日加权年化结果

## 1. 年化口径

本结果基于夏季、冬季和过渡季三个典型日，按代表天数加权形成年度近似结果。当前典型日仍由基准日缩放生成，因此结果用于方法验证和趋势分析。

## 2. 年度核心指标

- 年度代表天数：{annual_weight_days:.0f} 天
- 年度总运行成本：{annual['annual_total_cost_cny']:.2f} 元
- 年度购电量：{annual['annual_grid_purchase_kwh']:.2f} kWh
- 年度碳排放：{annual['annual_carbon_emission_kg']:.2f} kgCO2
- 年度新能源消纳率：{annual['annual_renewable_consumption_rate']:.2%}

## 3. 典型日贡献

- 年度成本贡献最高的典型日：{max_cost['typical_day_id']}，加权成本 {max_cost['weighted_total_cost_cny']:.2f} 元。
- 年度碳排放贡献最高的典型日：{max_carbon['typical_day_id']}，加权碳排放 {max_carbon['weighted_carbon_emission_kg']:.2f} kgCO2。

## 4. 初步结论

多典型日结果可以反映季节差异：冬季热负荷较高，热泵供热和购电需求更大；夏季光伏资源较好但电负荷较高；过渡季整体运行压力较低。后续容量规划应基于该年化口径，而不是只依据单日运行结果。
"""

    conclusion_path.write_text(text, encoding="utf-8")
    return conclusion_path
