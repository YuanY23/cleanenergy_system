"""结果图表绘制模块。"""

from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ENGINEERING_COLORS = {
    "economic": "#32628F",
    "low_carbon": "#2E8B57",
    "resilience": "#D17A22",
    "load": "#30343B",
    "pv": "#E5B73B",
    "wind": "#4B82C3",
    "grid": "#8C8C8C",
    "battery": "#7957A8",
    "hydrogen": "#18A6A6",
    "carbon_location": "#B34D4D",
    "carbon_method": "#4E8C60",
}


def plot_annual_duration_curves(
    annual_inputs: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot load and resource duration curves from the supplied hourly inputs."""

    _require_frame(
        annual_inputs,
        {"electric_load_kw", "pv_cf", "wind_cf_calibrated"},
        "annual_inputs",
    )
    figure_path = _prepare_engineering_figure(output_path)
    duration = 100 * (pd.Series(range(1, len(annual_inputs) + 1)) / len(annual_inputs))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))
    axes[0].plot(
        duration,
        annual_inputs["electric_load_kw"].sort_values(ascending=False).to_numpy(),
        color=ENGINEERING_COLORS["load"],
        linewidth=1.8,
    )
    axes[0].set(title="全年电负荷持续曲线", xlabel="累计小时占比/%", ylabel="电负荷/kW")
    axes[1].plot(
        duration,
        annual_inputs["pv_cf"].sort_values(ascending=False).to_numpy(),
        label="光伏容量因子",
        color=ENGINEERING_COLORS["pv"],
    )
    axes[1].plot(
        duration,
        annual_inputs["wind_cf_calibrated"].sort_values(ascending=False).to_numpy(),
        label="风电容量因子",
        color=ENGINEERING_COLORS["wind"],
    )
    axes[1].set(title="可再生能源资源持续曲线", xlabel="累计小时占比/%", ylabel="容量因子/p.u.")
    axes[1].legend(frameon=False)
    return _save_engineering_figure(fig, axes, figure_path, source_note)


def plot_representative_period_errors(
    diagnostics: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot supplied representative-period reconstruction errors."""

    _require_frame(
        diagnostics,
        {"scope", "feature", "metric", "relative_error"},
        "representative_diagnostics",
    )
    figure_path = _prepare_engineering_figure(output_path)
    selected = diagnostics.copy()
    selected["label"] = (
        selected["scope"].astype(str)
        + " | "
        + selected["feature"].astype(str)
        + " | "
        + selected["metric"].astype(str)
    )
    selected = selected.sort_values("relative_error", ascending=False).head(30)
    fig, ax = plt.subplots(figsize=(12, max(5.2, 0.25 * len(selected) + 1.8)))
    ax.barh(
        selected["label"][::-1],
        100 * selected["relative_error"][::-1],
        color=ENGINEERING_COLORS["wind"],
    )
    ax.set(title="代表日重构误差（最大30项）", xlabel="相对误差/%", ylabel="范围 | 特征 | 指标")
    return _save_engineering_figure(fig, [ax], figure_path, source_note)


def plot_portfolio_capacity_and_cost(
    portfolio_summary: pd.DataFrame,
    portfolio_capacity: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Compare supplied capacities and annual cost without recalculating KPIs."""

    _require_frame(
        portfolio_summary,
        {"portfolio_id", "annual_total_cost_cny"},
        "portfolio_summary",
    )
    _require_frame(
        portfolio_capacity,
        {"portfolio_id", "capacity_variable", "capacity_value"},
        "portfolio_capacity",
    )
    figure_path = _prepare_engineering_figure(output_path)
    capacity = portfolio_capacity.copy()
    capacity["unit"] = capacity["capacity_variable"].map(_capacity_unit)
    name_map = _portfolio_name_map(portfolio_summary)
    portfolio_order = portfolio_summary["portfolio_id"].map(name_map).tolist()
    capacity["portfolio_label"] = capacity["portfolio_id"].map(name_map)
    capacity["capacity_label"] = capacity["capacity_variable"].map(_capacity_label)
    units = [unit for unit in ("kW", "kWh", "kg") if unit in set(capacity["unit"])]
    fig, axes = plt.subplots(1, len(units) + 1, figsize=(5 * (len(units) + 1), 5.5))
    axes_list = list(axes) if hasattr(axes, "__len__") else [axes]
    for ax, unit in zip(axes_list, units):
        subset = capacity.loc[capacity["unit"] == unit]
        pivot = subset.pivot(
            index="portfolio_label", columns="capacity_label", values="capacity_value"
        ).fillna(0.0).reindex(portfolio_order, fill_value=0.0)
        pivot.plot(kind="bar", ax=ax, color=_engineering_palette(len(pivot.columns)))
        ax.set(title=f"设备容量（{unit}）", xlabel="工程方案", ylabel=f"容量/{unit}")
        ax.tick_params(axis="x", rotation=20)
        ax.legend(title="容量变量", fontsize=8, frameon=False)
    cost_ax = axes_list[-1]
    colors = [
        ENGINEERING_COLORS.get(str(portfolio), ENGINEERING_COLORS["grid"])
        for portfolio in portfolio_summary["portfolio_id"]
    ]
    cost_ax.bar(
        portfolio_summary["portfolio_id"].map(name_map),
        portfolio_summary["annual_total_cost_cny"] / 1e8,
        color=colors,
    )
    cost_ax.set(title="年化总成本", xlabel="工程方案", ylabel="成本/(亿元/年)")
    cost_ax.tick_params(axis="x", rotation=20)
    return _save_engineering_figure(fig, axes_list, figure_path, source_note)


def plot_monthly_operating_carbon(
    replay_hourly: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot monthly carbon values already provided by the replay output."""

    _require_frame(
        replay_hourly,
        {"timestamp_local", "location_carbon_kgco2", "zero_carbon_kgco2"},
        "replay_hourly",
    )
    figure_path = _prepare_engineering_figure(output_path)
    frame = replay_hourly.copy()
    frame["month"] = pd.to_datetime(frame["timestamp_local"]).dt.month
    grouping = ["month"]
    if "portfolio_id" in frame:
        grouping.insert(0, "portfolio_id")
    monthly = frame.groupby(grouping, as_index=False)[
        ["location_carbon_kgco2", "zero_carbon_kgco2"]
    ].sum()
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    for portfolio, selected in _portfolio_groups(monthly):
        axes[0].plot(
            selected["month"],
            selected["location_carbon_kgco2"] / 1e6,
            marker="o",
            label=portfolio,
        )
        axes[1].plot(
            selected["month"],
            selected["zero_carbon_kgco2"] / 1e6,
            marker="o",
            label=portfolio,
        )
    axes[0].set(title="位置法运行碳排放", ylabel="碳排放/tCO2")
    axes[1].set(title="零碳园区核算方法运行碳排放", xlabel="月份", ylabel="碳排放/tCO2")
    for ax in axes:
        ax.set_xticks(sorted(monthly["month"].unique()))
        ax.legend(frameon=False)
    return _save_engineering_figure(fig, axes, figure_path, source_note)


def plot_annual_storage_states(
    replay_hourly: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot annual battery and hydrogen inventory states from replay."""

    _require_frame(
        replay_hourly,
        {"timestamp_local", "battery_soc_kwh", "h2_storage_kg"},
        "replay_hourly",
    )
    figure_path = _prepare_engineering_figure(output_path)
    frame = replay_hourly.copy()
    frame["timestamp_local"] = pd.to_datetime(frame["timestamp_local"])
    fig, axes = plt.subplots(2, 1, figsize=(13, 7.5), sharex=True)
    for portfolio, selected in _portfolio_groups(frame):
        axes[0].plot(
            selected["timestamp_local"], selected["battery_soc_kwh"], label=portfolio
        )
        axes[1].plot(
            selected["timestamp_local"], selected["h2_storage_kg"], label=portfolio
        )
    axes[0].set(title="电池能量状态", ylabel="电量/kWh")
    axes[1].set(title="储氢库存", xlabel="时间", ylabel="储氢量/kg")
    for ax in axes:
        ax.legend(frameon=False)
    return _save_engineering_figure(fig, axes, figure_path, source_note)


def plot_extreme_week_dispatch(
    replay_hourly: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot a caller-labelled extreme window, with an explicit fallback label."""

    required = {
        "timestamp_local",
        "electric_load_kw",
        "pv_used_kw",
        "wind_used_kw",
        "grid_buy_kw",
        "battery_charge_kw",
        "battery_discharge_kw",
    }
    _require_frame(replay_hourly, required, "replay_hourly")
    figure_path = _prepare_engineering_figure(output_path)
    frame = replay_hourly.copy()
    marked = "is_extreme_week" in frame and frame["is_extreme_week"].astype(bool).any()
    selected = frame.loc[frame["is_extreme_week"].astype(bool)] if marked else frame.head(168)
    selected = selected.sort_values("timestamp_local")
    title = "极端周电力调度" if marked else "调度窗口（未提供极端周标记）"
    fig, axes = plt.subplots(2, 1, figsize=(13, 7.5), sharex=True)
    x = pd.to_datetime(selected["timestamp_local"])
    axes[0].plot(x, selected["electric_load_kw"], label="电负荷", color=ENGINEERING_COLORS["load"])
    axes[0].plot(x, selected["pv_used_kw"], label="光伏利用", color=ENGINEERING_COLORS["pv"])
    axes[0].plot(x, selected["wind_used_kw"], label="风电利用", color=ENGINEERING_COLORS["wind"])
    axes[0].plot(x, selected["grid_buy_kw"], label="电网购电", color=ENGINEERING_COLORS["grid"])
    axes[1].plot(x, selected["battery_charge_kw"], label="电池充电", color=ENGINEERING_COLORS["battery"])
    axes[1].plot(x, -selected["battery_discharge_kw"], label="电池放电（负向显示）", color="#A4478A")
    axes[0].set(title=title, ylabel="功率/kW")
    axes[1].set(xlabel="时间", ylabel="功率/kW")
    for ax in axes:
        ax.legend(frameon=False, ncol=4)
    return _save_engineering_figure(fig, axes, figure_path, source_note)


def plot_outage_duration_reliability(
    reliability_summary: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot supplied outage-duration, critical-supply and ENS results."""

    _require_frame(
        reliability_summary,
        {"duration_hours", "critical_load_supply_ratio", "ens_total_kwh"},
        "reliability_summary",
    )
    figure_path = _prepare_engineering_figure(output_path)
    fig, ax = plt.subplots(figsize=(10, 5.8))
    ens_ax = ax.twinx()
    for portfolio, selected in _portfolio_groups(reliability_summary):
        selected = selected.sort_values("duration_hours")
        ax.plot(
            selected["duration_hours"],
            100 * selected["critical_load_supply_ratio"],
            marker="o",
            label=f"{portfolio} 关键负荷供能率",
        )
        ens_ax.plot(
            selected["duration_hours"],
            selected["ens_total_kwh"],
            marker="s",
            linestyle="--",
            label=f"{portfolio} ENS",
        )
    ax.set(title="孤网停电时长—供能可靠性", xlabel="停电持续时间/h", ylabel="关键负荷供能率/%")
    ens_ax.set_ylabel("未供能量 ENS/kWh")
    lines, labels = ax.get_legend_handles_labels()
    other, other_labels = ens_ax.get_legend_handles_labels()
    ax.legend(lines + other, labels + other_labels, frameon=False)
    return _save_engineering_figure(fig, [ax, ens_ax], figure_path, source_note)


def plot_cost_carbon_reliability_tradeoff(
    portfolio_summary: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot supplied cost, carbon and reliability portfolio metrics."""

    _require_frame(
        portfolio_summary,
        {
            "portfolio_id",
            "annual_total_cost_cny",
            "zero_carbon_total_kgco2",
            "critical_load_supply_ratio",
            "minimum_island_survival_hours",
        },
        "portfolio_summary",
    )
    figure_path = _prepare_engineering_figure(output_path)
    fig, ax = plt.subplots(figsize=(9, 6.2))
    sizes = 70 + 18 * portfolio_summary["minimum_island_survival_hours"].clip(lower=0)
    colors = [
        ENGINEERING_COLORS.get(str(portfolio), ENGINEERING_COLORS["grid"])
        for portfolio in portfolio_summary["portfolio_id"]
    ]
    ax.scatter(
        portfolio_summary["annual_total_cost_cny"] / 1e8,
        portfolio_summary["zero_carbon_total_kgco2"] / 1e6,
        s=sizes,
        c=colors,
        alpha=0.82,
        edgecolors="white",
        linewidths=1.2,
    )
    for _, row in portfolio_summary.iterrows():
        portfolio_label = (
            row["portfolio_name"]
            if "portfolio_name" in row and pd.notna(row["portfolio_name"])
            else _portfolio_label(str(row["portfolio_id"]))
        )
        ax.annotate(
            f"{portfolio_label}\n供能率 {row['critical_load_supply_ratio']:.1%}",
            (row["annual_total_cost_cny"] / 1e8, row["zero_carbon_total_kgco2"] / 1e6),
            xytext=(5, 6),
            textcoords="offset points",
        )
    ax.set(
        title="成本—碳排—可靠性权衡",
        xlabel="年化总成本/(亿元/年)",
        ylabel="零碳园区核算碳排放/tCO2",
    )
    ax.text(
        0.01,
        0.02,
        "气泡面积表示最短孤网生存时长；标签供能率为传入指标",
        transform=ax.transAxes,
        fontsize=8,
        color="#555555",
    )
    return _save_engineering_figure(fig, [ax], figure_path, source_note)


def plot_sensitivity_tornado(
    sensitivity_summary: pd.DataFrame,
    output_path: str | Path,
    *,
    source_note: str,
) -> Path:
    """Plot supplied low/high cost impacts as a tornado chart."""

    _require_frame(
        sensitivity_summary,
        {"parameter", "low_impact_cny", "high_impact_cny"},
        "sensitivity_summary",
    )
    figure_path = _prepare_engineering_figure(output_path)
    frame = sensitivity_summary.copy()
    fig, ax = plt.subplots(figsize=(10, max(5.2, 0.6 * len(frame) + 2)))
    positions = range(len(frame))
    ax.barh(
        positions,
        frame["low_impact_cny"] / 1e6,
        color="#4B82C3",
        label="低值相对基准影响",
    )
    ax.barh(
        positions,
        frame["high_impact_cny"] / 1e6,
        color="#D17A22",
        label="高值相对基准影响",
    )
    ax.axvline(0, color="#333333", linewidth=0.9)
    ax.set_yticks(list(positions), frame["parameter"])
    ax.set(title="年化总成本敏感性", xlabel="相对基准成本变化/(百万元/年)", ylabel="敏感参数")
    ax.legend(frameon=False)
    return _save_engineering_figure(fig, [ax], figure_path, source_note)


def _prepare_engineering_figure(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _configure_chinese_font()
    return path


def _save_engineering_figure(fig, axes, path: Path, source_note: str) -> Path:
    for ax in axes:
        ax.grid(True, alpha=0.18, linewidth=0.7)
    fig.text(0.01, 0.008, source_note, fontsize=7.5, color="#666666")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _require_frame(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    if frame.empty:
        raise ValueError(f"{label} cannot be empty")
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def _portfolio_groups(frame: pd.DataFrame):
    if "portfolio_id" in frame:
        for portfolio, selected in frame.groupby("portfolio_id", sort=False):
            yield _portfolio_label(str(portfolio)), selected
    else:
        yield "本次运行", frame


def _capacity_unit(variable: str) -> str:
    if variable.endswith("_kwh"):
        return "kWh"
    if variable.endswith("_kg"):
        return "kg"
    return "kW"


def _capacity_label(variable: str) -> str:
    labels = {
        "wind_capacity_kw": "风电",
        "pv_capacity_kw": "光伏",
        "battery_power_capacity_kw": "电池功率",
        "battery_energy_capacity_kwh": "电池容量",
        "electrolyzer_power_capacity_kw": "电解槽",
        "h2_storage_capacity_kg": "储氢罐",
        "fuel_cell_power_capacity_kw": "燃料电池",
        "heat_pump_power_capacity_kw": "热泵",
    }
    return labels.get(variable, variable)


def _portfolio_label(portfolio_id: str) -> str:
    return {
        "economic": "经济型",
        "low_carbon": "低碳型",
        "resilience": "韧性型",
    }.get(portfolio_id, portfolio_id)


def _portfolio_name_map(summary: pd.DataFrame) -> dict[object, str]:
    if "portfolio_name" in summary:
        return {
            row["portfolio_id"]: str(row["portfolio_name"])
            for _, row in summary.iterrows()
        }
    return {
        portfolio: _portfolio_label(str(portfolio))
        for portfolio in summary["portfolio_id"]
    }


def _engineering_palette(count: int) -> list[str]:
    palette = ["#32628F", "#2E8B57", "#D17A22", "#7957A8", "#18A6A6", "#B34D4D"]
    return [palette[index % len(palette)] for index in range(count)]


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
