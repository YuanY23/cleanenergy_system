"""结果图表绘制模块。"""

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_input_curves(timeseries: pd.DataFrame, output_path: str | Path) -> Path:
    """绘制 24 小时输入曲线预览图。"""

    figure_path = Path(output_path)
    figure_path.parent.mkdir(parents=True, exist_ok=True)

    # 尽量使用系统常见中文字体；如果缺失，matplotlib 会自动回退。
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    hours = timeseries["hour"]

    # 第一张图展示风电和光伏可发功率。
    axes[0].plot(hours, timeseries["pv_available_kw"], label="光伏可发功率", marker="o")
    axes[0].plot(hours, timeseries["wind_available_kw"], label="风电可发功率", marker="o")
    axes[0].set_ylabel("功率/kW")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # 第二张图展示电负荷和热负荷。
    axes[1].plot(hours, timeseries["electric_load_kw"], label="电负荷", marker="o")
    axes[1].plot(hours, timeseries["heat_load_kw"], label="热负荷", marker="o")
    axes[1].set_ylabel("负荷/kW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    # 第三张图展示氢负荷和分时电价。
    axes[2].bar(hours, timeseries["hydrogen_load_kg"], label="氢负荷", alpha=0.65)
    price_axis = axes[2].twinx()
    price_axis.plot(
        hours,
        timeseries["electricity_price_cny_per_kwh"],
        label="分时电价",
        color="tab:red",
        marker="o",
    )
    axes[2].set_ylabel("氢负荷/kg")
    price_axis.set_ylabel("电价/(元/kWh)")
    axes[2].set_xlabel("小时")
    axes[2].grid(True, alpha=0.3)

    lines, labels = axes[2].get_legend_handles_labels()
    price_lines, price_labels = price_axis.get_legend_handles_labels()
    axes[2].legend(lines + price_lines, labels + price_labels)

    fig.suptitle("24小时典型输入数据预览")
    fig.tight_layout()
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)

    return figure_path


def plot_device_outputs(hourly_results: pd.DataFrame, output_path: str | Path) -> Path:
    """绘制完整场景下的关键设备出力曲线。"""

    figure_path = Path(output_path)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()

    scenario_data = _select_representative_scenario(hourly_results)
    hours = scenario_data["hour"]

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

    axes[0].plot(hours, scenario_data["grid_buy_kw"], label="电网购电", marker="o")
    axes[0].plot(hours, scenario_data["pv_used_kw"], label="光伏利用", marker="o")
    axes[0].plot(hours, scenario_data["wind_used_kw"], label="风电利用", marker="o")
    axes[0].plot(hours, scenario_data["fuel_cell_power_kw"], label="燃料电池发电", marker="o")
    axes[0].set_ylabel("电功率/kW")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(hours, scenario_data["heat_pump_heat_kw"], label="热泵供热", marker="o")
    axes[1].plot(hours, scenario_data["gas_boiler_heat_kw"], label="燃气锅炉供热", marker="o")
    axes[1].set_ylabel("热功率/kW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(hours, scenario_data["electrolyzer_power_kw"], label="电解槽耗电", marker="o")
    axes[2].plot(hours, scenario_data["battery_charge_kw"], label="电池充电", marker="o")
    axes[2].plot(hours, scenario_data["battery_discharge_kw"], label="电池放电", marker="o")
    axes[2].set_ylabel("功率/kW")
    axes[2].set_xlabel("小时")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    fig.suptitle(f"{scenario_data['scenario_id'].iloc[0]} 关键设备出力曲线")
    fig.tight_layout()
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)
    return figure_path


def plot_battery_soc(hourly_results: pd.DataFrame, output_path: str | Path) -> Path:
    """绘制电池 SOC 曲线。"""

    figure_path = Path(output_path)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()

    fig, ax = plt.subplots(figsize=(11, 4.8))
    for scenario_id, scenario_data in hourly_results.groupby("scenario_id"):
        if scenario_data["battery_soc_kwh"].max() > 0:
            ax.plot(
                scenario_data["hour"],
                scenario_data["battery_soc_kwh"],
                label=scenario_id,
                marker="o",
            )

    ax.set_title("电池 SOC 曲线")
    ax.set_xlabel("小时")
    ax.set_ylabel("SOC/kWh")
    ax.grid(True, alpha=0.3)
    if ax.get_legend_handles_labels()[0]:
        ax.legend()
    fig.tight_layout()
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)
    return figure_path


def plot_h2_storage(hourly_results: pd.DataFrame, output_path: str | Path) -> Path:
    """绘制储氢量曲线。"""

    figure_path = Path(output_path)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()

    fig, ax = plt.subplots(figsize=(11, 4.8))
    for scenario_id, scenario_data in hourly_results.groupby("scenario_id"):
        if scenario_data["h2_storage_kg"].max() > 0:
            ax.plot(
                scenario_data["hour"],
                scenario_data["h2_storage_kg"],
                label=scenario_id,
                marker="o",
            )

    ax.set_title("储氢罐储氢量曲线")
    ax.set_xlabel("小时")
    ax.set_ylabel("储氢量/kg")
    ax.grid(True, alpha=0.3)
    if ax.get_legend_handles_labels()[0]:
        ax.legend()
    fig.tight_layout()
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)
    return figure_path


def plot_scenario_comparisons(
    summary: pd.DataFrame, output_dir: str | Path
) -> dict[str, Path]:
    """绘制成本、碳排放和新能源消纳率场景对比图。"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()

    summary = summary.copy()
    renewable_total = summary["renewable_used_kwh"] + summary["renewable_curtailment_kwh"]
    summary["renewable_consumption_rate"] = summary["renewable_used_kwh"] / renewable_total.replace(0, pd.NA)
    summary["renewable_consumption_rate"] = summary["renewable_consumption_rate"].fillna(0)

    paths = {
        "scenario_cost_png": output_path / "scenario_cost_comparison.png",
        "scenario_carbon_png": output_path / "scenario_carbon_comparison.png",
        "scenario_renewable_png": output_path / "scenario_renewable_consumption.png",
    }

    _bar_plot(
        summary,
        "total_cost_cny",
        "不同场景系统总成本对比",
        "成本/元",
        paths["scenario_cost_png"],
    )
    _bar_plot(
        summary,
        "carbon_emission_kg",
        "不同场景碳排放量对比",
        "碳排放/kgCO2",
        paths["scenario_carbon_png"],
    )
    _bar_plot(
        summary,
        "renewable_consumption_rate",
        "不同场景新能源消纳率对比",
        "消纳率",
        paths["scenario_renewable_png"],
    )

    return paths


def plot_annual_cost_breakdown(
    annual_summary: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """绘制年度成本构成图。"""

    figure_path = Path(output_path)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()

    row = annual_summary.iloc[0]
    cost_items = {
        "购电成本": float(row.get("annual_grid_cost_cny", 0.0)),
        "天然气成本": float(row.get("annual_gas_cost_cny", 0.0)),
        "碳成本": float(row.get("annual_carbon_cost_cny", 0.0)),
    }

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(cost_items.keys(), cost_items.values())
    ax.set_title("年度运行成本构成")
    ax.set_ylabel("成本/元")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)
    return figure_path


def plot_annual_carbon_by_typical_day(
    contribution: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """绘制不同典型日对年度碳排放的贡献。"""

    figure_path = Path(output_path)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(
        contribution["typical_day_id"],
        contribution["weighted_carbon_emission_kg"],
    )
    ax.set_title("典型日年度碳排放贡献")
    ax.set_xlabel("典型日")
    ax.set_ylabel("碳排放/kgCO2")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)
    return figure_path


def plot_annual_energy_by_typical_day(
    contribution: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """绘制典型日年度能源量贡献图。"""

    figure_path = Path(output_path)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()

    x_labels = contribution["typical_day_id"]
    x_positions = range(len(contribution))
    width = 0.25

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(
        [x - width for x in x_positions],
        contribution["weighted_grid_purchase_kwh"],
        width=width,
        label="购电量",
    )
    ax.bar(
        list(x_positions),
        contribution["weighted_heat_pump_heat_kwh"],
        width=width,
        label="热泵供热",
    )
    ax.bar(
        [x + width for x in x_positions],
        contribution["weighted_h2_production_kg"],
        width=width,
        label="制氢量",
    )
    ax.set_title("典型日年度能源量贡献")
    ax.set_xlabel("典型日")
    ax.set_ylabel("能源量")
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(x_labels)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=150)
    plt.close(fig)
    return figure_path


def _configure_chinese_font() -> None:
    """设置 matplotlib 中文字体。"""

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False


def _select_representative_scenario(hourly_results: pd.DataFrame) -> pd.DataFrame:
    """优先选择 S5，其次选择最后一个场景作为设备出力图代表。"""

    if "S5" in set(hourly_results["scenario_id"]):
        return hourly_results[hourly_results["scenario_id"] == "S5"]
    last_scenario = hourly_results["scenario_id"].iloc[-1]
    return hourly_results[hourly_results["scenario_id"] == last_scenario]


def _bar_plot(
    summary: pd.DataFrame,
    value_column: str,
    title: str,
    ylabel: str,
    output_path: Path,
) -> None:
    """通用场景柱状图。"""

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(summary["scenario_id"], summary[value_column])
    ax.set_title(title)
    ax.set_xlabel("场景")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
