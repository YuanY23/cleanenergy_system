from __future__ import annotations

from pathlib import Path
import os

import pandas as pd
import pytest

import scripts.build_codex_data_workbook as workbook_builder
from scripts.build_codex_data_workbook import build_workbook


def test_workbook_builder_rejects_historical_or_unregistered_input(tmp_path: Path) -> None:
    historical = tmp_path / "outputs" / "annual.csv"
    historical.parent.mkdir()
    historical.write_text("timestamp_utc\n", encoding="utf-8")

    with pytest.raises(ValueError, match="data/processed"):
        build_workbook(
            annual_csv=historical,
            source_registry_csv=Path("data/metadata/source_registry.csv"),
            output_xlsx=Path("artifacts/runs/test/tables/audit.xlsx"),
            node_executable="missing-node",
            node_modules="missing-modules",
        )


def test_legacy_builder_contains_no_download_or_old_cache_logic() -> None:
    script = Path("scripts/build_codex_data_workbook.py").read_text(encoding="utf-8")

    assert "nasa_power_ordos_2024.json" not in script
    assert "urlopen" not in script
    assert "0.6849" not in script
    assert "data/processed" in script


def test_artifact_tool_builder_exports_and_renders_8784_hour_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = os.environ.get("CODEX_NODE")
    node_modules = os.environ.get("CODEX_NODE_MODULES")
    if not node or not node_modules:
        pytest.skip("bundled artifact-tool runtime not provided")

    processed = tmp_path / "data" / "processed"
    metadata = tmp_path / "data" / "metadata"
    output = tmp_path / "artifacts" / "runs" / "test" / "tables" / "audit.xlsx"
    processed.mkdir(parents=True)
    metadata.mkdir(parents=True)
    utc = pd.date_range("2023-12-31 16:00", periods=8784, freq="h", tz="UTC")
    local = utc.tz_convert("Asia/Shanghai")
    annual = pd.DataFrame(
        {
            "timestamp_utc": utc.astype(str),
            "timestamp_local": local.astype(str),
            "wind_speed_100m": 6.0,
            "solar_irradiance_w_m2": 300.0,
            "air_temperature_c": 5.0,
            "pv_cf": 0.2,
            "wind_cf_uncalibrated": 0.25,
            "wind_cf_calibrated": 0.27,
        }
    )
    annual_path = processed / "annual_timeseries_2024.csv"
    annual.to_csv(annual_path, index=False)
    source_path = metadata / "source_registry.csv"
    source_path.write_text(
        "field_name,source_id,source_category,url,published_at,retrieved_at,"
        "original_unit,target_unit,timezone,processing_method,conversion_formula,"
        "file_sha256,applicable_from,applicable_to,confidence,notes,is_primary,"
        "verification_status\n"
        "pv_cf,ERA5,reanalysis,https://example.com,2024-01-01,2026-08-09,"
        "W/m2,fraction,UTC,pvlib,model," + "a" * 64
        + ",2024-01-01,2024-12-31,high,test,true,verified\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(workbook_builder, "ROOT", tmp_path)

    result = build_workbook(
        annual_csv=annual_path,
        source_registry_csv=source_path,
        output_xlsx=output,
        node_executable=node,
        node_modules=node_modules,
    )

    assert result == output
    assert output.exists() and output.stat().st_size > 0
    preview = output.parent / "annual_data_audit_preview.png"
    assert preview.exists() and preview.stat().st_size > 0
