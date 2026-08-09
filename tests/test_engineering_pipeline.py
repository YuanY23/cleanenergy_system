from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from zero_carbon_park.reporting.engineering_report import (
    EngineeringReportInputs,
    generate_static_engineering_outputs,
)
from zero_carbon_park.reporting.plots import plot_portfolio_capacity_and_cost


def _inputs() -> EngineeringReportInputs:
    timestamps = pd.date_range(
        "2024-01-01", periods=48, freq="h", tz="Asia/Shanghai"
    )
    annual = pd.DataFrame(
        {
            "timestamp_local": timestamps,
            "electric_load_kw": [100.0 + hour for hour in range(48)],
            "pv_cf": [0.2] * 48,
            "wind_cf_calibrated": [0.4] * 48,
        }
    )
    diagnostics = pd.DataFrame(
        {
            "scope": ["annual", "annual", "monthly"],
            "month": [pd.NA, pd.NA, 1],
            "feature": ["electric_load_kw", "pv_cf", "electric_load_kw"],
            "metric": ["energy", "p95", "energy"],
            "original_value": [1000.0, 0.8, 100.0],
            "reconstructed_value": [990.0, 0.76, 97.0],
            "relative_error": [0.01, 0.05, 0.03],
        }
    )
    portfolios = pd.DataFrame(
        {
            "portfolio_id": ["economic", "low_carbon", "resilience"],
            "portfolio_name": ["经济型", "低碳型", "韧性型"],
            "annual_total_cost_cny": [987654321.0, 1020000000.0, 1100000000.0],
            "zero_carbon_total_kgco2": [6.0e8, 3.0e8, 4.0e8],
            "critical_load_supply_ratio": [0.90, 0.97, 1.00],
            "minimum_island_survival_hours": [4.0, 12.0, 24.0],
        }
    )
    capacities = pd.DataFrame(
        [
            {
                "portfolio_id": portfolio,
                "capacity_variable": variable,
                "capacity_value": value,
            }
            for portfolio, values in {
                "economic": (300.0, 200.0),
                "low_carbon": (400.0, 250.0),
                "resilience": (420.0, 360.0),
            }.items()
            for variable, value in zip(
                ("wind_capacity_kw", "battery_energy_capacity_kwh"), values
            )
        ]
    )
    replay = pd.DataFrame(
        {
            "timestamp_local": timestamps,
            "portfolio_id": ["resilience"] * 48,
            "location_carbon_kgco2": [500.0] * 48,
            "zero_carbon_kgco2": [300.0] * 48,
            "battery_soc_kwh": [50.0 + (hour % 24) for hour in range(48)],
            "h2_storage_kg": [10.0 + (hour % 12) for hour in range(48)],
            "electric_load_kw": [100.0] * 48,
            "pv_used_kw": [20.0] * 48,
            "wind_used_kw": [30.0] * 48,
            "grid_buy_kw": [50.0] * 48,
            "battery_charge_kw": [5.0] * 48,
            "battery_discharge_kw": [4.0] * 48,
            "is_extreme_week": [True] * 24 + [False] * 24,
        }
    )
    reliability = pd.DataFrame(
        {
            "portfolio_id": ["resilience"] * 3,
            "duration_hours": [4, 12, 24],
            "critical_load_supply_ratio": [1.0, 0.99, 0.95],
            "ens_total_kwh": [0.0, 20.0, 100.0],
        }
    )
    sensitivity = pd.DataFrame(
        {
            "parameter": ["电价", "电池投资", "可再生能源资源"],
            "low_impact_cny": [-2.0e7, -1.0e7, -0.5e7],
            "high_impact_cny": [3.0e7, 1.5e7, 2.0e7],
        }
    )
    notes = pd.DataFrame(
        {
            "category": ["公开事实", "模型结果", "工程假设"],
            "item": ["园区用电规模", "方案成本", "供热需求"],
            "statement": ["来自政府公开资料", "来自本次模型", "用于情景分析"],
            "source": ["https://example.gov/fact", "run-20240809", "assumptions.yaml"],
        }
    )
    return EngineeringReportInputs(
        annual_inputs=annual,
        representative_diagnostics=diagnostics,
        portfolio_summary=portfolios,
        portfolio_capacity=capacities,
        replay_hourly=replay,
        reliability_summary=reliability,
        sensitivity_summary=sensitivity,
        source_notes=notes,
    )


def test_static_bundle_is_run_scoped_complete_and_uses_supplied_metrics(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    original_costs = inputs.portfolio_summary.copy(deep=True)

    outputs = generate_static_engineering_outputs(
        output_root=tmp_path,
        run_id="run-20240809",
        inputs=inputs,
    )

    expected_keys = {
        "duration_curve_png",
        "representative_error_png",
        "portfolio_capacity_cost_png",
        "monthly_carbon_png",
        "storage_state_png",
        "extreme_week_dispatch_png",
        "outage_reliability_png",
        "tradeoff_bubble_png",
        "sensitivity_tornado_png",
        "technical_report_md",
        "results_index_csv",
    }
    assert set(outputs) == expected_keys
    expected_root = (tmp_path / "run-20240809" / "reporting").resolve()
    assert all(path.resolve().is_relative_to(expected_root) for path in outputs.values())
    assert all(path.is_file() and path.stat().st_size > 0 for path in outputs.values())

    report = outputs["technical_report_md"].read_text(encoding="utf-8")
    assert "987,654,321" in report
    assert "公开事实" in report and "模型结果" in report and "工程假设" in report
    assert "run-20240809" in report
    assert "S0" not in report and "S5" not in report

    index = pd.read_csv(outputs["results_index_csv"])
    assert set(index["artifact_key"]) == expected_keys - {"results_index_csv"}
    assert index["run_id"].eq("run-20240809").all()
    assert index["relative_path"].str.startswith("reporting/").all()
    pd.testing.assert_frame_equal(inputs.portfolio_summary, original_costs)


def test_static_bundle_rejects_empty_or_unsafe_run_inputs(tmp_path: Path) -> None:
    empty = _inputs()
    empty.annual_inputs.drop(empty.annual_inputs.index, inplace=True)
    with pytest.raises(ValueError, match="annual_inputs cannot be empty"):
        generate_static_engineering_outputs(
            output_root=tmp_path, run_id="run-empty", inputs=empty
        )
    with pytest.raises(ValueError, match="safe run identifier"):
        generate_static_engineering_outputs(
            output_root=tmp_path, run_id="../old-results", inputs=_inputs()
        )

    stale = _inputs()
    stale.source_notes.loc[stale.source_notes["category"] == "模型结果", "source"] = (
        "run-legacy"
    )
    with pytest.raises(ValueError, match="must reference current run_id"):
        generate_static_engineering_outputs(
            output_root=tmp_path, run_id="run-20240809", inputs=stale
        )


def test_capacity_and_cost_panels_keep_the_same_portfolio_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _inputs()
    captured_orders: list[list[str]] = []
    original_plot = pd.DataFrame.plot

    def capture_plot(frame: pd.DataFrame, *args: object, **kwargs: object) -> object:
        captured_orders.append(frame.index.tolist())
        return original_plot(frame)(*args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "plot", capture_plot)
    output = plot_portfolio_capacity_and_cost(
        inputs.portfolio_summary,
        inputs.portfolio_capacity,
        tmp_path / "portfolio.png",
        source_note="本次运行",
    )

    expected = ["经济型", "低碳型", "韧性型"]
    assert captured_orders == [expected, expected]
    assert output.is_file()
