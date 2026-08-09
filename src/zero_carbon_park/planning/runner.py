"""容量规划运行入口。"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from pathlib import Path

import matplotlib
import pandas as pd
from pyomo.environ import value

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zero_carbon_park.data.loader import load_input_workbook
from zero_carbon_park.optimization.solver import solve_model
from zero_carbon_park.planning.builder import build_capacity_planning_model
from zero_carbon_park.planning.cost_params import get_default_planning_cost_params
from zero_carbon_park.planning.results import extract_capacity_planning_results
from zero_carbon_park.planning.variables import CAPACITY_BOUNDS
from zero_carbon_park.reporting.plots import (
    plot_annual_carbon_by_typical_day,
    plot_annual_cost_breakdown,
)
from zero_carbon_park.typical_days.definitions import get_default_typical_days
from zero_carbon_park.typical_days.generator import generate_typical_day_workbook


def classify_independent_engineering_solution(
    *,
    candidate_capacities: dict[str, float],
    baseline_capacities: dict[str, float],
    candidate_metrics: dict[str, float],
    baseline_metrics: dict[str, float],
    relative_threshold: float = 1.0e-4,
    absolute_threshold: float = 1.0e-6,
) -> tuple[bool, str]:
    """Reject a portfolio label when capacities and outcomes are numerically identical."""

    if relative_threshold < 0.0 or absolute_threshold < 0.0:
        raise ValueError("engineering-solution thresholds cannot be negative")

    def materially_different(candidate: dict[str, float], baseline: dict[str, float]) -> bool:
        if set(candidate) != set(baseline):
            raise ValueError("candidate and baseline must use identical fields")
        return any(
            abs(float(candidate[name]) - float(baseline[name]))
            > max(
                absolute_threshold,
                relative_threshold
                * max(abs(float(candidate[name])), abs(float(baseline[name])), 1.0),
            )
            for name in candidate
        )

    independent = materially_different(
        candidate_capacities, baseline_capacities
    ) or materially_different(candidate_metrics, baseline_metrics)
    return (
        (True, "形成独立工程方案")
        if independent
        else (False, "未形成独立工程方案")
    )


def solve_engineering_portfolios(
    typical_days,
    cost_params,
    *,
    capacity_upper_bounds: dict[str, float],
    low_carbon_cost_ratio: float = 1.10,
    critical_supply_min_ratio: float = 0.99,
    secure_capacity_multiplier: float = 1.20,
    secure_battery_duration_hours: float = 4.0,
    resilience_planning_islanded: bool = True,
    time_limit_seconds: float | None = 3_600.0,
    mip_gap: float | None = 0.01,
) -> dict[str, pd.DataFrame]:
    """Solve three auditable capacity portfolios from one representative-day input.

    The low-carbon case minimizes operating emissions inside a cost budget based
    on the proven economic optimum. The resilience case always prohibits
    externally purchased hydrogen and may be sized either islanded or in normal
    grid-connected operation followed by fixed-capacity island-event validation.
    The 120% firm-capacity check is an engineering benchmark, not certification.
    Formal studies may size the resilience portfolio in normal grid-connected
    operation and reserve islanding for fixed-capacity chronological events;
    this avoids treating every weighted representative day as an indefinitely
    repeated island.
    """

    _validate_portfolio_inputs(
        capacity_upper_bounds=capacity_upper_bounds,
        low_carbon_cost_ratio=low_carbon_cost_ratio,
        critical_supply_min_ratio=critical_supply_min_ratio,
        secure_capacity_multiplier=secure_capacity_multiplier,
        secure_battery_duration_hours=secure_battery_duration_hours,
    )
    common = {
        "typical_days": typical_days,
        "cost_params": cost_params,
        "capacity_upper_bounds": capacity_upper_bounds,
    }

    economic_model = build_capacity_planning_model(**common, objective_mode="economic")
    _require_full_load_service(economic_model)
    economic = _solve_engineering_case(
        "economic",
        economic_model,
        time_limit_seconds=time_limit_seconds,
        mip_gap=mip_gap,
    )
    if economic["status"] != "optimal":
        raise RuntimeError(
            "economic baseline is not proven optimal; low-carbon cost budget "
            f"cannot be established (status={economic['status']})"
        )

    economic_cost = float(economic["summary"]["annual_total_cost_cny"])
    low_carbon_cost_cap = economic_cost * low_carbon_cost_ratio
    low_carbon_model = build_capacity_planning_model(
        **common,
        objective_mode="carbon",
        annual_total_cost_cap_cny=low_carbon_cost_cap,
    )
    _require_full_load_service(low_carbon_model)
    low_carbon = _solve_engineering_case(
        "low_carbon",
        low_carbon_model,
        time_limit_seconds=time_limit_seconds,
        mip_gap=mip_gap,
        annual_cost_cap_cny=low_carbon_cost_cap,
    )
    resilience = _solve_engineering_case(
        "resilience",
        build_capacity_planning_model(
            **common,
            objective_mode="economic",
            islanded=resilience_planning_islanded,
            allow_external_h2=False,
            critical_supply_min_ratio=critical_supply_min_ratio,
            secure_capacity_multiplier=secure_capacity_multiplier,
            secure_battery_duration_hours=secure_battery_duration_hours,
        ),
        time_limit_seconds=time_limit_seconds,
        mip_gap=mip_gap,
    )

    cases = [economic, low_carbon, resilience]
    cost_input = asdict(cost_params) if is_dataclass(cost_params) else vars(cost_params)
    period_weights = {
        config.day_id: float(config.weight_days) for config, _ in typical_days
    }
    for case in cases:
        case["summary"]["cost_params_json"] = json.dumps(
            cost_input, ensure_ascii=False, sort_keys=True
        )
        case["summary"]["representative_period_weights_json"] = json.dumps(
            period_weights, ensure_ascii=False, sort_keys=True
        )
    _add_comparative_metrics(cases, economic)
    summary = pd.DataFrame([case["summary"] for case in cases])
    capacity = pd.concat([case["capacity"] for case in cases], ignore_index=True)
    cost_breakdown = pd.concat(
        [case["cost_breakdown"] for case in cases], ignore_index=True
    )
    constraints = pd.concat(
        [case["constraints"] for case in cases], ignore_index=True
    )
    hourly = pd.concat([case["hourly"] for case in cases], ignore_index=True)
    return {
        "summary": summary,
        "capacity": capacity,
        "cost_breakdown": cost_breakdown,
        "constraints": constraints,
        "hourly": hourly,
    }


def _require_full_load_service(model) -> None:
    """Prevent a planning objective from claiming savings via deliberate ENS."""

    for variable_name in (
        "load_shed_critical",
        "load_shed_important",
        "load_shed_interruptible",
    ):
        for variable in getattr(model, variable_name).values():
            variable.fix(0.0)


def _validate_portfolio_inputs(
    *,
    capacity_upper_bounds,
    low_carbon_cost_ratio,
    critical_supply_min_ratio,
    secure_capacity_multiplier,
    secure_battery_duration_hours,
) -> None:
    if set(capacity_upper_bounds) != set(CAPACITY_BOUNDS):
        raise ValueError("capacity_upper_bounds must contain all capacity variables")
    if any(
        not math.isfinite(float(selected)) or float(selected) <= 0.0
        for selected in capacity_upper_bounds.values()
    ):
        raise ValueError("capacity upper bounds must be finite and positive")
    if low_carbon_cost_ratio < 1.0:
        raise ValueError("low_carbon_cost_ratio must be at least 1.0")
    if not 0.0 <= critical_supply_min_ratio <= 1.0:
        raise ValueError("critical_supply_min_ratio must be within [0, 1]")
    if secure_capacity_multiplier < 0.0:
        raise ValueError("secure_capacity_multiplier cannot be negative")
    if secure_battery_duration_hours < 0.0:
        raise ValueError("secure_battery_duration_hours cannot be negative")


def _solve_engineering_case(
    portfolio_id,
    model,
    *,
    time_limit_seconds,
    mip_gap,
    annual_cost_cap_cny=None,
):
    status = solve_model(
        model,
        time_limit_seconds=time_limit_seconds,
        mip_gap=mip_gap,
    )
    # Do not silently extract uninitialized values or relabel solver outcomes.
    if status not in {"optimal", "time_limit", "feasible"}:
        raise RuntimeError(f"portfolio {portfolio_id} has no usable solution: {status}")
    try:
        results = extract_capacity_planning_results(model, status)
    except (TypeError, ValueError) as exc:
        if status != "optimal":
            raise RuntimeError(
                f"portfolio {portfolio_id} status={status}: no extractable incumbent"
            ) from exc
        raise
    summary = results["summary"].iloc[0].to_dict()
    capacities = dict(
        zip(
            results["capacity"]["capacity_variable"],
            results["capacity"]["capacity_value"],
        )
    )
    critical_energy = sum(
        float(value(model.weight_days[d]))
        * sum(float(value(model.critical_load[d, t])) for t in model.T)
        for d in model.D
    )
    critical_ens = float(summary["annual_ens_critical_kwh"])
    critical_supply_rate = (
        max(0.0, 1.0 - critical_ens / critical_energy)
        if critical_energy > 0.0
        else 1.0
    )
    secure_required = float(value(model.secure_capacity_multiplier)) * float(
        value(model.peak_critical_load_kw)
    )
    secure_available = (
        float(capacities["battery_power_capacity_kw"])
        + float(capacities["fuel_cell_power_capacity_kw"])
    )
    secure_battery_energy_required = (
        float(value(model.secure_battery_duration_hours))
        * float(capacities["battery_power_capacity_kw"])
    )
    solve_metadata = getattr(model, "solve_metadata", {})
    summary.update(
        {
            "portfolio_id": portfolio_id,
            "objective_basis": (
                "minimum annualized total cost"
                if portfolio_id != "low_carbon"
                else "minimum operating carbon within economic cost budget"
            ),
            "annual_cost_cap_cny": annual_cost_cap_cny,
            "annual_cost_cap_margin_cny": (
                annual_cost_cap_cny - float(summary["annual_total_cost_cny"])
                if annual_cost_cap_cny is not None
                else None
            ),
            "critical_load_supply_rate": critical_supply_rate,
            "critical_supply_margin_ratio": critical_supply_rate
            - float(value(model.critical_supply_min_ratio)),
            "secure_self_supply_capacity_kw": secure_available,
            "secure_capacity_required_kw": secure_required,
            "secure_capacity_margin_kw": secure_available - secure_required,
            "secure_battery_duration_hours": float(
                value(model.secure_battery_duration_hours)
            ),
            "secure_battery_energy_margin_kwh": float(
                capacities["battery_energy_capacity_kwh"]
            )
            - secure_battery_energy_required,
            "islanded_design_basis": bool(model.islanded),
            "islanded_validation_required": portfolio_id == "resilience",
            "external_hydrogen_allowed": bool(model.allow_external_h2),
            "certification_claimed": False,
            "engineering_boundary": "120%保安负荷为工程对标，不构成认证结论",
            "carbon_accounting_boundary": "购电与燃气运行排放；外送电不抵扣",
            "capacity_upper_bounds_json": json.dumps(
                model.capacity_upper_bounds, ensure_ascii=False, sort_keys=True
            ),
            "solver_requested_mip_gap": solve_metadata.get("requested_mip_gap"),
            "solver_actual_mip_gap": solve_metadata.get("actual_gap"),
            "solver_status_raw": solve_metadata.get("solver_status"),
            "solver_termination_condition": solve_metadata.get(
                "termination_condition", status
            ),
        }
    )
    capacity = results["capacity"].copy()
    capacity.insert(0, "portfolio_id", portfolio_id)
    hourly = results["hourly"].copy()
    hourly.insert(0, "portfolio_id", portfolio_id)
    cost_rows = [
        ("operation", summary["annual_operation_cost_cny"]),
        ("annualized_investment", summary["annualized_investment_cost_cny"]),
        ("demand_charge", summary["annual_demand_charge_cost_cny"]),
        ("backup_value", -summary["annual_fuel_cell_backup_value_cny"]),
        ("total", summary["annual_total_cost_cny"]),
    ]
    cost_breakdown = pd.DataFrame(
        [
            {
                "portfolio_id": portfolio_id,
                "cost_component": component,
                "annual_cost_cny": selected,
            }
            for component, selected in cost_rows
        ]
    )
    constraints = pd.DataFrame(
        [
            {
                "portfolio_id": portfolio_id,
                "constraint": "economic_cost_budget",
                "margin": summary["annual_cost_cap_margin_cny"],
                "unit": "CNY/year",
            },
            {
                "portfolio_id": portfolio_id,
                "constraint": "critical_load_supply_rate",
                "margin": summary["critical_supply_margin_ratio"],
                "unit": "p.u.",
            },
            {
                "portfolio_id": portfolio_id,
                "constraint": "firm_self_supply_capacity",
                "margin": summary["secure_capacity_margin_kw"],
                "unit": "kW",
            },
            {
                "portfolio_id": portfolio_id,
                "constraint": "secure_battery_duration",
                "margin": summary["secure_battery_energy_margin_kwh"],
                "unit": "kWh",
            },
        ]
    )
    return {
        "status": status,
        "summary": summary,
        "capacities": capacities,
        "capacity": capacity,
        "hourly": hourly,
        "cost_breakdown": cost_breakdown,
        "constraints": constraints,
    }


def _add_comparative_metrics(cases, economic):
    baseline = economic["summary"]
    baseline_metrics = {
        "cost": float(baseline["annual_total_cost_cny"]),
        "carbon": float(baseline["annual_carbon_emission_kg"]),
        "reliability": float(baseline["critical_load_supply_rate"]),
    }
    for case in cases:
        selected = case["summary"]
        selected_metrics = {
            "cost": float(selected["annual_total_cost_cny"]),
            "carbon": float(selected["annual_carbon_emission_kg"]),
            "reliability": float(selected["critical_load_supply_rate"]),
        }
        independent, label = classify_independent_engineering_solution(
            candidate_capacities=case["capacities"],
            baseline_capacities=economic["capacities"],
            candidate_metrics=selected_metrics,
            baseline_metrics=baseline_metrics,
        )
        if case is economic:
            independent, label = True, "经济型基准方案"
        selected.update(
            {
                "incremental_cost_vs_economic_cny": selected_metrics["cost"]
                - baseline_metrics["cost"],
                "carbon_reduction_vs_economic_kg": baseline_metrics["carbon"]
                - selected_metrics["carbon"],
                "ens_reduction_vs_economic_kwh": float(
                    baseline["annual_ens_critical_kwh"]
                )
                - float(selected["annual_ens_critical_kwh"]),
                "reliability_benefit_vs_economic": selected_metrics["reliability"]
                - baseline_metrics["reliability"],
                "is_independent_engineering_solution": independent,
                "engineering_solution_label": label,
            }
        )


def run_capacity_planning(
    workbook_path: str | Path,
    output_root: str | Path = "outputs",
) -> dict[str, Path]:
    """运行多典型日容量规划优化并导出结果。"""

    workbook = load_input_workbook(workbook_path)
    typical_days = [
        (config, generate_typical_day_workbook(workbook, config))
        for config in get_default_typical_days()
    ]
    cost_params = get_default_planning_cost_params()
    model = build_capacity_planning_model(typical_days, cost_params)
    status = solve_model(model)
    results = extract_capacity_planning_results(model, status)

    output_dir = Path(output_root) / "results" / "v2_capacity_planning"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = _export_tables(results, output_dir)
    paths["capacity_mix_png"] = _plot_capacity_mix(
        results["capacity"],
        output_dir / "capacity_mix.png",
    )
    paths["annual_cost_breakdown_png"] = plot_annual_cost_breakdown(
        results["summary"],
        output_dir / "annual_cost_breakdown.png",
    )
    paths["annual_carbon_by_typical_day_png"] = plot_annual_carbon_by_typical_day(
        results["typical_day_operation"],
        output_dir / "annual_carbon_by_typical_day.png",
    )
    paths["planning_conclusion_md"] = _export_planning_conclusion(
        results,
        output_dir / "planning_conclusion.md",
    )
    return paths


def _export_tables(results: dict, output_dir: Path) -> dict[str, Path]:
    summary_csv = output_dir / "planning_summary.csv"
    summary_excel = output_dir / "planning_summary.xlsx"
    capacity_csv = output_dir / "planning_capacity_result.csv"
    capacity_excel = output_dir / "planning_capacity_result.xlsx"
    operation_csv = output_dir / "planning_typical_day_operation.csv"
    operation_excel = output_dir / "planning_typical_day_operation.xlsx"
    hourly_csv = output_dir / "planning_hourly_results.csv"

    # Annual monetary totals are reported to whole CNY.  This is both the
    # meaningful reporting precision at park scale and keeps the exported
    # accounting identity exact after CSV readers parse the values as floats.
    summary_export = results["summary"].copy()
    money_columns = [
        "annual_operation_cost_cny",
        "annualized_investment_cost_cny",
        "annual_demand_charge_cost_cny",
        "annual_fuel_cell_backup_value_cny",
    ]
    summary_export[money_columns] = summary_export[money_columns].round(0)
    summary_export["annual_total_cost_cny"] = (
        summary_export["annual_operation_cost_cny"]
        + summary_export["annualized_investment_cost_cny"]
        + summary_export["annual_demand_charge_cost_cny"]
        - summary_export["annual_fuel_cell_backup_value_cny"]
    )
    summary_export.to_csv(summary_csv, index=False, encoding="utf-8-sig")
    summary_export.to_excel(summary_excel, index=False)
    results["capacity"].to_csv(capacity_csv, index=False, encoding="utf-8-sig")
    results["capacity"].to_excel(capacity_excel, index=False)
    results["typical_day_operation"].to_csv(
        operation_csv, index=False, encoding="utf-8-sig"
    )
    results["typical_day_operation"].to_excel(operation_excel, index=False)
    results["hourly"].to_csv(hourly_csv, index=False, encoding="utf-8-sig")

    return {
        "planning_summary_csv": summary_csv,
        "planning_summary_excel": summary_excel,
        "planning_capacity_result_csv": capacity_csv,
        "planning_capacity_result_excel": capacity_excel,
        "planning_typical_day_operation_csv": operation_csv,
        "planning_typical_day_operation_excel": operation_excel,
        "planning_hourly_results_csv": hourly_csv,
    }


def _plot_capacity_mix(capacity, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(capacity["capacity_variable"], capacity["capacity_value"])
    ax.set_title("容量规划最优设备容量")
    ax.set_ylabel("容量值")
    ax.tick_params(axis="x", labelrotation=40)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def _export_planning_conclusion(results: dict, output_path: Path) -> Path:
    summary = results["summary"].iloc[0]
    capacity = results["capacity"].set_index("capacity_variable")["capacity_value"]
    text = f"""# 容量规划优化结果

## 1. 年度成本

- 求解状态：{summary['status']}
- 年度运行成本：{summary['annual_operation_cost_cny']:.2f} 元
- 年化投资成本：{summary['annualized_investment_cost_cny']:.2f} 元
- 年度总成本：{summary['annual_total_cost_cny']:.2f} 元
- 年度碳排放：{summary['annual_carbon_emission_kg']:.2f} kgCO2
- 年度新能源消纳率：{summary['annual_renewable_consumption_rate']:.2%}
- 年度外部补氢量：{summary['annual_h2_external_supply_kg']:.2f} kg

## 2. 最优容量

- 风电装机：{capacity['wind_capacity_kw']:.2f} kW
- 光伏装机：{capacity['pv_capacity_kw']:.2f} kW
- 电池功率：{capacity['battery_power_capacity_kw']:.2f} kW
- 电池容量：{capacity['battery_energy_capacity_kwh']:.2f} kWh
- 电解槽功率：{capacity['electrolyzer_power_capacity_kw']:.2f} kW
- 储氢容量：{capacity['h2_storage_capacity_kg']:.2f} kg
- 燃料电池功率：{capacity['fuel_cell_power_capacity_kw']:.2f} kW
- 热泵功率：{capacity['heat_pump_power_capacity_kw']:.2f} kW

## 3. 说明

当前容量规划使用三个缩放生成的典型日和工程假设投资参数，适合验证规划-运行一体化方法。后续若替换真实全年数据和设备报价，规划结果需要重新计算。
"""
    output_path.write_text(text, encoding="utf-8")
    return output_path
