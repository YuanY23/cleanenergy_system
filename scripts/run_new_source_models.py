from __future__ import annotations

import json
import shutil
import sys
import traceback
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from zero_carbon_park.cli import run_full_pipeline
from zero_carbon_park.planning.cost_params import PlanningCostParams
from zero_carbon_park.planning.pareto import run_cost_carbon_pareto_analysis
from zero_carbon_park.planning.runner import run_capacity_planning
from zero_carbon_park.planning.sensitivity import run_investment_sensitivity_analysis
from zero_carbon_park.scenarios.sensitivity import (
    run_v1_1_sensitivity_analysis,
    run_v1_2_sensitivity_analysis,
    run_v1_3_sensitivity_analysis,
    run_v1_4_sensitivity_analysis,
)
from zero_carbon_park.typical_days.annualization import run_annualized_typical_days
from zero_carbon_park.typical_days.runner import run_typical_day_scenarios
from zero_carbon_park.uncertainty.robust_planning import run_robust_capacity_planning
from zero_carbon_park.uncertainty.stochastic_planning import (
    run_stochastic_capacity_planning,
)
from zero_carbon_park.uncertainty.stress_test import run_uncertainty_stress_test


SOURCE_WORKBOOK = ROOT / "codex数据汇总表.xlsx"
OUTPUT_ROOT = ROOT / "new_source_results"
INPUT_DIR = OUTPUT_ROOT / "00_inputs"
MODEL_WORKBOOK = INPUT_DIR / "codex_model_input_workbook.xlsx"
STOCHASTIC_KEY_CASE_IDS = ["NORMAL", "LOAD_HIGH", "EXTREME"]
ROBUST_WORST_CASE_IDS = ["EXTREME"]


def _read_new_workbook() -> dict[str, pd.DataFrame]:
    return pd.read_excel(
        SOURCE_WORKBOOK,
        sheet_name=[
            "Sources_来源索引",
            "Parameters_推荐参数",
            "TypicalDays_72h",
            "TimeSeries_2024_hourly",
            "Assumptions_推导公式",
        ],
    )


def _source_url_map(sources: pd.DataFrame) -> dict[str, str]:
    return {
        str(row.source_id): str(row.url)
        for row in sources.itertuples(index=False)
        if pd.notna(row.source_id) and pd.notna(row.url)
    }


def _parameter_map(params: pd.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in params.itertuples(index=False):
        field = str(getattr(row, "字段名"))
        value = getattr(row, "推荐值")
        if pd.notna(value):
            try:
                out[field] = float(value)
            except (TypeError, ValueError):
                continue
    return out


def _source_for(params: pd.DataFrame, field: str, url_map: dict[str, str]) -> str:
    matches = params[params["字段名"] == field]
    if matches.empty:
        return ""
    ids = str(matches.iloc[0]["来源ID"]).split(";")
    urls = [url_map.get(source_id.strip(), "") for source_id in ids]
    return "; ".join(url for url in urls if url)


def _heat_pump_cop_from_temperature(temperature_c: float, fallback: float) -> float:
    if temperature_c <= -15:
        return max(2.1, fallback - 1.1)
    if temperature_c <= -5:
        return 2.3 + (temperature_c + 15) * 0.05
    if temperature_c <= 5:
        return 2.8 + (temperature_c + 5) * 0.06
    if temperature_c <= 15:
        return 3.4 + (temperature_c - 5) * 0.05
    return min(4.2, fallback + 0.7)


def _heat_pump_available_ratio_from_temperature(temperature_c: float) -> float:
    if temperature_c <= -20:
        return 0.65
    if temperature_c <= -15:
        return 0.75
    if temperature_c <= -10:
        return 0.85
    return 1.0


def _make_timeseries(typical: pd.DataFrame, pmap: dict[str, float]) -> pd.DataFrame:
    winter = typical[typical["typical_day_type"] == "典型冬季日"].copy()
    if winter.empty:
        winter = typical.head(24).copy()
    winter = winter.head(24).reset_index(drop=True)
    if len(winter) != 24:
        raise ValueError("新数据表中无法取得 24 小时典型日数据")

    wind_capacity_kw = 120_000.0
    pv_capacity_kw = 100_000.0
    if "temperature_c" in winter.columns:
        temperature_c = winter["temperature_c"].astype(float)
    else:
        temperature_c = pd.Series([0.0] * len(winter))
    heat_pump_cop = temperature_c.map(
        lambda value: _heat_pump_cop_from_temperature(
            float(value), pmap.get("heat_pump_cop", 3.5)
        )
    )
    heat_pump_available_ratio = temperature_c.map(
        lambda value: _heat_pump_available_ratio_from_temperature(float(value))
    )

    return pd.DataFrame(
        {
            "hour": range(24),
            "pv_cf": winter["pv_cf"].astype(float),
            "wind_cf": winter["wind_cf"].astype(float),
            "pv_available_kW": winter["pv_cf"].astype(float) * pv_capacity_kw,
            "wind_available_kW": winter["wind_cf"].astype(float) * wind_capacity_kw,
            "electric_load_kW": winter["electric_load_kw"].astype(float),
            "heat_load_kW": winter["heat_load_kw"].astype(float),
            "h2_load_kg": winter["hydrogen_load_kg"].astype(float),
            "tou_period": winter["tou_period"],
            "electricity_price_yuan_per_kWh": winter[
                "electricity_price_cny_per_kwh"
            ].astype(float),
            "gas_price_yuan_per_m3": winter["gas_price_cny_per_m3"].astype(float),
            "grid_emission_kgCO2_per_kWh": winter[
                "grid_emission_kgco2_per_kwh"
            ].astype(float),
            "carbon_price_yuan_per_tCO2": winter[
                "carbon_price_cny_per_tco2"
            ].astype(float),
            "heat_pump_cop": heat_pump_cop,
            "heat_pump_available_ratio": heat_pump_available_ratio,
            "说明": "来自 codex数据汇总表.xlsx 的典型冬季日；负荷为公开案例校准重构，风光为 NASA POWER 推导",
        }
    )


def _param_row(
    category: str,
    name: str,
    field: str,
    unit: str,
    value: float,
    source_url: str,
    note: str,
    source_attr: str = "codex新数据表",
    sensitivity_range: str = "",
) -> dict[str, Any]:
    return {
        "类别": category,
        "参数": name,
        "符号/字段": field,
        "单位": unit,
        "基准值": value,
        "敏感性范围": sensitivity_range,
        "来源属性": source_attr,
        "来源URL": source_url,
        "用途/备注": note,
    }


def _make_parameters(params: pd.DataFrame, sources: pd.DataFrame) -> pd.DataFrame:
    url_map = _source_url_map(sources)
    p = _parameter_map(params)
    src = lambda field: _source_for(params, field, url_map)

    rows = [
        _param_row("规模", "风电装机", "wind_capacity_kW", "kW", 120_000, src("wind_cf"), "按新数据源风资源和园区尺度设定"),
        _param_row("规模", "光伏装机", "pv_capacity_kW", "kW", 100_000, src("pv_cf"), "按新数据源光伏资源和园区尺度设定"),
        _param_row("电储能", "额定功率", "battery_power_kW", "kW", 50_000, src("battery_power_capex_cny_per_kw"), "园区级储能功率假设"),
        _param_row("电储能", "额定容量", "battery_energy_kWh", "kWh", 200_000, src("battery_energy_capex_cny_per_kwh"), "4h 储能时长假设"),
        _param_row("电储能", "充电效率", "battery_eta_ch", "-", p["battery_charge_efficiency"], src("battery_charge_efficiency"), "新参数表推荐值"),
        _param_row("电储能", "放电效率", "battery_eta_dis", "-", p["battery_discharge_efficiency"], src("battery_discharge_efficiency"), "新参数表推荐值"),
        _param_row("电储能", "初始SOC", "battery_initial_soc", "kWh", 100_000, src("battery_energy_capex_cny_per_kwh"), "按 50% SOC 初始化"),
        _param_row("氢能", "电解槽额定功率", "electrolyzer_power_kW", "kW", 60_000, src("electrolyzer_capex_cny_per_kw"), "按约 1000 kg/h 供氢能力设定"),
        _param_row("氢能", "电解槽耗电量", "electrolyzer_kWh_per_kgH2", "kWh/kgH2", p["electrolyzer_kwh_per_kg"], src("electrolyzer_kwh_per_kg"), "新参数表推荐值"),
        _param_row("氢能", "电解槽最小负荷率", "electrolyzer_min_load_rate", "-", 0.15, src("electrolyzer_kwh_per_kg"), "P1 运行约束：低于最小负荷视为停机"),
        _param_row("氢能", "电解槽分段1下限", "electrolyzer_segment_1_min_rate", "-", 0.15, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段1上限", "electrolyzer_segment_1_max_rate", "-", 0.30, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段1耗电", "electrolyzer_segment_1_kwh_per_kg", "kWh/kgH2", 60.0, src("electrolyzer_kwh_per_kg"), "低负荷效率较低"),
        _param_row("氢能", "电解槽分段2下限", "electrolyzer_segment_2_min_rate", "-", 0.30, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段2上限", "electrolyzer_segment_2_max_rate", "-", 0.60, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段2耗电", "electrolyzer_segment_2_kwh_per_kg", "kWh/kgH2", 55.0, src("electrolyzer_kwh_per_kg"), "中低负荷接近额定推荐值"),
        _param_row("氢能", "电解槽分段3下限", "electrolyzer_segment_3_min_rate", "-", 0.60, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段3上限", "electrolyzer_segment_3_max_rate", "-", 0.90, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段3耗电", "electrolyzer_segment_3_kwh_per_kg", "kWh/kgH2", 51.0, src("electrolyzer_kwh_per_kg"), "高效运行区"),
        _param_row("氢能", "电解槽分段4下限", "electrolyzer_segment_4_min_rate", "-", 0.90, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段4上限", "electrolyzer_segment_4_max_rate", "-", 1.00, src("electrolyzer_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "电解槽分段4耗电", "electrolyzer_segment_4_kwh_per_kg", "kWh/kgH2", 54.0, src("electrolyzer_kwh_per_kg"), "接近满负荷效率回落"),
        _param_row("氢能", "储氢容量", "h2_storage_capacity_kg", "kg", 10_000, src("hydrogen_storage_capex_cny_per_kg"), "园区级日内储氢假设"),
        _param_row("氢能", "初始储氢量", "h2_storage_initial_kg", "kg", 5_000, src("hydrogen_storage_capex_cny_per_kg"), "按 50% 储量初始化"),
        _param_row("氢能", "储氢逐时损耗率", "h2_storage_loss_rate_per_hour", "-", p.get("hydrogen_storage_loss_per_day", 0.001) / 24.0, src("hydrogen_storage_loss_per_day"), "P1 储氢罐日损耗折算为逐时损耗"),
        _param_row("氢能", "燃料电池额定功率", "fuel_cell_power_kW", "kW", 10_000, src("fuel_cell_capex_cny_per_kw"), "备用与调峰能力假设"),
        _param_row("氢能", "燃料电池电效率", "fuel_cell_kWh_per_kgH2", "kWh/kgH2", p["fuel_cell_kwh_per_kg"], src("fuel_cell_kwh_per_kg"), "新参数表推荐值"),
        _param_row("氢能", "燃料电池最小负荷率", "fuel_cell_min_load_rate", "-", 0.10, src("fuel_cell_kwh_per_kg"), "P1 运行约束：低于最小负荷视为停机"),
        _param_row("氢能", "燃料电池分段1下限", "fuel_cell_segment_1_min_rate", "-", 0.10, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段1上限", "fuel_cell_segment_1_max_rate", "-", 0.30, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段1发电量", "fuel_cell_segment_1_kwh_per_kg", "kWh/kgH2", 16.0, src("fuel_cell_kwh_per_kg"), "低负荷效率较低"),
        _param_row("氢能", "燃料电池分段2下限", "fuel_cell_segment_2_min_rate", "-", 0.30, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段2上限", "fuel_cell_segment_2_max_rate", "-", 0.60, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段2发电量", "fuel_cell_segment_2_kwh_per_kg", "kWh/kgH2", 18.5, src("fuel_cell_kwh_per_kg"), "额定附近推荐值"),
        _param_row("氢能", "燃料电池分段3下限", "fuel_cell_segment_3_min_rate", "-", 0.60, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段3上限", "fuel_cell_segment_3_max_rate", "-", 0.90, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段3发电量", "fuel_cell_segment_3_kwh_per_kg", "kWh/kgH2", 19.5, src("fuel_cell_kwh_per_kg"), "高效运行区"),
        _param_row("氢能", "燃料电池分段4下限", "fuel_cell_segment_4_min_rate", "-", 0.90, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段4上限", "fuel_cell_segment_4_max_rate", "-", 1.00, src("fuel_cell_kwh_per_kg"), "P0 分段性能曲线"),
        _param_row("氢能", "燃料电池分段4发电量", "fuel_cell_segment_4_kwh_per_kg", "kWh/kgH2", 18.5, src("fuel_cell_kwh_per_kg"), "满负荷效率回落"),
        _param_row("热力", "热泵额定电功率", "heat_pump_power_kW", "kW", 50_000, src("heat_pump_capex_cny_per_kwth"), "按 COP 供热能力匹配园区热负荷"),
        _param_row("热力", "热泵COP", "heat_pump_COP", "-", p["heat_pump_cop"], src("heat_pump_cop"), "新参数表推荐值"),
        _param_row("热力", "燃气锅炉最大供热", "gas_boiler_heat_kW", "kWth", 130_000, src("gas_boiler_efficiency"), "覆盖新典型日峰值热负荷"),
        _param_row("热力", "燃气锅炉效率", "gas_boiler_eff", "-", p["gas_boiler_efficiency"], src("gas_boiler_efficiency"), "新参数表推荐值"),
        _param_row("热力", "天然气低位热值", "gas_lhv_kwh_per_m3", "kWh/m3", p["gas_lhv_kwh_per_m3"], src("gas_lhv_kwh_per_m3"), "新参数表推荐值"),
        _param_row("能源价格", "平段电价", "flat_electricity_price", "元/kWh", 0.45, src("electricity_price_cny_per_kwh"), "分时电价的平段建模基准"),
        _param_row("能源价格", "天然气价格", "gas_price", "元/m3", p["gas_price_cny_per_m3"], src("gas_price_cny_per_m3"), "鄂尔多斯非居民管道气价"),
        _param_row("能源价格", "售氢价格", "h2_sale_price", "元/kg", p["h2_sale_price_cny_per_kg"], src("h2_sale_price_cny_per_kg"), "中国氢能报告消费侧价格参考"),
        _param_row("能源价格", "外购氢价格", "h2_external_supply_cost", "元/kg", p["external_h2_purchase_cny_per_kg"], src("external_h2_purchase_cny_per_kg"), "供氢不足兜底成本"),
        _param_row("能源价格", "售氢启用", "h2_sale_enabled", "-", 0.0, src("h2_sale_price_cny_per_kg"), "默认关闭，v1.4 售氢场景会打开"),
        _param_row("能源价格", "余电上网价格", "grid_sell_price_cny_per_kwh", "元/kWh", p["grid_sell_price_cny_per_kwh"], src("grid_sell_price_cny_per_kwh"), "用于容量规划余电出售收益"),
        _param_row("碳价", "碳价", "carbon_price", "元/tCO2", p["carbon_price_cny_per_tco2"], src("carbon_price_cny_per_tco2"), "全国碳市场均价"),
        _param_row("碳排放", "购电排放因子", "grid_emission_factor", "kgCO2/kWh", p["grid_emission_kgco2_per_kwh"], src("grid_emission_kgco2_per_kwh"), "内蒙古省级电力排放因子"),
        _param_row("碳排放", "天然气排放因子", "gas_emission_factor", "kgCO2/m3", p["gas_emission_kgco2_per_m3"], src("gas_emission_kgco2_per_m3"), "按国家核算指南推导"),
        _param_row("碳排放", "碳排放上限", "carbon_emission_cap_kg", "kgCO2", p["annual_carbon_cap_kgco2"] / 365, src("annual_carbon_cap_kgco2"), "日调度模型使用日上限"),
        _param_row("碳排放", "碳超额惩罚", "carbon_cap_excess_penalty", "元/kgCO2", 0.0, src("annual_carbon_cap_kgco2"), "本轮关闭超额惩罚，仅记录超额量"),
        _param_row("惩罚成本", "弃风弃光惩罚", "curtail_penalty", "元/kWh", 0.10, "", "机会成本场景假设"),
        _param_row("运维成本", "电池运维", "battery_om", "元/kWh throughput", 0.0, src("battery_degradation_cny_per_kwh_throughput"), "退化成本已拆入分段退化曲线，避免重复计入"),
        _param_row("运维成本", "电池退化分段1宽度", "battery_degradation_segment_1_width_rate", "-", 0.20, src("battery_degradation_cny_per_kwh_throughput"), "P0 分段退化成本：浅循环低成本区"),
        _param_row("运维成本", "电池退化分段1成本", "battery_degradation_segment_1_cost_cny_per_kwh", "元/kWh throughput", 0.05, src("battery_degradation_cny_per_kwh_throughput"), "浅循环退化折算成本"),
        _param_row("运维成本", "电池退化分段2宽度", "battery_degradation_segment_2_width_rate", "-", 0.30, src("battery_degradation_cny_per_kwh_throughput"), "P0 分段退化成本：常规循环区"),
        _param_row("运维成本", "电池退化分段2成本", "battery_degradation_segment_2_cost_cny_per_kwh", "元/kWh throughput", 0.10, src("battery_degradation_cny_per_kwh_throughput"), "常规循环退化折算成本"),
        _param_row("运维成本", "电池退化分段3宽度", "battery_degradation_segment_3_width_rate", "-", 0.50, src("battery_degradation_cny_per_kwh_throughput"), "P0 分段退化成本：深循环高成本区"),
        _param_row("运维成本", "电池退化分段3成本", "battery_degradation_segment_3_cost_cny_per_kwh", "元/kWh throughput", 0.18, src("battery_degradation_cny_per_kwh_throughput"), "深循环退化折算成本"),
        _param_row("运维成本", "电解槽运维", "electrolyzer_om", "元/kgH2", p["electrolyzer_var_om_cny_per_kg"], src("electrolyzer_var_om_cny_per_kg"), "新参数表推荐值"),
        _param_row("运维成本", "燃料电池运维", "fuel_cell_om", "元/kWh", p["fuel_cell_var_om_cny_per_kwh"], src("fuel_cell_var_om_cny_per_kwh"), "新参数表推荐值"),
        _param_row("惩罚成本", "新能源最低消纳率", "renewable_min_consumption_rate", "-", p["min_renewable_utilization"], src("min_renewable_utilization"), "政策约束场景使用"),
        _param_row("政策约束", "容量规划最低绿电比例", "green_power_min_share", "-", 0.50, "https://www.nea.gov.cn/20250318/0c73110958864a75bd1a823c7861c40c/c.html; https://www.ndrc.gov.cn/xxgk/zcfb/tz/202507/t20250708_1399055.html", "按零碳园区高比例绿电消费和绿电直供政策口径，本轮采用 50% 作为容量规划硬约束"),
    ]
    return pd.DataFrame(rows)


def _make_scenarios() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["S0", "传统供能", "外部电网 + 燃气锅炉", "wind=pv=battery=electrolyzer=storage=fuelcell=0", "总成本、购电量、气耗、碳排放", "基准场景"],
            ["S1", "加入风光", "电网 + 燃气锅炉 + 风电 + 光伏", "use_renewables=True", "新能源消纳、弃风弃光、购电减少", "评估风光直接替代"],
            ["S2", "风光 + 电池", "S1 + 电池储能", "use_battery=True", "储能充放电、峰谷套利、弃电变化", "评估电储能价值"],
            ["S3", "风光储 + 制氢储氢", "S2 + 电解槽 + 储氢 + 氢负荷", "use_hydrogen=True", "制氢量、储氢、外购氢", "评估氢能消纳"],
            ["S4", "电热氢储完整系统", "S3 + 热泵 + 燃料电池", "use_heat_pump=True; use_fuel_cell=True", "电热氢耦合、备用发电", "完整系统调度"],
            ["S5", "完整系统 + 碳价", "S4 + 碳成本", "use_carbon_price=True", "碳排放、碳成本、低碳调度", "低碳经济性对比"],
        ],
        columns=["场景编号", "场景名称", "启用技术/机制", "关键设置", "主要观察指标", "作用"],
    )


def _build_compatible_workbook() -> tuple[Path, PlanningCostParams]:
    data = _read_new_workbook()
    sources = data["Sources_来源索引"]
    params = data["Parameters_推荐参数"]
    p = _parameter_map(params)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SOURCE_WORKBOOK, INPUT_DIR / SOURCE_WORKBOOK.name)

    timeseries = _make_timeseries(data["TypicalDays_72h"], p)
    parameter_table = _make_parameters(params, sources)
    source_table = sources.rename(
        columns={
            "source_id": "编号",
            "来源名称": "来源名称",
            "url": "URL",
            "可用数据/用途": "用于哪些数据",
        }
    )
    if "编号" not in source_table.columns:
        source_table.insert(0, "编号", sources["source_id"])
    if "URL" not in source_table.columns:
        source_table["URL"] = sources["url"]
    if "用于哪些数据" not in source_table.columns:
        source_table["用于哪些数据"] = sources["可用数据/用途"]
    source_table = source_table[["编号", "来源名称", "URL", "用于哪些数据"]]

    with pd.ExcelWriter(MODEL_WORKBOOK, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                ["说明", "由 codex数据汇总表.xlsx 自动转换，供现有模型 loader 读取"],
                ["源文件", str(SOURCE_WORKBOOK)],
                ["输出目录", str(OUTPUT_ROOT)],
            ],
            columns=["项目", "内容"],
        ).to_excel(writer, sheet_name="00_说明", index=False)
        sources.to_excel(writer, sheet_name="01_数据来源总表", index=False)
        pd.DataFrame(
            [
                ["背景", "鄂尔多斯零碳产业园公开案例"],
                ["数据", "NASA POWER + 政府/报告/论文参数 + 公开案例校准重构"],
            ],
            columns=["项目", "公开信息/采用方式"],
        ).to_excel(writer, sheet_name="02_园区背景", index=False)
        timeseries.to_excel(writer, sheet_name="03_24h输入数据", index=False)
        parameter_table.to_excel(writer, sheet_name="04_设备技术经济参数", index=False)
        _make_scenarios().to_excel(writer, sheet_name="05_场景设置", index=False)
        source_table.to_excel(writer, sheet_name="06_来源URL", index=False)
        data["Assumptions_推导公式"].to_excel(
            writer, sheet_name="07_Codex使用说明", index=False
        )

    cost_params = PlanningCostParams(
        discount_rate=p["discount_rate"],
        wind_capex_cny_per_kw=p["wind_capex_cny_per_kw"],
        wind_life_years=int(p["wind_lifetime_year"]),
        pv_capex_cny_per_kw=p["pv_capex_cny_per_kw"],
        pv_life_years=int(p["pv_lifetime_year"]),
        battery_power_capex_cny_per_kw=p["battery_power_capex_cny_per_kw"],
        battery_energy_capex_cny_per_kwh=p["battery_energy_capex_cny_per_kwh"],
        battery_life_years=int(p["battery_lifetime_year"]),
        electrolyzer_capex_cny_per_kw=p["electrolyzer_capex_cny_per_kw"],
        electrolyzer_life_years=int(p["electrolyzer_lifetime_year"]),
        h2_storage_capex_cny_per_kg=p["hydrogen_storage_capex_cny_per_kg"],
        h2_storage_life_years=int(p["hydrogen_storage_lifetime_year"]),
        fuel_cell_capex_cny_per_kw=p["fuel_cell_capex_cny_per_kw"],
        fuel_cell_life_years=int(p["fuel_cell_lifetime_year"]),
        heat_pump_capex_cny_per_kw=p["heat_pump_capex_cny_per_kwth"],
        heat_pump_life_years=15,
        battery_degradation_cost_cny_per_kwh=p[
            "battery_degradation_cny_per_kwh_throughput"
        ],
        fuel_cell_backup_value_cny_per_kw_year=p[
            "fuel_cell_backup_value_cny_per_kw_year"
        ],
        fuel_cell_backup_reserve_kw=10_000,
        fuel_cell_backup_required_kw=p["fuel_cell_backup_required_kw"]
        if "fuel_cell_backup_required_kw" in p
        else 0.0,
        grid_export_limit_kw=p["max_grid_export_kw"],
        demand_charge_cny_per_kw_year=p["demand_charge_cny_per_kw_year"],
    )
    return MODEL_WORKBOOK, cost_params


def _install_new_cost_params(cost_params: PlanningCostParams) -> None:
    def provider() -> PlanningCostParams:
        return replace(cost_params)

    import zero_carbon_park.planning.runner as planning_runner
    import zero_carbon_park.planning.sensitivity as planning_sensitivity
    import zero_carbon_park.planning.pareto as planning_pareto
    import zero_carbon_park.uncertainty.stress_test as stress_test
    import zero_carbon_park.uncertainty.stochastic_planning as stochastic_planning
    import zero_carbon_park.uncertainty.robust_planning as robust_planning

    planning_runner.get_default_planning_cost_params = provider
    planning_sensitivity.get_default_planning_cost_params = provider
    planning_pareto.get_default_planning_cost_params = provider
    stress_test.get_default_planning_cost_params = provider
    stochastic_planning.get_default_planning_cost_params = provider
    robust_planning.get_default_planning_cost_params = provider


def _install_park_scale_capacity_bounds() -> None:
    from pyomo.environ import NonNegativeReals, Var

    def add_park_scale_capacity_variables(model) -> None:
        model.wind_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 2_000_000))
        model.pv_capacity_kw = Var(domain=NonNegativeReals, bounds=(0, 2_000_000))
        model.battery_power_capacity_kw = Var(
            domain=NonNegativeReals, bounds=(0, 300_000)
        )
        model.battery_energy_capacity_kwh = Var(
            domain=NonNegativeReals, bounds=(0, 1_000_000)
        )
        model.electrolyzer_power_capacity_kw = Var(
            domain=NonNegativeReals, bounds=(0, 200_000)
        )
        model.h2_storage_capacity_kg = Var(
            domain=NonNegativeReals, bounds=(0, 100_000)
        )
        model.fuel_cell_power_capacity_kw = Var(
            domain=NonNegativeReals, bounds=(0, 100_000)
        )
        model.heat_pump_power_capacity_kw = Var(
            domain=NonNegativeReals, bounds=(0, 200_000)
        )

    import zero_carbon_park.planning.builder as planning_builder
    import zero_carbon_park.planning.variables as planning_variables

    planning_variables.add_capacity_variables = add_park_scale_capacity_variables
    planning_builder.add_capacity_variables = add_park_scale_capacity_variables


def _flatten_paths(value: Any) -> list[str]:
    if isinstance(value, Path):
        return [str(value)]
    if isinstance(value, dict):
        paths: list[str] = []
        for item in value.values():
            paths.extend(_flatten_paths(item))
        return paths
    if isinstance(value, (list, tuple)):
        paths: list[str] = []
        for item in value:
            paths.extend(_flatten_paths(item))
        return paths
    return []


def _run_step(
    name: str,
    func: Callable[..., Any],
    workbook: Path,
    output_dir: Path,
) -> dict[str, Any]:
    print(f"[RUN] {name}")
    try:
        result = func(workbook, output_dir)
        paths = _flatten_paths(result)
        print(f"[OK] {name}: {len(paths)} files")
        return {
            "name": name,
            "status": "ok",
            "output_dir": str(output_dir),
            "file_count": len(paths),
            "files": paths,
        }
    except Exception as exc:  # noqa: BLE001 - batch runner must continue.
        print(f"[FAIL] {name}: {exc}")
        return {
            "name": name,
            "status": "failed",
            "output_dir": str(output_dir),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _run_uncertainty_stress_test_without_green_hard_constraint(
    workbook: Path,
    output_dir: Path,
) -> dict[str, Path]:
    return run_uncertainty_stress_test(
        workbook,
        output_dir,
        enforce_green_power_share=False,
    )


def _run_key_case_stochastic_planning(
    workbook: Path,
    output_dir: Path,
) -> dict[str, Path]:
    return run_stochastic_capacity_planning(
        workbook,
        output_dir,
        uncertainty_case_ids=STOCHASTIC_KEY_CASE_IDS,
    )


def _run_worst_case_robust_planning(
    workbook: Path,
    output_dir: Path,
) -> dict[str, Path]:
    return run_robust_capacity_planning(
        workbook,
        output_dir,
        uncertainty_case_ids=ROBUST_WORST_CASE_IDS,
    )


def _reset_output_root() -> None:
    output_root = OUTPUT_ROOT.resolve()
    project_root = ROOT.resolve()
    if output_root == project_root or project_root not in output_root.parents:
        raise RuntimeError(f"Refuse to delete unsafe output path: {output_root}")
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    _reset_output_root()
    workbook, cost_params = _build_compatible_workbook()
    _install_new_cost_params(cost_params)
    _install_park_scale_capacity_bounds()

    manifest: list[dict[str, Any]] = []
    manifest.append(
        {
            "name": "input_conversion",
            "status": "ok",
            "output_dir": str(INPUT_DIR),
            "files": [str(workbook), str(INPUT_DIR / SOURCE_WORKBOOK.name)],
            "planning_cost_params": asdict(cost_params),
        }
    )

    steps: list[tuple[str, Callable[..., Any], Path]] = [
        ("01_full_pipeline", run_full_pipeline, OUTPUT_ROOT / "01_full_pipeline"),
        ("02_capacity_planning", run_capacity_planning, OUTPUT_ROOT / "02_capacity_planning"),
        ("03_pareto_cost_carbon", run_cost_carbon_pareto_analysis, OUTPUT_ROOT / "03_pareto_cost_carbon"),
        ("04_uncertainty_stress_test", _run_uncertainty_stress_test_without_green_hard_constraint, OUTPUT_ROOT / "04_uncertainty_stress_test"),
        ("05_stochastic_planning", _run_key_case_stochastic_planning, OUTPUT_ROOT / "05_stochastic_planning"),
        ("06_robust_planning", _run_worst_case_robust_planning, OUTPUT_ROOT / "06_robust_planning"),
    ]

    for name, func, output_dir in steps:
        manifest.append(_run_step(name, func, workbook, output_dir))

    manifest_path = OUTPUT_ROOT / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = pd.DataFrame(
        [
            {
                "name": row["name"],
                "status": row["status"],
                "output_dir": row.get("output_dir", ""),
                "file_count": row.get("file_count", len(row.get("files", []))),
                "error": row.get("error", ""),
            }
            for row in manifest
        ]
    )
    summary.to_csv(OUTPUT_ROOT / "run_summary.csv", index=False, encoding="utf-8-sig")
    summary.to_excel(OUTPUT_ROOT / "run_summary.xlsx", index=False)
    print(f"[DONE] manifest: {manifest_path}")


if __name__ == "__main__":
    main()
