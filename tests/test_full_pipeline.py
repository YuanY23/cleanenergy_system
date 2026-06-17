from pathlib import Path

import pandas as pd

from zero_carbon_park.cli import main, run_full_pipeline


def _workbook_path() -> Path:
    matches = list(Path(".").glob("*电热氢储优化调度_数据包.xlsx"))
    assert matches, "测试需要项目根目录下的数据包 xlsx 文件"
    return matches[0]


def test_run_full_pipeline_exports_results_figures_and_conclusions(tmp_path: Path):
    outputs = run_full_pipeline(_workbook_path(), tmp_path)

    expected_keys = {
        "processed_dir",
        "run_dir",
        "figure_dir",
        "conclusion_md",
        "input_curves_png",
        "device_outputs_png",
        "battery_soc_png",
        "h2_storage_png",
        "scenario_cost_png",
        "scenario_carbon_png",
        "scenario_renewable_png",
        "summary_csv",
        "hourly_csv",
    }
    assert expected_keys.issubset(outputs)

    for key in expected_keys:
        path = outputs[key]
        assert path.exists(), key
        if path.is_file():
            assert path.stat().st_size > 0, key

    summary = pd.read_csv(outputs["summary_csv"])
    assert list(summary["scenario_id"]) == ["S0", "S1", "S2", "S3", "S4", "S5"]
    assert summary["status"].eq("optimal").all()

    hourly = pd.read_csv(outputs["hourly_csv"])
    assert set(hourly["scenario_id"]) == {"S0", "S1", "S2", "S3", "S4", "S5"}
    assert len(hourly) == 24 * 6

    conclusion = outputs["conclusion_md"].read_text(encoding="utf-8")
    assert "项目结论初稿" in conclusion
    assert "S0" in conclusion
    assert "S5" in conclusion


def test_cli_run_typical_days_exports_v2_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-typical-days",
        ],
    )

    main()

    assert (tmp_path / "results" / "v2_typical_days" / "typical_day_summary.csv").exists()


def test_cli_run_annualization_exports_v2_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-annualization",
        ],
    )

    main()

    assert (tmp_path / "results" / "v2_annualized" / "annual_summary.csv").exists()
    assert (
        tmp_path / "results" / "v2_annualized" / "annual_conclusion.md"
    ).exists()


def test_cli_run_capacity_planning_exports_v2_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-capacity-planning",
        ],
    )

    main()

    assert (
        tmp_path / "results" / "v2_capacity_planning" / "planning_summary.csv"
    ).exists()
    assert (
        tmp_path / "results" / "v2_capacity_planning" / "planning_capacity_result.csv"
    ).exists()


def test_cli_run_investment_sensitivity_exports_v3_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-investment-sensitivity",
        ],
    )

    main()

    assert (
        tmp_path / "results" / "v3_investment_sensitivity" / "scenario_summary.csv"
    ).exists()
    assert (
        tmp_path / "results" / "v3_investment_sensitivity" / "capacity_results.csv"
    ).exists()


def test_cli_run_pareto_analysis_exports_v3_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-pareto-analysis",
        ],
    )

    main()

    assert (
        tmp_path / "results" / "v3_pareto_cost_carbon" / "pareto_summary.csv"
    ).exists()
    assert (
        tmp_path / "results" / "v3_pareto_cost_carbon" / "pareto_capacity_results.csv"
    ).exists()


def test_cli_run_uncertainty_stress_test_exports_v4_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-uncertainty-stress-test",
        ],
    )

    main()

    assert (
        tmp_path / "results" / "v4_uncertainty_stress_test" / "stress_summary.csv"
    ).exists()
    assert (
        tmp_path
        / "results"
        / "v4_uncertainty_stress_test"
        / "reference_capacity.csv"
    ).exists()


def test_cli_run_stochastic_planning_exports_v4_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-stochastic-planning",
        ],
    )

    main()

    assert (
        tmp_path / "results" / "v4_stochastic_planning" / "stochastic_summary.csv"
    ).exists()
    assert (
        tmp_path
        / "results"
        / "v4_stochastic_planning"
        / "stochastic_capacity_result.csv"
    ).exists()


def test_cli_run_robust_planning_exports_v4_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "zero-carbon-park",
            "--workbook",
            str(_workbook_path()),
            "--output",
            str(tmp_path),
            "--run-robust-planning",
        ],
    )

    main()

    assert (
        tmp_path / "results" / "v4_robust_planning" / "robust_summary.csv"
    ).exists()
    assert (
        tmp_path
        / "results"
        / "v4_robust_planning"
        / "robust_capacity_result.csv"
    ).exists()
