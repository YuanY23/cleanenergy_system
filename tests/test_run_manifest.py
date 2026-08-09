from __future__ import annotations

import json
from pathlib import Path

import pytest

from zero_carbon_park.config import (
    ManifestInput,
    ManifestValidationError,
    build_run_manifest,
    load_verified_manifest,
)
from zero_carbon_park.cli import resolve_declared_workbook
from zero_carbon_park.data.sources import SourceRecord, SourceRegistry


def _registry(*entries: tuple[str, Path]) -> SourceRegistry:
    records = []
    for source_id, path in entries:
        records.append(
            SourceRecord(
                field_name=f"input_{source_id}",
                source_id=source_id,
                source_category="test_fixture",
                url="https://example.gov/source",
                published_at="2024-01-01",
                retrieved_at="2026-08-09",
                original_unit="file",
                target_unit="file",
                timezone="N/A",
                processing_method="Copied without modification.",
                conversion_formula="identity",
                file_sha256=__import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                applicable_from="2024-01-01",
                applicable_to="2024-12-31",
                confidence="high",
                notes="Test fixture.",
                is_primary=True,
                verification_status="verified",
            )
        )
    return SourceRegistry(records)


def _inputs(manifest_project) -> list[ManifestInput]:
    return [
        ManifestInput(
            logical_name="era5_hourly",
            path=manifest_project.registered_input,
            source_id="era5-single-levels-2024",
        ),
        ManifestInput(
            logical_name="annual_inputs",
            path=manifest_project.second_registered_input,
            source_id="processed-annual-inputs-v1",
        ),
    ]


def test_manifest_records_only_declared_inputs_and_excludes_history(manifest_project):
    manifest_path = build_run_manifest(
        repo_root=manifest_project.root,
        inputs=_inputs(manifest_project),
        run_id="baseline-2024-test",
        git_commit="0123456789abcdef",
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = load_verified_manifest(
        manifest_path,
        repo_root=manifest_project.root,
        source_registry=_registry(
            ("era5-single-levels-2024", manifest_project.registered_input),
            ("processed-annual-inputs-v1", manifest_project.second_registered_input),
        ),
        verify_git_revision=False,
    )

    assert manifest_path == (
        manifest_project.root
        / "artifacts"
        / "runs"
        / "baseline-2024-test"
        / "manifest.json"
    )
    assert payload["run_id"] == "baseline-2024-test"
    assert payload["study_year"] == 2024
    assert payload["git_commit"] == "0123456789abcdef"
    assert {item["logical_name"] for item in payload["inputs"]} == {
        "era5_hourly",
        "annual_inputs",
    }
    assert all(item["sha256"] for item in payload["inputs"])
    assert all(item["source_id"] for item in payload["inputs"])
    assert verified.input_paths == {
        "era5_hourly": manifest_project.registered_input.resolve(),
        "annual_inputs": manifest_project.second_registered_input.resolve(),
    }

    excluded = set(payload["excluded_history_paths"])
    assert "old_input_a.xlsx" in excluded
    assert "old_input_b.xlsx" in excluded
    assert "outputs" in excluded
    assert manifest_project.historical_duplicate.resolve() not in set(
        verified.input_paths.values()
    )


def test_manifest_rejects_a_missing_source_id(manifest_project):
    with pytest.raises(ManifestValidationError, match="source_id"):
        build_run_manifest(
            repo_root=manifest_project.root,
            inputs=[
                ManifestInput(
                    logical_name="weather",
                    path=manifest_project.registered_input,
                    source_id="",
                )
            ],
            run_id="missing-source",
            git_commit="0123456789abcdef",
        )


def test_manifest_rejects_hash_drift_after_creation(manifest_project):
    manifest_path = build_run_manifest(
        repo_root=manifest_project.root,
        inputs=_inputs(manifest_project),
        run_id="hash-drift",
        git_commit="0123456789abcdef",
    )
    manifest_project.registered_input.write_bytes(b"changed-after-manifest")

    with pytest.raises(ManifestValidationError, match="SHA256"):
        load_verified_manifest(
            manifest_path,
            repo_root=manifest_project.root,
            source_registry=_registry(
                ("era5-single-levels-2024", manifest_project.registered_input),
                ("processed-annual-inputs-v1", manifest_project.second_registered_input),
            ),
            verify_git_revision=False,
        )


@pytest.mark.parametrize("forbidden_location", ["root", "outputs"])
def test_manifest_rejects_inputs_outside_data_layers(
    manifest_project, forbidden_location: str
):
    path: Path
    if forbidden_location == "root":
        path = manifest_project.root_workbooks[0]
    else:
        path = manifest_project.historical_duplicate

    with pytest.raises(ManifestValidationError, match="data/raw|data/processed"):
        build_run_manifest(
            repo_root=manifest_project.root,
            inputs=[
                ManifestInput(
                    logical_name="forbidden",
                    path=path,
                    source_id="should-not-be-readable",
                )
            ],
            run_id=f"forbidden-{forbidden_location}",
            git_commit="0123456789abcdef",
        )


def test_manifest_rejects_duplicate_logical_names(manifest_project):
    with pytest.raises(ManifestValidationError, match="unique"):
        build_run_manifest(
            repo_root=manifest_project.root,
            inputs=[
                ManifestInput(
                    logical_name="weather",
                    path=manifest_project.registered_input,
                    source_id="era5",
                ),
                ManifestInput(
                    logical_name="weather",
                    path=manifest_project.second_registered_input,
                    source_id="processed",
                ),
            ],
            run_id="duplicate-name",
            git_commit="0123456789abcdef",
        )


def test_formal_cli_resolves_only_the_manifest_workbook(manifest_project):
    declared_workbook = manifest_project.root / "data" / "processed" / "model.xlsx"
    declared_workbook.write_bytes(b"declared-workbook")
    manifest_path = build_run_manifest(
        repo_root=manifest_project.root,
        inputs=[
            ManifestInput(
                logical_name="model_workbook",
                path=declared_workbook,
                source_id="processed-model-workbook-v1",
            )
        ],
        run_id="formal-workbook",
        git_commit="0123456789abcdef",
    )

    verified, workbook = resolve_declared_workbook(
        manifest_path,
        repo_root=manifest_project.root,
        source_registry=_registry(
            ("processed-model-workbook-v1", declared_workbook),
        ),
        verify_git_revision=False,
    )

    assert verified.run_id == "formal-workbook"
    assert workbook == declared_workbook.resolve()
    assert workbook not in {path.resolve() for path in manifest_project.root_workbooks}


def test_formal_cli_rejects_manifest_without_declared_workbook(manifest_project):
    manifest_path = build_run_manifest(
        repo_root=manifest_project.root,
        inputs=_inputs(manifest_project),
        run_id="no-workbook",
        git_commit="0123456789abcdef",
    )

    with pytest.raises(ManifestValidationError, match="model_workbook"):
        resolve_declared_workbook(
            manifest_path,
            repo_root=manifest_project.root,
            source_registry=_registry(
                ("era5-single-levels-2024", manifest_project.registered_input),
                ("processed-annual-inputs-v1", manifest_project.second_registered_input),
            ),
            verify_git_revision=False,
        )


def test_manifest_rejects_unknown_or_hash_mismatched_provenance(manifest_project):
    manifest_path = build_run_manifest(
        repo_root=manifest_project.root,
        inputs=_inputs(manifest_project),
        run_id="provenance-gate",
        git_commit="0123456789abcdef",
    )
    incomplete_registry = _registry(
        ("era5-single-levels-2024", manifest_project.registered_input),
    )

    with pytest.raises(ManifestValidationError, match="processed-annual-inputs-v1"):
        load_verified_manifest(
            manifest_path,
            repo_root=manifest_project.root,
            source_registry=incomplete_registry,
            verify_git_revision=False,
        )


def test_manifest_rejects_stale_code_revision(manifest_project, monkeypatch):
    manifest_path = build_run_manifest(
        repo_root=manifest_project.root,
        inputs=_inputs(manifest_project),
        run_id="stale-code",
        git_commit="expected-commit",
    )
    monkeypatch.setattr(
        "zero_carbon_park.config._read_git_commit", lambda _root: "different-commit"
    )

    with pytest.raises(ManifestValidationError, match="git revision"):
        load_verified_manifest(
            manifest_path,
            repo_root=manifest_project.root,
            source_registry=_registry(
                ("era5-single-levels-2024", manifest_project.registered_input),
                ("processed-annual-inputs-v1", manifest_project.second_registered_input),
            ),
        )


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--output", "somewhere-else"],
        ["--run-typical-days"],
    ],
)
def test_formal_cli_cannot_route_manifest_into_legacy_outputs(
    monkeypatch, extra_args: list[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv", ["zero-carbon-park", "--manifest", "missing.json", *extra_args]
    )

    from zero_carbon_park.cli import main

    with pytest.raises(ManifestValidationError, match="formal manifest mode"):
        main()
