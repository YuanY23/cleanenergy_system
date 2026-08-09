from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from zero_carbon_park.data.sources import (
    SOURCE_REGISTRY_COLUMNS,
    AssumptionRecord,
    SourceRecord,
    SourceRegistry,
    SourceRegistryValidationError,
    load_assumptions,
    load_source_registry,
    validate_assumptions,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _record(**overrides: object) -> SourceRecord:
    base = SourceRecord(
        field_name="grid_import_price_cny_per_kwh",
        source_id="MENGXI_TOU_2021",
        source_category="policy",
        url="https://fgw.nmg.gov.cn/example.html",
        published_at="2021-11-24",
        retrieved_at="2026-08-09",
        original_unit="dimensionless multiplier",
        target_unit="dimensionless multiplier",
        timezone="Asia/Shanghai",
        processing_method="Map local hour and month to the published time-of-use band.",
        conversion_formula="base_price * tou_multiplier",
        file_sha256="a" * 64,
        applicable_from="2021-12-01",
        applicable_to="9999-12-31",
        confidence="high",
        notes="Fixture.",
        is_primary=True,
        verification_status="verified",
    )
    return replace(base, **overrides)


def test_checked_in_registry_has_required_schema_and_declared_source_families():
    registry_path = PROJECT_ROOT / "data" / "metadata" / "source_registry.csv"
    registry = load_source_registry(registry_path)

    assert set(SOURCE_REGISTRY_COLUMNS).issubset(registry.columns)
    assert {
        "ERA5_SINGLE_LEVELS_2024",
        "NASA_POWER_HOURLY",
        "GLOBAL_WIND_ATLAS",
        "MENGXI_TOU_2021",
        "NDRC_TRANSMISSION_4TH_2026",
        "ORDOS_GAS_2026",
        "MEE_GRID_FACTOR_2023",
        "NDRC_ZERO_CARBON_METHOD_2025",
        "MEE_NATURAL_GAS_GUIDE",
        "IRENA_COSTS_2024",
        "IEA_HYDROGEN_REVIEW_2025",
        "DOE_PEM_TARGETS",
        "GBT_29328_2018",
        "NEA_RELIABILITY_RULES",
        "KOTZUR_2018",
    }.issubset(registry.source_ids)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"url": ""}, "url"),
        ({"target_unit": ""}, "target_unit"),
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"processing_method": ""}, "processing_method"),
        ({"file_sha256": "not-a-hash"}, "file_sha256"),
    ],
)
def test_source_record_rejects_incomplete_or_invalid_provenance(overrides, message):
    with pytest.raises(SourceRegistryValidationError, match=message):
        SourceRegistry([_record(**overrides)])


def test_policy_lookup_rejects_dates_outside_the_effective_interval():
    registry = SourceRegistry(
        [_record(applicable_from="2026-08-01", applicable_to="2029-12-31")]
    )

    with pytest.raises(SourceRegistryValidationError, match="no applicable primary source"):
        registry.primary_for(
            "grid_import_price_cny_per_kwh", applicable_on=date(2026, 7, 31)
        )


def test_same_field_cannot_have_overlapping_primary_sources():
    with pytest.raises(SourceRegistryValidationError, match="overlapping primary"):
        SourceRegistry(
            [
                _record(source_id="POLICY_A", applicable_to="2026-12-31"),
                _record(
                    source_id="POLICY_B",
                    applicable_from="2026-01-01",
                    applicable_to="2027-12-31",
                ),
            ]
        )


def test_assumptions_have_bounded_values_and_cannot_claim_measurement():
    assumptions = load_assumptions(
        PROJECT_ROOT / "data" / "metadata" / "assumptions.yaml"
    )
    validate_assumptions(assumptions)

    measured = AssumptionRecord(
        field_name="park_peak_electric_load_mw",
        base_value=150.0,
        lower_bound=75.0,
        upper_bound=225.0,
        unit="MW",
        source_category="measured",
        confidence="low",
        source_ids=("MENGXI_TOU_2021",),
        rationale="Synthetic study scale.",
        notes="Fixture.",
    )
    with pytest.raises(SourceRegistryValidationError, match="engineering_assumption"):
        validate_assumptions([measured])


def test_formal_validation_rejects_unresolved_download_hashes():
    registry = SourceRegistry(
        [
            _record(
                file_sha256="PENDING_DOWNLOAD",
                verification_status="planned",
                published_at="PENDING_VERIFICATION",
            )
        ]
    )

    with pytest.raises(SourceRegistryValidationError, match="formal run"):
        registry.validate_for_formal_run()
