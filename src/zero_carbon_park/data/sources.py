"""Field-level source registry and bounded engineering assumptions.

The checked-in registry is deliberately a *planning registry*: records copied
from the approved study plan may carry ``PENDING_DOWNLOAD`` until the raw
artifact is downloaded.  :meth:`SourceRegistry.validate_for_formal_run` is the
strict publication gate and rejects every unresolved date, hash, or verification
status.  This keeps early provenance honest without inventing file hashes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


PENDING_DOWNLOAD = "PENDING_DOWNLOAD"
PENDING_VERIFICATION = "PENDING_VERIFICATION"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CONFIDENCE_LEVELS = {"high", "medium", "low"}
_VERIFICATION_STATES = {"planned", "verified"}
_NON_TEMPORAL_TIMEZONES = {"N/A", "not_applicable"}

SOURCE_REGISTRY_COLUMNS = (
    "field_name",
    "source_id",
    "source_category",
    "url",
    "published_at",
    "retrieved_at",
    "original_unit",
    "target_unit",
    "timezone",
    "processing_method",
    "conversion_formula",
    "file_sha256",
    "applicable_from",
    "applicable_to",
    "confidence",
    "notes",
    "is_primary",
    "verification_status",
)


class SourceRegistryValidationError(ValueError):
    """Raised when provenance is incomplete, ambiguous, or overstated."""


@dataclass(frozen=True)
class SourceRecord:
    field_name: str
    source_id: str
    source_category: str
    url: str
    published_at: str
    retrieved_at: str
    original_unit: str
    target_unit: str
    timezone: str
    processing_method: str
    conversion_formula: str
    file_sha256: str
    applicable_from: str
    applicable_to: str
    confidence: str
    notes: str
    is_primary: bool
    verification_status: str = "planned"

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> "SourceRecord":
        return cls(
            field_name=row.get("field_name", "").strip(),
            source_id=row.get("source_id", "").strip(),
            source_category=row.get("source_category", "").strip(),
            url=row.get("url", "").strip(),
            published_at=row.get("published_at", "").strip(),
            retrieved_at=row.get("retrieved_at", "").strip(),
            original_unit=row.get("original_unit", "").strip(),
            target_unit=row.get("target_unit", "").strip(),
            timezone=row.get("timezone", "").strip(),
            processing_method=row.get("processing_method", "").strip(),
            conversion_formula=row.get("conversion_formula", "").strip(),
            file_sha256=row.get("file_sha256", "").strip(),
            applicable_from=row.get("applicable_from", "").strip(),
            applicable_to=row.get("applicable_to", "").strip(),
            confidence=row.get("confidence", "").strip().lower(),
            notes=row.get("notes", "").strip(),
            is_primary=_parse_bool(row.get("is_primary", "")),
            verification_status=row.get("verification_status", "").strip().lower(),
        )


@dataclass(frozen=True)
class AssumptionRecord:
    field_name: str
    base_value: float
    lower_bound: float
    upper_bound: float
    unit: str
    source_category: str
    confidence: str
    source_ids: tuple[str, ...]
    rationale: str
    notes: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "AssumptionRecord":
        source_ids = row.get("source_ids", ())
        if isinstance(source_ids, str):
            source_ids = (source_ids,)
        if not isinstance(source_ids, Sequence):
            raise SourceRegistryValidationError("assumption source_ids must be a list")
        try:
            return cls(
                field_name=str(row.get("field_name", "")).strip(),
                base_value=float(row["base_value"]),
                lower_bound=float(row["lower_bound"]),
                upper_bound=float(row["upper_bound"]),
                unit=str(row.get("unit", "")).strip(),
                source_category=str(row.get("source_category", "")).strip(),
                confidence=str(row.get("confidence", "")).strip().lower(),
                source_ids=tuple(str(item).strip() for item in source_ids),
                rationale=str(row.get("rationale", "")).strip(),
                notes=str(row.get("notes", "")).strip(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceRegistryValidationError(
                f"invalid numeric bounds for assumption {row.get('field_name')!r}"
            ) from exc


class SourceRegistry:
    """Validated collection with unambiguous point-in-time primary lookup."""

    def __init__(
        self,
        records: Iterable[SourceRecord],
        *,
        columns: Iterable[str] = SOURCE_REGISTRY_COLUMNS,
    ) -> None:
        self.records = tuple(records)
        self.columns = tuple(columns)
        _validate_registry_columns(self.columns)
        if not self.records:
            raise SourceRegistryValidationError("source registry must not be empty")
        for record in self.records:
            _validate_source_record(record)
        _validate_primary_intervals(self.records)

    @property
    def source_ids(self) -> set[str]:
        return {record.source_id for record in self.records}

    def primary_for(self, field_name: str, *, applicable_on: date) -> SourceRecord:
        candidates = [
            record
            for record in self.records
            if record.field_name == field_name
            and record.is_primary
            and _contains_date(record, applicable_on)
        ]
        if len(candidates) != 1:
            raise SourceRegistryValidationError(
                f"no applicable primary source for {field_name!r} on {applicable_on}"
                if not candidates
                else f"multiple applicable primary sources for {field_name!r}"
            )
        return candidates[0]

    def validate_for_formal_run(self) -> None:
        unresolved = [
            record.source_id
            for record in self.records
            if record.verification_status != "verified"
            or record.file_sha256 == PENDING_DOWNLOAD
            or PENDING_VERIFICATION
            in {record.published_at, record.applicable_from, record.applicable_to}
        ]
        if unresolved:
            joined = ", ".join(sorted(set(unresolved)))
            raise SourceRegistryValidationError(
                f"formal run requires verified dates and downloaded file hashes: {joined}"
            )

    def validate_assumption_sources(
        self, assumptions: Iterable[AssumptionRecord]
    ) -> None:
        unknown = sorted(
            {
                source_id
                for assumption in assumptions
                for source_id in assumption.source_ids
                if source_id not in self.source_ids
            }
        )
        if unknown:
            raise SourceRegistryValidationError(
                f"assumptions reference unknown source_ids: {', '.join(unknown)}"
            )


def load_source_registry(path: str | Path) -> SourceRegistry:
    """Load and validate a UTF-8 CSV registry."""

    registry_path = Path(path)
    try:
        with registry_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = tuple(reader.fieldnames or ())
            records = [SourceRecord.from_mapping(row) for row in reader]
    except OSError as exc:
        raise SourceRegistryValidationError(
            f"cannot read source registry: {registry_path}"
        ) from exc
    return SourceRegistry(records, columns=columns)


def load_assumptions(path: str | Path) -> tuple[AssumptionRecord, ...]:
    """Load the bounded engineering-assumption catalog from YAML."""

    assumption_path = Path(path)
    try:
        payload = yaml.safe_load(assumption_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SourceRegistryValidationError(
            f"cannot read assumptions: {assumption_path}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SourceRegistryValidationError("assumptions schema_version must be 1")
    rows = payload.get("assumptions")
    if not isinstance(rows, list) or not rows:
        raise SourceRegistryValidationError("assumptions must be a non-empty list")
    records = tuple(AssumptionRecord.from_mapping(row) for row in rows)
    validate_assumptions(records)
    return records


def validate_assumptions(assumptions: Iterable[AssumptionRecord]) -> None:
    """Reject missing bounds and any claim that synthetic inputs were measured."""

    records = tuple(assumptions)
    if not records:
        raise SourceRegistryValidationError("assumptions must not be empty")
    seen: set[str] = set()
    for record in records:
        if not record.field_name or record.field_name in seen:
            raise SourceRegistryValidationError(
                "assumption field_name must be non-empty and unique"
            )
        seen.add(record.field_name)
        if record.source_category != "engineering_assumption":
            raise SourceRegistryValidationError(
                f"{record.field_name} must be labelled engineering_assumption, not measured"
            )
        if not all(
            math.isfinite(value)
            for value in (record.lower_bound, record.base_value, record.upper_bound)
        ):
            raise SourceRegistryValidationError(
                f"{record.field_name} bounds must be finite"
            )
        if not record.lower_bound <= record.base_value <= record.upper_bound:
            raise SourceRegistryValidationError(
                f"{record.field_name} requires lower_bound <= base_value <= upper_bound"
            )
        if not record.unit or not record.rationale:
            raise SourceRegistryValidationError(
                f"{record.field_name} requires unit and rationale"
            )
        if record.confidence not in _CONFIDENCE_LEVELS:
            raise SourceRegistryValidationError(
                f"invalid confidence for assumption {record.field_name!r}"
            )
        if not record.source_ids or any(not item for item in record.source_ids):
            raise SourceRegistryValidationError(
                f"{record.field_name} requires at least one source_id"
            )


def _validate_registry_columns(columns: tuple[str, ...]) -> None:
    missing = set(SOURCE_REGISTRY_COLUMNS) - set(columns)
    if missing:
        raise SourceRegistryValidationError(
            f"source registry missing columns: {', '.join(sorted(missing))}"
        )


def _validate_source_record(record: SourceRecord) -> None:
    required = (
        "field_name",
        "source_id",
        "source_category",
        "url",
        "published_at",
        "retrieved_at",
        "original_unit",
        "target_unit",
        "timezone",
        "processing_method",
        "conversion_formula",
        "file_sha256",
        "applicable_from",
        "applicable_to",
        "confidence",
        "notes",
        "verification_status",
    )
    for field_name in required:
        if not str(getattr(record, field_name)).strip():
            raise SourceRegistryValidationError(
                f"{record.source_id or '<unknown>'}: {field_name} must not be empty"
            )
    parsed_url = urlparse(record.url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise SourceRegistryValidationError(
            f"{record.source_id}: url must be an absolute HTTP(S) URL"
        )
    _date_or_pending(record.published_at, "published_at", pending_allowed=True)
    _date_or_pending(record.retrieved_at, "retrieved_at", pending_allowed=False)
    start = _date_or_pending(
        record.applicable_from, "applicable_from", pending_allowed=True
    )
    end = _date_or_pending(record.applicable_to, "applicable_to", pending_allowed=True)
    if start is not None and end is not None and start > end:
        raise SourceRegistryValidationError(
            f"{record.source_id}: applicable_from must not exceed applicable_to"
        )
    if record.timezone not in _NON_TEMPORAL_TIMEZONES:
        try:
            ZoneInfo(record.timezone)
        except ZoneInfoNotFoundError as exc:
            raise SourceRegistryValidationError(
                f"{record.source_id}: timezone is invalid: {record.timezone}"
            ) from exc
    if record.file_sha256 != PENDING_DOWNLOAD and not _SHA256_PATTERN.fullmatch(
        record.file_sha256
    ):
        raise SourceRegistryValidationError(
            f"{record.source_id}: file_sha256 must be 64 lowercase hex characters "
            f"or {PENDING_DOWNLOAD}"
        )
    if record.confidence not in _CONFIDENCE_LEVELS:
        raise SourceRegistryValidationError(
            f"{record.source_id}: invalid confidence {record.confidence!r}"
        )
    if record.verification_status not in _VERIFICATION_STATES:
        raise SourceRegistryValidationError(
            f"{record.source_id}: invalid verification_status"
        )
    if record.verification_status == "verified" and (
        record.file_sha256 == PENDING_DOWNLOAD
        or PENDING_VERIFICATION
        in {record.published_at, record.applicable_from, record.applicable_to}
    ):
        raise SourceRegistryValidationError(
            f"{record.source_id}: verified records cannot contain pending metadata"
        )
    if record.source_category == "engineering_assumption":
        raise SourceRegistryValidationError(
            "engineering assumptions belong in assumptions.yaml with explicit bounds"
        )


def _validate_primary_intervals(records: tuple[SourceRecord, ...]) -> None:
    by_field: dict[str, list[SourceRecord]] = {}
    for record in records:
        if record.is_primary:
            by_field.setdefault(record.field_name, []).append(record)
    for field_name, candidates in by_field.items():
        resolved = [
            record
            for record in candidates
            if PENDING_VERIFICATION
            not in {record.applicable_from, record.applicable_to}
        ]
        ordered = sorted(resolved, key=lambda item: date.fromisoformat(item.applicable_from))
        for left, right in zip(ordered, ordered[1:]):
            left_end = date.fromisoformat(left.applicable_to)
            right_start = date.fromisoformat(right.applicable_from)
            if right_start <= left_end:
                raise SourceRegistryValidationError(
                    f"overlapping primary sources for field {field_name!r}: "
                    f"{left.source_id}, {right.source_id}"
                )


def _contains_date(record: SourceRecord, candidate: date) -> bool:
    if PENDING_VERIFICATION in {record.applicable_from, record.applicable_to}:
        return False
    return (
        date.fromisoformat(record.applicable_from)
        <= candidate
        <= date.fromisoformat(record.applicable_to)
    )


def _date_or_pending(value: str, field_name: str, *, pending_allowed: bool) -> date | None:
    if pending_allowed and value == PENDING_VERIFICATION:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SourceRegistryValidationError(
            f"{field_name} must be an ISO date"
            + (f" or {PENDING_VERIFICATION}" if pending_allowed else "")
        ) from exc


def _parse_bool(value: object) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise SourceRegistryValidationError(f"is_primary must be true or false, got {value!r}")
