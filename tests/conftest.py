from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class ManifestProject:
    root: Path
    registered_input: Path
    second_registered_input: Path
    root_workbooks: tuple[Path, Path]
    historical_duplicate: Path


@pytest.fixture
def manifest_project(tmp_path: Path) -> ManifestProject:
    """Create an isolated project whose valid inputs have explicit file names."""

    raw_dir = tmp_path / "data" / "raw"
    processed_dir = tmp_path / "data" / "processed"
    outputs_dir = tmp_path / "outputs"
    raw_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    outputs_dir.mkdir()

    registered_input = raw_dir / "era5_ordos_2024.nc"
    registered_input.write_bytes(b"fresh-era5-input")
    second_registered_input = processed_dir / "annual_inputs_2024.csv"
    second_registered_input.write_text("timestamp,pv_cf\n2024-01-01 00:00,0\n", encoding="utf-8")

    root_workbooks = (tmp_path / "old_input_a.xlsx", tmp_path / "old_input_b.xlsx")
    for workbook in root_workbooks:
        workbook.write_bytes(b"historical-workbook")

    historical_duplicate = outputs_dir / second_registered_input.name
    historical_duplicate.write_text("timestamp,pv_cf\nold,1\n", encoding="utf-8")

    return ManifestProject(
        root=tmp_path,
        registered_input=registered_input,
        second_registered_input=second_registered_input,
        root_workbooks=root_workbooks,
        historical_duplicate=historical_duplicate,
    )
