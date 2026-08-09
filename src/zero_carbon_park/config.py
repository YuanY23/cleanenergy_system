"""Study configuration and immutable run-input manifests.

Formal runs never discover inputs by filename.  A run manifest is created from
an explicit list of files under ``data/raw`` or ``data/processed`` and pins
each file by SHA256 before any model code reads it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Iterable, Mapping

from zero_carbon_park.data.sources import (
    SourceRegistry,
    SourceRegistryValidationError,
    load_source_registry,
)


MANIFEST_SCHEMA_VERSION = 1
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ManifestValidationError(ValueError):
    """Raised when a formal run manifest is incomplete or no longer reproducible."""


@dataclass(frozen=True)
class SolverConfig:
    name: str = "highs"
    time_limit_seconds: int = 3_600
    relative_mip_gap: float = 0.01
    threads: int = 0


@dataclass(frozen=True)
class CapacityBounds:
    """Engineering search envelope sized for the calibrated 450 MW park."""

    pv_mw: tuple[float, float] = (0.0, 1_500.0)
    wind_mw: tuple[float, float] = (0.0, 1_500.0)
    grid_connection_mw: tuple[float, float] = (0.0, 600.0)
    battery_power_mw: tuple[float, float] = (0.0, 600.0)
    battery_energy_mwh: tuple[float, float] = (0.0, 4_800.0)
    electrolyzer_mw: tuple[float, float] = (0.0, 600.0)
    hydrogen_storage_kg: tuple[float, float] = (0.0, 3_000_000.0)
    fuel_cell_mw: tuple[float, float] = (0.0, 600.0)
    heat_pump_mw: tuple[float, float] = (0.0, 600.0)


@dataclass(frozen=True)
class LoadReconstructionConfig:
    """Auditable synthetic-load calibration targets, never SCADA claims."""

    annual_electricity_mwh: float = 3_100_000.0
    peak_electric_load_mw: float = 450.0
    annual_heat_energy_mwh: float = 1_150_000.0
    peak_heat_load_mw_th: float = 270.0
    daily_hydrogen_demand_kg: float = 30_000.0
    hydrogen_interruptible_share: float = 0.30
    heating_balance_temperature_c: float = 18.0
    cooling_balance_temperature_c: float = 24.0
    load_scale_sensitivities: tuple[float, float, float] = (0.5, 1.0, 1.5)
    scale_evidence_source_id: str = "ORDOS_ZERO_CARBON_PARK_SCALE_2025"

    def __post_init__(self) -> None:
        positive = {
            "annual_electricity_mwh": self.annual_electricity_mwh,
            "peak_electric_load_mw": self.peak_electric_load_mw,
            "annual_heat_energy_mwh": self.annual_heat_energy_mwh,
            "peak_heat_load_mw_th": self.peak_heat_load_mw_th,
            "daily_hydrogen_demand_kg": self.daily_hydrogen_demand_kg,
        }
        if any(value <= 0 for value in positive.values()):
            raise ValueError("load calibration targets must be positive")
        if not 0 <= self.hydrogen_interruptible_share <= 1:
            raise ValueError("hydrogen_interruptible_share must be within [0, 1]")
        if not all(scale > 0 for scale in self.load_scale_sensitivities):
            raise ValueError("load scale sensitivities must be positive")


@dataclass(frozen=True)
class StudyConfig:
    study_year: int = 2024
    expected_hours: int = 8_784
    local_timezone: str = "Asia/Shanghai"
    park_peak_electric_load_mw: float = 450.0
    load: LoadReconstructionConfig = field(default_factory=LoadReconstructionConfig)
    capacity_bounds: CapacityBounds = field(default_factory=CapacityBounds)
    solver: SolverConfig = field(default_factory=SolverConfig)


@dataclass(frozen=True)
class ProjectPaths:
    repo_root: Path
    raw_data: Path
    processed_data: Path
    artifacts: Path

    @classmethod
    def from_root(cls, repo_root: str | Path) -> "ProjectPaths":
        root = Path(repo_root).resolve()
        return cls(
            repo_root=root,
            raw_data=root / "data" / "raw",
            processed_data=root / "data" / "processed",
            artifacts=root / "artifacts",
        )

    @property
    def allowed_input_roots(self) -> tuple[Path, Path]:
        return (self.raw_data, self.processed_data)


@dataclass(frozen=True)
class ManifestInput:
    logical_name: str
    path: Path
    source_id: str


@dataclass(frozen=True)
class VerifiedRunManifest:
    manifest_path: Path
    run_id: str
    study_year: int
    git_commit: str
    input_paths: Mapping[str, Path]
    excluded_history_paths: tuple[str, ...]


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return a streaming SHA256 digest for one input file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_run_manifest(
    *,
    repo_root: str | Path,
    inputs: Iterable[ManifestInput],
    run_id: str | None = None,
    study: StudyConfig | None = None,
    git_commit: str | None = None,
) -> Path:
    """Validate explicit inputs and atomically write an immutable run manifest.

    All validation happens before the run directory is created.  This prevents
    a failed preflight from leaving a directory that resembles a valid run.
    """

    paths = ProjectPaths.from_root(repo_root)
    selected_study = study or StudyConfig()
    selected_inputs = tuple(inputs)
    selected_run_id = run_id or _new_run_id()
    _validate_run_id(selected_run_id)

    manifest_inputs = _prepare_inputs(selected_inputs, paths)
    commit = (git_commit or _read_git_commit(paths.repo_root)).strip()
    if not commit:
        raise ManifestValidationError("git_commit must not be empty")

    excluded = _discover_excluded_history(paths, selected_inputs)
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": selected_run_id,
        "study_year": selected_study.study_year,
        "expected_hours": selected_study.expected_hours,
        "local_timezone": selected_study.local_timezone,
        "study_config": asdict(selected_study),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "inputs": manifest_inputs,
        "excluded_history_paths": excluded,
    }

    run_dir = paths.artifacts / "runs" / selected_run_id
    manifest_path = run_dir / "manifest.json"
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ManifestValidationError(
            f"run_id already exists and run directories are immutable: {selected_run_id}"
        ) from exc
    temporary_path = run_dir / ".manifest.json.tmp"
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(manifest_path)
    return manifest_path


def load_verified_manifest(
    manifest_path: str | Path,
    *,
    repo_root: str | Path,
    source_registry: SourceRegistry | None = None,
    verify_git_revision: bool = True,
) -> VerifiedRunManifest:
    """Load a manifest and reject undeclared locations, missing provenance or drift."""

    root_paths = ProjectPaths.from_root(repo_root)
    resolved_manifest = Path(manifest_path).resolve()
    try:
        payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestValidationError(f"cannot read manifest: {resolved_manifest}") from exc

    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestValidationError(
            f"unsupported manifest schema_version: {payload.get('schema_version')!r}"
        )
    run_id = payload.get("run_id")
    _validate_run_id(run_id)
    source_items = payload.get("inputs")
    if not isinstance(source_items, list) or not source_items:
        raise ManifestValidationError("manifest inputs must be a non-empty list")

    registry = source_registry or _load_default_source_registry(root_paths.repo_root)
    try:
        registry.validate_for_formal_run()
    except SourceRegistryValidationError as exc:
        raise ManifestValidationError(f"formal source registry is unresolved: {exc}") from exc
    logical_names: set[str] = set()
    resolved_paths: set[Path] = set()
    verified_paths: dict[str, Path] = {}
    for item in source_items:
        if not isinstance(item, dict):
            raise ManifestValidationError("each manifest input must be an object")
        logical_name = _required_text(item, "logical_name")
        source_id = _required_text(item, "source_id")
        relative_path = _required_text(item, "path")
        expected_hash = _required_text(item, "sha256").lower()
        if not _SHA256_PATTERN.fullmatch(expected_hash):
            raise ManifestValidationError(
                f"invalid SHA256 for input {logical_name!r}: {expected_hash!r}"
            )
        input_path = _resolve_against_root(relative_path, root_paths.repo_root)
        _validate_allowed_input_path(input_path, root_paths)
        if logical_name in logical_names or input_path in resolved_paths:
            raise ManifestValidationError(
                "manifest logical names and resolved input paths must be unique"
            )
        if not input_path.is_file():
            raise ManifestValidationError(f"manifest input does not exist: {input_path}")
        actual_hash = sha256_file(input_path)
        if actual_hash != expected_hash:
            raise ManifestValidationError(
                f"SHA256 mismatch for {logical_name!r}: expected {expected_hash}, "
                f"got {actual_hash}"
            )
        try:
            registry.validate_manifest_input(source_id, expected_hash)
        except SourceRegistryValidationError as exc:
            raise ManifestValidationError(
                f"source provenance failed for {logical_name!r}: {exc}"
            ) from exc
        logical_names.add(logical_name)
        resolved_paths.add(input_path)
        verified_paths[logical_name] = input_path

    git_commit = _required_text(payload, "git_commit")
    if verify_git_revision:
        _validate_git_revision(root_paths.repo_root, git_commit)
    study_year = payload.get("study_year")
    if not isinstance(study_year, int):
        raise ManifestValidationError("study_year must be an integer")
    excluded = payload.get("excluded_history_paths", [])
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        raise ManifestValidationError("excluded_history_paths must be a list of strings")

    return VerifiedRunManifest(
        manifest_path=resolved_manifest,
        run_id=run_id,
        study_year=study_year,
        git_commit=git_commit,
        input_paths=verified_paths,
        excluded_history_paths=tuple(excluded),
    )


def _prepare_inputs(
    inputs: tuple[ManifestInput, ...], paths: ProjectPaths
) -> list[dict[str, str]]:
    if not inputs:
        raise ManifestValidationError("at least one explicit input is required")
    logical_names: set[str] = set()
    resolved_paths: set[Path] = set()
    prepared: list[dict[str, str]] = []
    for item in inputs:
        logical_name = item.logical_name.strip()
        source_id = item.source_id.strip()
        if not logical_name:
            raise ManifestValidationError("input logical_name must not be empty")
        if not source_id:
            raise ManifestValidationError(
                f"source_id must not be empty for input {logical_name!r}"
            )
        input_path = _resolve_against_root(item.path, paths.repo_root)
        _validate_allowed_input_path(input_path, paths)
        if logical_name in logical_names or input_path in resolved_paths:
            raise ManifestValidationError(
                "manifest logical names and resolved input paths must be unique"
            )
        if not input_path.is_file():
            raise ManifestValidationError(f"input does not exist: {input_path}")
        logical_names.add(logical_name)
        resolved_paths.add(input_path)
        prepared.append(
            {
                "logical_name": logical_name,
                "path": input_path.relative_to(paths.repo_root).as_posix(),
                "source_id": source_id,
                "sha256": sha256_file(input_path),
            }
        )
    return prepared


def _validate_allowed_input_path(input_path: Path, paths: ProjectPaths) -> None:
    if not any(
        input_path.is_relative_to(root.resolve()) for root in paths.allowed_input_roots
    ):
        raise ManifestValidationError(
            f"formal inputs must be located under data/raw or data/processed: {input_path}"
        )


def _discover_excluded_history(
    paths: ProjectPaths, declared_inputs: tuple[ManifestInput, ...]
) -> list[str]:
    declared = {
        _resolve_against_root(item.path, paths.repo_root) for item in declared_inputs
    }
    excluded: set[str] = set()
    for pattern in ("*.xlsx", "*.xls", "*.csv"):
        for candidate in paths.repo_root.glob(pattern):
            if candidate.resolve() not in declared:
                excluded.add(candidate.relative_to(paths.repo_root).as_posix())
    for name in ("outputs", "results_v1"):
        candidate = paths.repo_root / name
        if candidate.exists():
            excluded.add(candidate.relative_to(paths.repo_root).as_posix())
    return sorted(excluded)


def _read_git_commit(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ManifestValidationError(
            "git_commit could not be determined; pass it explicitly for a non-git fixture"
        ) from exc
    return completed.stdout.strip()


def _load_default_source_registry(repo_root: Path) -> SourceRegistry:
    registry_path = repo_root / "data" / "metadata" / "source_registry.csv"
    try:
        return load_source_registry(registry_path)
    except SourceRegistryValidationError as exc:
        raise ManifestValidationError(
            f"formal source registry is unavailable or invalid: {registry_path}"
        ) from exc


def _validate_git_revision(repo_root: Path, expected_commit: str) -> None:
    actual_commit = _read_git_commit(repo_root)
    if actual_commit != expected_commit:
        raise ManifestValidationError(
            f"git revision drift: manifest pins {expected_commit}, executing {actual_commit}"
        )
    try:
        completed = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                "src",
                "scripts",
                "pyproject.toml",
                "data/metadata",
            ],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ManifestValidationError("cannot verify formal-run code state") from exc
    if completed.stdout.strip():
        raise ManifestValidationError(
            "formal run requires clean tracked code and metadata at the pinned revision"
        )


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{key} must be a non-empty string")
    return value.strip()


def _validate_run_id(run_id: object) -> None:
    if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ManifestValidationError(
            "run_id must contain only letters, digits, dots, underscores and hyphens"
        )


def _new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _resolve_against_root(path: str | Path, repo_root: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()
