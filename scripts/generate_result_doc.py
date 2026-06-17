from __future__ import annotations

from datetime import datetime
from pathlib import Path
import html

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "结果文档.doc"


def read_summary(relative_path: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / relative_path)


def escape(value: object) -> str:
    return html.escape(str(value))


def fmt(value: object) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
        number = float(value)
    except Exception:
        return escape(value)

    if abs(number) >= 100000:
        return f"{number:,.0f}"
    if abs(number) >= 1000:
        return f"{number:,.2f}"
    if abs(number) >= 10:
        return f"{number:,.2f}"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def add_heading(parts: list[str], level: int, text: str) -> None:
    parts.append(f"<h{level}>{escape(text)}</h{level}>")


def add_paragraph(parts: list[str], text: str) -> None:
    parts.append(f"<p>{escape(text)}</p>")


def add_list(parts: list[str], items: list[str]) -> None:
    parts.append("<ul>")
    for item in items:
        parts.append(f"<li>{escape(item)}</li>")
    parts.append("</ul>")


def table_from_rows(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["<table>"]
    lines.append("<tr>" + "".join(f"<th>{escape(header)}</th>" for header in headers) + "</tr>")
    for row in rows:
        lines.append("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def table_from_frame(df: pd.DataFrame, columns: list[tuple[str, str]]) -> str:
    selected = [(column, header) for column, header in columns if column in df.columns]
    lines = ["<table>"]
    lines.append("<tr>" + "".join(f"<th>{escape(header)}</th>" for _, header in selected) + "</tr>")
    output_df = df.copy()
    if "x_value" in output_df.columns:
        output_df = output_df.sort_values("x_value")
    for _, row in output_df.iterrows():
        cells = []
        for column, _ in selected:
            cells.append(f"<td>{fmt(row[column])}</td>")
        lines.append("<tr>" + "".join(cells) + "</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def extremes(df: pd.DataFrame) -> list[str]:
    min_cost = df.loc[df["total_cost_cny"].idxmin()]
    max_cost = df.loc[df["total_cost_cny"].idxmax()]
    min_carbon = df.loc[df["carbon_emission_kg"].idxmin()]
    max_carbon = df.loc[df["carbon_emission_kg"].idxmax()]
    return [
        f"成本最低场景为 {min_cost['scenario_id']}，总成本 {fmt(min_cost['total_cost_cny'])} 元；成本最高场景为 {max_cost['scenario_id']}，总成本 {fmt(max_cost['total_cost_cny'])} 元。",
        f"碳排放最低场景为 {min_carbon['scenario_id']}，碳排放 {fmt(min_carbon['carbon_emission_kg'])} kgCO2；碳排放最高场景为 {max_carbon['scenario_id']}，碳排放 {fmt(max_carbon['carbon_emission_kg'])} kgCO2。",
    ]


def add_group(
    parts: list[str],
    title: str,
    csv_path: str,
    model_text: str,
    system_text: str,
    setting_text: str,
    columns: list[tuple[str, str]],
    findings: list[str],
) -> None:
    df = read_summary(csv_path)
    add_heading(parts, 2, title)
    add_paragraph(parts, f"模型/系统：{model_text}")
    add_paragraph(parts, f"涉及系统：{system_text}")
    add_paragraph(parts, f"场景设置：{setting_text}")
    add_paragraph(parts, f"本组共 {len(df)} 个场景，求解状态为：{', '.join(sorted(map(str, df['status'].unique())))}。")
    parts.append(table_from_frame(df, columns))
    add_paragraph(parts, "主要发现：")
    add_list(parts, extremes(df) + findings)


COMMON_COLUMNS = [
    ("scenario_id", "场景"),
    ("case_label", "设置"),
    ("status", "状态"),
    ("x_value", "参数值"),
    ("total_cost_cny", "总成本/元"),
    ("grid_purchase_kwh", "购电量/kWh"),
    ("renewable_curtailment_kwh", "弃风弃光/kWh"),
    ("carbon_emission_kg", "碳排放/kgCO2"),
    ("carbon_cost_cny", "碳成本/元"),
]


def build_document() -> str:
    parts: list[str] = [
        """<!DOCTYPE html><html><head><meta charset="utf-8"><title>零碳园区优化调度结果文档</title>
<style>
@page { size: A4; margin: 2cm; }
body { font-family: "Microsoft YaHei", SimSun, Arial, sans-serif; font-size: 10.5pt; line-height: 1.55; color: #222; }
h1 { text-align: center; font-size: 22pt; margin-top: 80px; }
h2 { font-size: 16pt; margin-top: 24px; border-bottom: 1px solid #888; padding-bottom: 4px; }
p { margin: 6px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px 0; font-size: 8.5pt; }
th { background: #D9EAF7; font-weight: bold; }
th, td { border: 1px solid #999; padding: 4px 5px; vertical-align: top; }
.pagebreak { page-break-before: always; }
</style></head><body>""",
        "<h1>零碳园区电-热-氢-储优化调度结果文档</h1>",
        f'<p style="text-align:center">生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}</p>',
        '<p style="text-align:center">数据来源：鄂尔多斯零碳园区_电热氢储优化调度_数据包.xlsx；结果来源：outputs/runs/first_version 与 outputs/results。</p>',
        '<div class="pagebreak"></div>',
    ]

    add_heading(parts, 2, "一、总体说明")
    add_paragraph(
        parts,
        "本文件汇总当前项目已经完成的所有基础场景和敏感性/政策场景结果。模型采用 24 小时日前 MILP 优化调度，求解器为开源 HiGHS。系统边界包括电网、风电、光伏、电池储能、电解槽、储氢罐、燃料电池、热泵、燃气锅炉、碳排放核算，以及 v1.4 中新增的售氢收益、碳排放上限和新能源消纳率约束。",
    )
    add_paragraph(
        parts,
        "文档中的总成本为模型目标函数值，已经包含购电、天然气、弃风弃光惩罚、碳成本、设备运维、外部补氢成本，并在售氢场景中扣除了售氢收益。",
    )
    parts.append(
        table_from_rows(
            ["阶段", "场景数量", "主要内容"],
            [
                ["基础 S0-S5", "6", "传统供能、新能源、电池、氢能、燃料电池/热泵、碳价"],
                ["v1.1 参数敏感性", "23", "碳价、新能源倍率、电池容量、氢负荷"],
                ["v1.2 价格与排放因子", "14", "峰谷电价、天然气价格、电网排放因子"],
                ["v1.3 设备容量组合", "15", "电解槽、储氢罐、燃料电池容量"],
                ["v1.4 政策和收益机制", "14", "售氢收益、碳排放上限、新能源消纳率约束"],
            ],
        )
    )

    add_heading(parts, 2, "二、基础场景 S0-S5")
    base = read_summary("outputs/runs/first_version/scenario_summary.csv")
    base["scenario_meaning"] = base["scenario_id"].map(
        {
            "S0": "传统供能：电网购电 + 燃气锅炉",
            "S1": "加入风电和光伏",
            "S2": "加入电池储能",
            "S3": "加入电解槽、储氢罐和氢负荷",
            "S4": "完整电-热-氢-储系统：热泵 + 燃料电池",
            "S5": "S4 基础上加入碳价成本",
        }
    )
    add_paragraph(parts, "模型/系统：基础场景用于验证系统从传统供能到完整电-热-氢-储耦合系统的逐步构建效果。")
    parts.append(
        table_from_frame(
            base,
            [
                ("scenario_id", "场景"),
                ("scenario_meaning", "含义"),
                ("status", "状态"),
                ("total_cost_cny", "总成本/元"),
                ("grid_purchase_kwh", "购电量/kWh"),
                ("renewable_curtailment_kwh", "弃风弃光/kWh"),
                ("carbon_emission_kg", "碳排放/kgCO2"),
                ("carbon_cost_cny", "碳成本/元"),
            ],
        )
    )
    add_paragraph(parts, "主要发现：")
    add_list(
        parts,
        [
            "S0 是传统供能基准，购电量和碳排放最高。",
            "S1 引入风电光伏后，总成本和碳排放显著下降，但出现弃风弃光。",
            "S2 加入电池后，弃风弃光明显下降，系统成本继续降低。",
            "S3 加入氢负荷后，制氢需求提高了购电量和成本。",
            "S4 引入热泵后替代燃气锅炉，系统总成本显著下降；当前参数下燃料电池不运行。",
            "S5 在 S4 上加入碳价，物理调度基本一致，但总成本增加了碳成本。",
        ],
    )

    add_heading(parts, 2, "三、v1.1 参数敏感性场景")
    add_group(parts, "3.1 碳价敏感性 C0-C5", "outputs/results/carbon_price_sensitivity/scenario_summary.csv", "完整 S5 系统 + 不同碳价。", "电网、风光、电池、热泵、锅炉、电解槽、储氢、燃料电池、碳成本。", "碳价分别为 0、30、60、100、150、200 元/tCO2。", COMMON_COLUMNS, ["碳价升高后，总成本随碳成本上升而增加。", "当前设备组合下，碳价变化对物理调度影响有限，更多体现为成本核算变化。"])
    add_group(parts, "3.2 新能源出力比例 R0-R5", "outputs/results/renewable_scale_sensitivity/scenario_summary.csv", "完整 S5 系统 + 风光可发功率倍率扰动。", "重点观察新能源接入、弃电、购电和碳排放。", "风电和光伏可发功率倍率为 0.6、0.8、1.0、1.2、1.5、2.0。", COMMON_COLUMNS, ["新能源资源增加总体降低购电依赖。", "高倍率下仍需要关注储能和氢能消纳空间。"])
    add_group(parts, "3.3 电池容量 B0-B5", "outputs/results/battery_capacity_sensitivity/scenario_summary.csv", "完整 S5 系统 + 电池功率/容量同步倍率扰动。", "重点观察电池充放电、SOC、弃电和成本。", "电池功率和容量倍率为 0、0.5、1.0、1.5、2.0、3.0。", COMMON_COLUMNS + [("battery_charge_kwh", "充电量/kWh"), ("battery_discharge_kwh", "放电量/kWh"), ("battery_soc_max_kwh", "最大SOC/kWh")], ["电池可以降低弃风弃光和系统成本。", "电池容量继续扩大后边际收益下降。"])
    add_group(parts, "3.4 氢负荷 H0-H4", "outputs/results/hydrogen_load_sensitivity/scenario_summary.csv", "完整 S5 系统 + 氢负荷倍率扰动。", "重点观察制氢、储氢、外部补氢和成本。", "氢负荷倍率为 0、0.5、1.0、1.5、2.0。", COMMON_COLUMNS + [("hydrogen_load_kg", "氢负荷/kg"), ("h2_production_kg", "制氢量/kg"), ("h2_external_supply_kg", "外部补氢/kg")], ["高氢负荷会暴露电解槽和储氢系统的供氢能力边界。", "外部补氢变量用于记录本地供氢不足时的缺口。"])

    add_heading(parts, 2, "四、v1.2 价格与排放因子场景")
    add_group(parts, "4.1 电价峰谷差 P0-P4", "outputs/results/electricity_price_spread_sensitivity/scenario_summary.csv", "完整 S5 系统 + 谷价/峰价倍率扰动。", "重点观察电池、电解槽、购电成本和供热方式。", "谷价倍率从 1.0 降到 0.6，峰价倍率从 1.0 升到 1.5。", COMMON_COLUMNS + [("battery_charge_kwh", "充电量/kWh"), ("battery_discharge_kwh", "放电量/kWh"), ("electrolyzer_power_kwh", "电解槽耗电/kWh"), ("gas_boiler_heat_kwh", "锅炉供热/kWh"), ("heat_pump_heat_kwh", "热泵供热/kWh")], ["峰谷价差变化会改变购电成本和供热组合。", "价差扩大后，系统更倾向利用低价时段购电，运行成本整体下降。"])
    add_group(parts, "4.2 天然气价格 G0-G4", "outputs/results/gas_price_sensitivity/scenario_summary.csv", "完整 S5 系统 + 天然气价格倍率扰动。", "重点观察热泵与燃气锅炉的替代关系。", "天然气价格倍率为 0.8、1.0、1.2、1.5、2.0。", COMMON_COLUMNS + [("gas_boiler_heat_kwh", "锅炉供热/kWh"), ("heat_pump_heat_kwh", "热泵供热/kWh"), ("gas_consumption_m3", "天然气/m3")], ["低天然气价格下，燃气锅炉会参与供热。", "天然气价格提高后，热泵成为主要供热方式。"])
    add_group(parts, "4.3 电网排放因子 E0-E3", "outputs/results/grid_emission_factor_sensitivity/scenario_summary.csv", "完整 S5 系统 + 电网排放因子倍率扰动。", "重点观察外部电网低碳化对碳排放和碳成本的影响。", "电网排放因子倍率为 0.4、0.7、1.0、1.2。", COMMON_COLUMNS, ["电网排放因子变化时，购电调度基本不变。", "外部电网低碳化能够直接降低园区核算碳排放和碳成本。"])

    add_heading(parts, 2, "五、v1.3 设备容量组合场景")
    add_group(parts, "5.1 电解槽容量 EL0-EL4", "outputs/results/electrolyzer_capacity_sensitivity/scenario_summary.csv", "完整 S5 系统 + 电解槽功率倍率扰动。", "重点观察制氢能力、外部补氢和成本。", "电解槽功率倍率为 0.5、1.0、1.5、2.0、3.0。", COMMON_COLUMNS + [("h2_production_kg", "制氢量/kg"), ("h2_external_supply_kg", "外部补氢/kg"), ("h2_storage_max_kg", "最大储氢/kg")], ["0.5 倍电解槽容量不足，会出现外部补氢。", "电解槽达到 1.0 倍后基本满足当前氢负荷，继续增容边际收益有限。"])
    add_group(parts, "5.2 储氢罐容量 HS0-HS4", "outputs/results/h2_storage_capacity_sensitivity/scenario_summary.csv", "完整 S5 系统 + 储氢罐容量倍率扰动。", "重点观察储氢库存、制氢和弃电。", "储氢罐容量倍率为 0.5、1.0、1.5、2.0、3.0。", COMMON_COLUMNS + [("h2_production_kg", "制氢量/kg"), ("h2_storage_max_kg", "最大储氢/kg")], ["储氢罐容量从 0.5 倍到 3.0 倍时，结果几乎不变。", "当前场景下储氢罐容量不是主要瓶颈。"])
    add_group(parts, "5.3 燃料电池容量 FC0-FC4", "outputs/results/fuel_cell_capacity_sensitivity/scenario_summary.csv", "完整 S5 系统 + 燃料电池容量倍率扰动。", "重点观察燃料电池是否运行及其经济性。", "燃料电池容量倍率为 0、0.5、1.0、1.5、2.0。", COMMON_COLUMNS + [("fuel_cell_generation_kwh", "燃料电池发电/kWh"), ("h2_fuel_cell_kg", "燃料电池耗氢/kg")], ["燃料电池容量从 0 到 2 倍时，燃料电池发电量仍为 0。", "当前电价、氢气效率、运维成本和碳价条件下，燃料电池发电不具经济性。"])

    add_heading(parts, 2, "六、v1.4 政策约束和市场收益场景")
    add_group(parts, "6.1 售氢收益 HSAL0-HSAL4", "outputs/results/h2_sale_price_sensitivity/scenario_summary.csv", "完整 S5 系统 + 售氢变量与售氢收益目标项。", "重点观察售氢价格对电解槽运行、制氢量和碳排放的影响。", "售氢价格为 0、10、20、30、40 元/kg。", COMMON_COLUMNS + [("h2_production_kg", "制氢量/kg"), ("h2_sale_kg", "售氢量/kg"), ("h2_sale_revenue_cny", "售氢收益/元")], ["售氢收益能够激励电解槽增加制氢。", "高售氢价格可能带来额外购电和碳排放，需要与碳约束联合评价。"])
    add_group(parts, "6.2 碳排放上限 CAP0-CAP4", "outputs/results/carbon_cap_sensitivity/scenario_summary.csv", "完整 S5 系统 + 日总碳排放上限约束。", "重点观察碳约束收紧对成本、购电和制氢的影响。", "碳排放上限分别为 S5 基准排放的 100%、90%、80%、70%、60%。", COMMON_COLUMNS + [("carbon_emission_cap_kg", "碳上限/kgCO2"), ("carbon_cap_excess_kg", "碳超额/kgCO2"), ("gas_consumption_m3", "天然气/m3"), ("h2_production_kg", "制氢量/kg")], ["碳约束越严格，系统成本越高。", "当前 CAP0-CAP4 均未出现碳超额，说明模型能通过调度满足这些约束。"])
    add_group(parts, "6.3 新能源消纳率约束 RC0-RC3", "outputs/results/renewable_consumption_constraint_sensitivity/scenario_summary.csv", "完整 S5 系统 + 最低新能源消纳率约束。", "重点观察强制消纳率对电池、制氢和成本的影响。", "最低新能源消纳率为 90%、95%、98%、99%。", COMMON_COLUMNS + [("renewable_consumption_rate", "实际消纳率"), ("renewable_min_consumption_rate", "最低消纳率"), ("battery_charge_kwh", "电池充电/kWh"), ("h2_production_kg", "制氢量/kg")], ["当前 S5 基准已实现 100% 新能源消纳，因此该约束不改变调度。", "后续可在高新能源装机或低储能能力场景中继续使用该约束。"])

    add_heading(parts, 2, "七、综合结论")
    add_list(
        parts,
        [
            "基础模型已经完整覆盖电、热、氢、储、碳排放和主要经济成本，S0-S5 验证了系统从传统供能到完整低碳调度的逐步效果。",
            "新能源、电池、热泵是当前 24 小时典型日中降低成本和碳排放的关键因素。",
            "氢能系统的主要价值在于吸纳电能并满足氢负荷；当氢负荷过高或电解槽容量不足时，外部补氢量会暴露供氢缺口。",
            "燃料电池在当前参数下始终不运行，说明其经济性不足；后续若要体现燃料电池价值，需要进一步设置更高峰电价、更高碳价、更低制氢成本或备用约束。",
            "售氢收益在高售氢价格下能够改变制氢行为，但会带来额外购电和碳排放，需要与碳约束联合评价。",
            "碳排放上限能够显著改变调度并推高成本，是后续政策约束分析的核心场景。",
            "当前 S5 已经实现 100% 新能源消纳，因此新能源最低消纳率约束在现有数据下不产生额外约束作用；后续可在高新能源装机或低储能能力场景中继续使用该约束。",
        ],
    )

    parts.append("</body></html>")
    return "\n".join(parts)


def main() -> None:
    OUTPUT_FILE.write_text(build_document(), encoding="utf-8-sig")
    print(OUTPUT_FILE)
    print(OUTPUT_FILE.stat().st_size)


if __name__ == "__main__":
    main()
