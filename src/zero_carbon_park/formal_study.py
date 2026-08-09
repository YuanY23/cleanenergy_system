"""End-to-end formal 2024 planning, replay and resilience study.

The entry point consumes only files declared by a verified run manifest.  It
does not scan legacy result folders or read the historical Excel workbook.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

import pandas as pd

from zero_carbon_park.config import load_verified_manifest
from zero_carbon_park.data.annual_pipeline import (
    AnnualWeatherConfig,
    compare_nasa_power_monthly,
    load_era5_netcdf,
    load_nasa_power_monthly_check,
    transform_era5_hourly,
    validate_annual_weather,
)
from zero_carbon_park.data.formal_inputs import (
    NATURAL_GAS_FACTOR_KGCO2_PER_M3,
    build_annual_model_workbook,
    build_representative_workbooks,
    capacity_upper_bounds_kw,
)
from zero_carbon_park.planning.cost_params import (
    CarbonFactors,
    PlanningCostParams,
    capital_recovery_factor,
    get_default_planning_cost_params,
)
from zero_carbon_park.planning.runner import solve_engineering_portfolios
from zero_carbon_park.reliability.definitions import (
    ReliabilityEvent,
    build_outage_event_catalog,
    select_stress_start_times,
)
from zero_carbon_park.reliability.runner import run_reliability_catalog
from zero_carbon_park.replay.runner import ReplayConfig, run_rolling_replay
from zero_carbon_park.reporting.engineering_report import (
    EngineeringReportInputs,
    generate_static_engineering_outputs,
)
from zero_carbon_park.reporting.metrics import build_engineering_comparison
from zero_carbon_park.typical_days.clustering import build_representative_periods
from zero_carbon_park.typical_days.definitions import RepresentativePeriodConfig
from zero_carbon_park.typical_days.diagnostics import evaluate_compression
from zero_carbon_park.typical_days.runner import write_representative_period_artifacts


PORTFOLIO_NAMES = {
    "economic": "经济型",
    "low_carbon": "低碳型",
    "resilience": "韧性型",
}


@dataclass(frozen=True)
class FormalStudyRunConfig:
    representative_k: int = 12
    planning_time_limit_seconds: float = 1_800.0
    planning_mip_gap: float = 0.01
    replay_lookahead_hours: int = 336
    replay_commit_hours: int = 168
    replay_time_limit_seconds: float = 300.0
    replay_mip_gap: float = 0.01

    def __post_init__(self) -> None:
        if self.representative_k not in {8, 12, 16}:
            raise ValueError("representative_k must be 8, 12 or 16")


def run_formal_study(
    manifest_path: str | Path,
    *,
    repo_root: str | Path,
    config: FormalStudyRunConfig | None = None,
) -> dict[str, Path]:
    """Execute the formal study and publish one immutable run-scoped bundle."""

    selected = config or FormalStudyRunConfig()
    root = Path(repo_root).resolve()
    manifest = load_verified_manifest(manifest_path, repo_root=root)
    run_dir = manifest.manifest_path.parent
    paths = _prepare_output_directories(run_dir)

    raw_weather_path = _required_manifest_input(manifest.input_paths, "era5_hourly_raw")
    nasa_path = _required_manifest_input(manifest.input_paths, "nasa_power_hourly")
    weather_config = AnnualWeatherConfig(year=manifest.study_year)
    annual_weather = transform_era5_hourly(
        load_era5_netcdf(raw_weather_path), weather_config
    )
    weather_quality = validate_annual_weather(
        annual_weather,
        year=manifest.study_year,
        timezone_name=weather_config.timezone_name,
    )
    annual_workbook = build_annual_model_workbook(annual_weather)
    input_paths = _write_formal_inputs(
        paths["inputs"], annual_weather, annual_workbook, weather_quality
    )
    crosscheck = _build_weather_crosscheck(
        annual_weather, load_nasa_power_monthly_check(nasa_path)
    )
    input_paths["weather_crosscheck"] = _write_csv(
        crosscheck, paths["inputs"] / "weather_monthly_crosscheck.csv"
    )

    representative_runs: dict[int, tuple[object, pd.DataFrame]] = {}
    representative_quality_rows: list[dict[str, object]] = []
    for k in (8, 12, 16):
        result = build_representative_periods(
            annual_workbook.timeseries,
            RepresentativePeriodConfig(k=k),
        )
        diagnostics = evaluate_compression(annual_workbook.timeseries, result)
        representative_runs[k] = (result, diagnostics)
        representative_quality_rows.append(
            _compression_summary(
                diagnostics, k=k, selected=k == selected.representative_k
            )
        )
        write_representative_period_artifacts(
            result, diagnostics, paths["representative"] / f"k{k}"
        )
    _write_csv(
        pd.DataFrame(representative_quality_rows),
        paths["representative"] / "representative_period_selection.csv",
    )
    representative, representative_diagnostics = representative_runs[
        selected.representative_k
    ]
    typical_days = build_representative_workbooks(annual_workbook, representative)

    cost_params = formal_planning_cost_params()
    planning = solve_engineering_portfolios(
        typical_days,
        cost_params,
        capacity_upper_bounds=capacity_upper_bounds_kw(),
        resilience_planning_islanded=False,
        time_limit_seconds=selected.planning_time_limit_seconds,
        mip_gap=selected.planning_mip_gap,
    )
    planning_paths = _write_table_bundle(paths["planning"], "planning", planning)

    replay_config = ReplayConfig(
        lookahead_hours=selected.replay_lookahead_hours,
        commit_hours=selected.replay_commit_hours,
        solver_time_limit_seconds=selected.replay_time_limit_seconds,
        solver_mip_gap=selected.replay_mip_gap,
    )
    replay_frames: list[pd.DataFrame] = []
    replay_windows: list[pd.DataFrame] = []
    replay_quality: list[dict[str, object]] = []
    reliability_summaries: list[pd.DataFrame] = []
    reliability_hourly: list[pd.DataFrame] = []
    extreme_start = pd.Timestamp(representative.extreme_days["joint_stress"])
    extreme_dates = {
        (extreme_start + pd.Timedelta(days=offset)).date() for offset in range(-3, 4)
    }

    for portfolio_id in PORTFOLIO_NAMES:
        fixed_capacities = _portfolio_capacities(planning["capacity"], portfolio_id)
        replay = run_rolling_replay(
            annual_workbook,
            fixed_capacities=fixed_capacities,
            cost_params=cost_params,
            config=replay_config,
        )
        if not replay.publication_eligible:
            raise RuntimeError(
                f"portfolio {portfolio_id} failed replay publication gate: "
                f"{replay.quality_report}"
            )
        hourly = replay.hourly.copy()
        hourly.insert(0, "portfolio_id", portfolio_id)
        hourly["is_extreme_week"] = pd.to_datetime(
            hourly["timestamp_local"]
        ).dt.date.isin(extreme_dates)
        replay_frames.append(hourly)
        windows = replay.windows.copy()
        windows.insert(0, "portfolio_id", portfolio_id)
        replay_windows.append(windows)
        replay_quality.append(
            {"portfolio_id": portfolio_id, **replay.quality_report}
        )

        starts = _canonical_reliability_starts(
            annual_workbook.timeseries,
            select_stress_start_times(annual_workbook.timeseries, replay.hourly),
        )
        events = _reliability_events(starts)
        reliability = run_reliability_catalog(
            annual_workbook,
            replay_hourly=replay.hourly,
            fixed_capacities=fixed_capacities,
            cost_params=cost_params,
            events=events,
            portfolio_id=portfolio_id,
        )
        reliability_summaries.append(reliability["summary"])
        reliability_hourly.append(reliability["hourly"])

    replay_hourly = pd.concat(replay_frames, ignore_index=True)
    replay_window_table = pd.concat(replay_windows, ignore_index=True)
    replay_quality_table = pd.DataFrame(replay_quality)
    reliability_summary = pd.concat(reliability_summaries, ignore_index=True)
    reliability_hourly_table = pd.concat(reliability_hourly, ignore_index=True)
    replay_paths = {
        "hourly": _write_csv(replay_hourly, paths["replay"] / "replay_hourly.csv"),
        "windows": _write_csv(
            replay_window_table, paths["replay"] / "replay_windows.csv"
        ),
        "quality": _write_csv(
            replay_quality_table, paths["replay"] / "replay_quality.csv"
        ),
    }
    reliability_paths = {
        "summary": _write_csv(
            reliability_summary, paths["reliability"] / "reliability_summary.csv"
        ),
        "hourly": _write_csv(
            reliability_hourly_table,
            paths["reliability"] / "reliability_hourly.csv",
        ),
    }

    metrics = build_engineering_comparison(
        planning["summary"],
        replay_hourly,
        reliability_summary,
        carbon_factors=CarbonFactors(),
        natural_gas_factor_kgco2_per_m3=NATURAL_GAS_FACTOR_KGCO2_PER_M3,
        cost_tolerance_cny=0.1,
    )
    portfolio_summary = metrics["comparison"].copy()
    portfolio_summary.insert(
        1,
        "portfolio_name",
        portfolio_summary["portfolio_id"].map(PORTFOLIO_NAMES),
    )
    sensitivity = fixed_solution_sensitivity(
        planning["summary"], planning["capacity"], cost_params
    )
    source_notes = _source_notes(manifest.run_id)
    metric_paths = {
        "portfolio_summary": _write_csv(
            portfolio_summary, paths["metrics"] / "portfolio_summary.csv"
        ),
        "definitions": _write_csv(
            metrics["definitions"], paths["metrics"] / "metric_definitions.csv"
        ),
        "replay_with_carbon": _write_csv(
            metrics["replay_with_carbon"],
            paths["metrics"] / "replay_hourly_with_carbon.csv",
        ),
        "sensitivity": _write_csv(
            sensitivity, paths["metrics"] / "fixed_solution_sensitivity.csv"
        ),
        "source_notes": _write_csv(
            source_notes, paths["metrics"] / "source_notes.csv"
        ),
    }

    report_outputs = generate_static_engineering_outputs(
        output_root=root / "artifacts" / "runs",
        run_id=manifest.run_id,
        inputs=EngineeringReportInputs(
            annual_inputs=annual_workbook.timeseries,
            representative_diagnostics=representative_diagnostics,
            portfolio_summary=portfolio_summary,
            portfolio_capacity=planning["capacity"],
            replay_hourly=metrics["replay_with_carbon"],
            reliability_summary=reliability_summary,
            sensitivity_summary=sensitivity,
            source_notes=source_notes,
        ),
    )
    completion = {
        "run_id": manifest.run_id,
        "status": "complete",
        "study_year": manifest.study_year,
        "hours_per_portfolio": 8784,
        "representative_k": selected.representative_k,
        "portfolios": list(PORTFOLIO_NAMES),
        "reliability_events_per_portfolio": int(
            reliability_summary.groupby("portfolio_id").size().min()
        ),
        "config": asdict(selected),
    }
    completion_path = run_dir / "completion.json"
    _atomic_write_json(completion_path, completion)
    latest_path = root / "artifacts" / "latest.json"
    _atomic_write_json(
        latest_path,
        {
            "run_id": manifest.run_id,
            "manifest": manifest.manifest_path.relative_to(root).as_posix(),
            "completion": completion_path.relative_to(root).as_posix(),
        },
    )
    return {
        "manifest": manifest.manifest_path,
        "completion": completion_path,
        "latest": latest_path,
        **{f"input_{key}": value for key, value in input_paths.items()},
        **{f"planning_{key}": value for key, value in planning_paths.items()},
        **{f"replay_{key}": value for key, value in replay_paths.items()},
        **{f"reliability_{key}": value for key, value in reliability_paths.items()},
        **{f"metric_{key}": value for key, value in metric_paths.items()},
        **{f"report_{key}": value for key, value in report_outputs.items()},
    }


def formal_planning_cost_params() -> PlanningCostParams:
    """Return the explicit grid and external-hydrogen bounds for this study."""

    return replace(
        get_default_planning_cost_params(),
        grid_import_limit_kw=600_000.0,
        h2_external_supply_limit_kg_per_hour=30_000.0,
    )


def fixed_solution_sensitivity(
    planning_summary: pd.DataFrame,
    planning_capacity: pd.DataFrame,
    cost_params: PlanningCostParams,
) -> pd.DataFrame:
    """Calculate transparent one-at-a-time cost exposure without re-optimizing."""

    summary = planning_summary.set_index("portfolio_id").loc["economic"]
    capacities = _portfolio_capacities(planning_capacity, "economic")
    crf = lambda years: capital_recovery_factor(cost_params.discount_rate, years)
    exposures = {
        "风电CAPEX（±30%）": 0.30
        * capacities["wind_capacity_kw"]
        * cost_params.wind_capex_cny_per_kw
        * crf(cost_params.wind_life_years),
        "光伏CAPEX（±30%）": 0.30
        * capacities["pv_capacity_kw"]
        * cost_params.pv_capex_cny_per_kw
        * crf(cost_params.pv_life_years),
        "电池CAPEX（±30%）": 0.30
        * (
            capacities["battery_power_capacity_kw"]
            * cost_params.battery_power_capex_cny_per_kw
            + capacities["battery_energy_capacity_kwh"]
            * cost_params.battery_energy_capex_cny_per_kwh
        )
        * crf(cost_params.battery_life_years),
        "购电成本（±20%）": 0.20 * float(summary["annual_grid_cost_cny"]),
        "天然气成本（±20%）": 0.20 * float(summary["annual_gas_cost_cny"]),
    }
    return pd.DataFrame(
        [
            {
                "parameter": parameter,
                "low_impact_cny": -float(exposure),
                "high_impact_cny": float(exposure),
                "method": "固定容量与运行量的一次一变成本暴露，不重新优化",
            }
            for parameter, exposure in exposures.items()
        ]
    )


def _canonical_reliability_starts(
    annual_timeseries: pd.DataFrame, starts: pd.DataFrame
) -> pd.DataFrame:
    chosen = starts.loc[
        starts["reason"].isin(
            {"minimum_battery_soc", "minimum_h2_inventory", "lowest_renewable"}
        )
    ].copy()
    monthly = starts.loc[starts["reason"].eq("monthly_high_electric_load")].copy()
    loads = annual_timeseries.set_index("timestamp_local")["electric_load_kw"]
    monthly["_load"] = monthly["start_timestamp"].map(loads)
    if not monthly.empty:
        chosen = pd.concat(
            [chosen, monthly.nlargest(1, "_load").drop(columns="_load")],
            ignore_index=True,
        )
    return chosen.drop_duplicates(["reason", "start_timestamp"]).reset_index(drop=True)


def _reliability_events(starts: pd.DataFrame) -> tuple[ReliabilityEvent, ...]:
    base = list(build_outage_event_catalog(starts))
    lowest = starts.loc[starts["reason"].eq("lowest_renewable")]
    if not lowest.empty:
        start = pd.Timestamp(lowest.iloc[0]["start_timestamp"])
        base.extend(
            [
                ReliabilityEvent(
                    event_id="LOWEST_RENEWABLE_BATTERY_FAULT_24H",
                    start_timestamp=start,
                    duration_hours=24,
                    failed_devices=("battery",),
                    description="24 h islanding plus battery unavailability",
                ),
                ReliabilityEvent(
                    event_id="LOWEST_RENEWABLE_FUEL_CELL_FAULT_24H",
                    start_timestamp=start,
                    duration_hours=24,
                    failed_devices=("fuel_cell",),
                    description="24 h islanding plus fuel-cell unavailability",
                ),
            ]
        )
    return tuple(base)


def _build_weather_crosscheck(
    annual_weather: pd.DataFrame, nasa_monthly: pd.DataFrame
) -> pd.DataFrame:
    result = compare_nasa_power_monthly(annual_weather, nasa_monthly)
    result["wind_height_note"] = "ERA5 100 m；NASA POWER 50 m，仅作分布校核"
    return result


def _source_notes(run_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "category": "公开事实",
                "item": "2024年逐时气象",
                "statement": "ERA5为生产时序，NASA POWER仅作月度独立校核",
                "source": "ERA5_SINGLE_LEVELS_2024; NASA_POWER_HOURLY",
            },
            {
                "category": "公开事实",
                "item": "园区用电尺度",
                "statement": "31亿kWh仅用于合成负荷年度量级校准，不表述为SCADA",
                "source": "ORDOS_ZERO_CARBON_PARK_SCALE_2025",
            },
            {
                "category": "模型结果",
                "item": "容量、成本、碳与孤网保供",
                "statement": "来自本次代表日规划、8784小时固定容量回放及确定性事件",
                "source": run_id,
            },
            {
                "category": "工程假设",
                "item": "热氢负荷与设备造价",
                "statement": "采用有上下界的工程假设和国际公开成本基准，不作为报价",
                "source": "data/metadata/assumptions.yaml",
            },
        ]
    )


def _compression_summary(
    diagnostics: pd.DataFrame, *, k: int, selected: bool
) -> dict[str, object]:
    annual = diagnostics.loc[diagnostics["scope"].eq("annual")]
    monthly = diagnostics.loc[diagnostics["scope"].eq("monthly")]
    annual_energy = float(
        annual.loc[annual["metric"].eq("energy"), "relative_error"].max()
    )
    annual_shape = float(
        annual.loc[~annual["metric"].eq("energy"), "relative_error"].max()
    )
    monthly_energy = float(
        monthly.loc[monthly["metric"].eq("energy"), "relative_error"].max()
    )
    monthly_shape = float(
        monthly.loc[~monthly["metric"].eq("energy"), "relative_error"].max()
    )
    return {
        "k": k,
        "selected": selected,
        "annual_energy_max_error": annual_energy,
        "annual_shape_max_error": annual_shape,
        "monthly_energy_max_error": monthly_energy,
        "monthly_shape_max_error": monthly_shape,
        "annual_gate_passed": annual_energy <= 0.05 and annual_shape <= 0.10,
        "monthly_gate_passed": monthly_energy <= 0.15 and monthly_shape <= 0.20,
        "selection_basis": (
            "满足年度能量/形状门；月度偏差由8784小时全年回放复核"
            if selected
            else "候选方案"
        ),
    }


def _prepare_output_directories(run_dir: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name in (
        "inputs",
        "representative_periods",
        "planning",
        "replay",
        "reliability",
        "metrics",
    ):
        path = run_dir / name
        path.mkdir(exist_ok=False)
        result["representative" if name == "representative_periods" else name] = path
    return result


def _required_manifest_input(inputs, logical_name: str) -> Path:
    try:
        return Path(inputs[logical_name])
    except KeyError as exc:
        raise ValueError(f"formal manifest missing input: {logical_name}") from exc


def _portfolio_capacities(table: pd.DataFrame, portfolio_id: str) -> dict[str, float]:
    selected = table.loc[table["portfolio_id"].eq(portfolio_id)]
    if selected.empty:
        raise ValueError(f"missing capacity portfolio: {portfolio_id}")
    return {
        str(row.capacity_variable): float(row.capacity_value)
        for row in selected.itertuples(index=False)
    }


def _write_formal_inputs(
    output_dir: Path, annual_weather, annual_workbook, weather_quality
) -> dict[str, Path]:
    paths = {
        "weather": _write_csv(annual_weather, output_dir / "annual_weather_8784.csv"),
        "timeseries": _write_csv(
            annual_workbook.timeseries, output_dir / "annual_model_timeseries_8784.csv"
        ),
        "device_params": _write_csv(
            annual_workbook.device_params, output_dir / "device_params.csv"
        ),
        "economic_params": _write_csv(
            annual_workbook.economic_params, output_dir / "economic_params.csv"
        ),
    }
    quality_path = output_dir / "weather_quality.json"
    _atomic_write_json(quality_path, weather_quality)
    paths["weather_quality"] = quality_path
    return paths


def _write_table_bundle(output_dir: Path, prefix: str, tables) -> dict[str, Path]:
    return {
        name: _write_csv(frame, output_dir / f"{prefix}_{name}.csv")
        for name, frame in tables.items()
    }


def _write_csv(frame: pd.DataFrame, path: Path) -> Path:
    temporary = path.with_suffix(path.suffix + ".part")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)
    return path


def _atomic_write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


__all__ = [
    "FormalStudyRunConfig",
    "fixed_solution_sensitivity",
    "formal_planning_cost_params",
    "run_formal_study",
]
