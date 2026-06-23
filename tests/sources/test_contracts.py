"""Phase B — Source contracts tests.

The contracts in ``leaders_db.sources.contracts`` are the public
dataclass surface every adapter must populate. Phase A ships the
shapes; Phase B tests assert the documented fields exist and the
documents the runtime invariants the adapter population must respect.

Coverage:

- ``SourceIngestRequest`` exposes the documented fields, including
  ``years=None`` "all-years" semantics, the default ``output_formats``
  ``("parquet",)``, and the default ``cache_policy`` ``"prefer_cache"``.
- ``NormalizedObservation`` carries source id, observation id, family,
  indicator code, value + value type, source version, raw/transform
  locators, quality flags, warnings, and an extension mapping.
- ``RawAsset`` and ``RawLocator`` are immutable, carry an asset id,
  source id, media type, path or URL, version, retrieval timestamp,
  and checksum where applicable.
- ``TransformLocator`` carries adapter/transform/catalog/rule keys.
- ``SourceAttribution`` carries the canonical citation and license.
- ``SourceManifest`` includes request summary, run id, source version,
  raw assets, output assets, observation count, coverage, warnings,
  attribution, adapter version, content hash, idempotency key.
- ``SourceWarning`` is a structured record with code, message, severity,
  source id, and context mapping.
- ``CoverageHint`` declares start/end year, country/leader tuples, and
  notes.

PASS-ELIGIBLE rationale
-----------------------
All tests in this file are PASS-ELIGIBLE: the dataclasses already
ship with the documented fields. The tests are guard-rails against
accidental field removal; they fail loudly if a refactor drops a
required field. They also encode the "default output format is
parquet, default cache policy is ``prefer_cache``" rule that the
runner depends on.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path
from typing import get_args

import pytest

# ---------------------------------------------------------------------------
# SourceIngestRequest shape
# ---------------------------------------------------------------------------


def test_ingest_request_exposes_all_documented_fields() -> None:
    """``SourceIngestRequest`` has every documented field.

    Contract (docs/architecture/sources.md §5.3, SRC-REQ-002):
    source id, years, countries, leaders, raw_root, processed_root,
    metadata_root, db_url, db_session, source_version, run_id,
    dry_run, overwrite, cache_policy, output_formats.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceIngestRequest

    expected = {
        "source_id",
        "years",
        "countries",
        "leaders",
        "raw_root",
        "processed_root",
        "metadata_root",
        "db_url",
        "db_session",
        "source_version",
        "run_id",
        "dry_run",
        "overwrite",
        "cache_policy",
        "output_formats",
    }
    actual = {f.name for f in dataclasses.fields(SourceIngestRequest)}
    assert expected.issubset(actual), (
        f"missing fields: {expected - actual}"
    )


def test_ingest_request_years_none_is_preserved_as_all_years() -> None:
    """``years=None`` is preserved as the "all available years" sentinel.

    SRC-REQ-003: ``years=None`` MUST mean "all available years", not
    "current year". The dataclass is ``frozen=True`` so it stores
    ``None`` directly; the runner is responsible for interpreting it.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(source_id=SourceId(slug="x"), years=None)
    assert request.years is None


def test_ingest_request_default_output_format_is_parquet() -> None:
    """The default ``output_formats`` is the parquet tuple.

    SRC-DEFAULT-002: parquet is canonical; CSV is optional/audit-friendly.
    The default tuple contains exactly ``("parquet",)``.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(source_id=SourceId(slug="x"))
    assert request.output_formats == ("parquet",)


def test_ingest_request_default_cache_policy_is_prefer_cache() -> None:
    """The default ``cache_policy`` is ``"prefer_cache"``.

    Per docs/architecture/sources.md §5.3, ``prefer_cache`` is the
    network-friendly default; adapters must obey it.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(source_id=SourceId(slug="x"))
    assert request.cache_policy == "prefer_cache"


def test_ingest_request_default_dry_run_and_overwrite_are_false() -> None:
    """``dry_run`` and ``overwrite`` default to ``False``.

    SRC-REQ-007: dry-run must not mutate; ``False`` is the safe
    default. ``overwrite=False`` protects existing processed outputs.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(source_id=SourceId(slug="x"))
    assert request.dry_run is False
    assert request.overwrite is False


def test_ingest_request_roots_default_to_documented_paths() -> None:
    """``raw_root`` / ``processed_root`` / ``metadata_root`` default to the
    data-lake folder layout.

    The dataclass defaults match the documented layout in
    docs/architecture/local-data-store.md.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(source_id=SourceId(slug="x"))
    assert request.raw_root == Path("data/raw")
    assert request.processed_root == Path("data/processed")
    assert request.metadata_root == Path("data/metadata")


def test_ingest_request_years_tuple_preserves_order() -> None:
    """Explicit ``years`` tuples round-trip unchanged.

    The dataclass is frozen; ordering is the caller's responsibility.
    The test pins the round-trip so the runner can rely on
    ``request.years`` for filter emission.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(
        source_id=SourceId(slug="x"), years=(2020, 2021, 2022),
    )
    assert request.years == (2020, 2021, 2022)


def test_ingest_request_db_url_and_db_session_roundtrip() -> None:
    """``db_url`` and ``db_session`` both round-trip.

    SRC-REQ-002: the request carries both a URL and a session so
    adapter code can use either.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    sentinel_session = object()
    request = SourceIngestRequest(
        source_id=SourceId(slug="x"),
        db_url="sqlite:///fake.db",
        db_session=sentinel_session,
    )
    assert request.db_url == "sqlite:///fake.db"
    assert request.db_session is sentinel_session


def test_ingest_request_run_id_and_source_version_roundtrip() -> None:
    """``run_id`` and ``source_version`` round-trip unchanged."""
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(
        source_id=SourceId(slug="x"),
        run_id="run-2023-01-01",
        source_version="v2.1",
    )
    assert request.run_id == "run-2023-01-01"
    assert request.source_version == "v2.1"


def test_ingest_request_countries_and_leaders_roundtrip() -> None:
    """``countries`` and ``leaders`` carry the requested filter tuples."""
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(
        source_id=SourceId(slug="x"),
        countries=("USA", "MEX"),
        leaders=("leader-1",),
    )
    assert request.countries == ("USA", "MEX")
    assert request.leaders == ("leader-1",)


def test_ingest_request_cache_policy_accepts_documented_values() -> None:
    """The four documented cache policies are accepted by the dataclass.

    ``offline_only``, ``prefer_cache``, ``refresh``, ``no_cache`` are
    the four documented values (docs/architecture/sources.md §5.3).

    PASS-ELIGIBLE (Phase A dataclass uses a TypeAlias; the test
    confirms every documented value can be constructed).
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    for policy in ("offline_only", "prefer_cache", "refresh", "no_cache"):
        request = SourceIngestRequest(
            source_id=SourceId(slug="x"), cache_policy=policy,
        )
        assert request.cache_policy == policy


def test_ingest_request_output_formats_accept_documented_values() -> None:
    """``output_formats`` accepts the documented ``parquet`` / ``csv``
    values, in any combination.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    for combo in (("parquet",), ("csv",), ("parquet", "csv")):
        request = SourceIngestRequest(
            source_id=SourceId(slug="x"), output_formats=combo,
        )
        assert request.output_formats == combo


def test_ingest_request_cache_policy_literal_alias_enumerates_documented_values() -> None:
    """The ``cache_policy`` ``Literal`` alias enumerates exactly the four documented values.

    docs/architecture/sources.md §5.3 and the ``contracts.CachePolicy``
    ``TypeAlias`` define the four values ``offline_only``,
    ``prefer_cache``, ``refresh``, ``no_cache``. The runtime dataclass
    does NOT enforce this alias (a ``str`` is accepted at construction
    time), so request validity is the runner's responsibility rather
    than the dataclass's. This test pins the alias content so a future
    refactor cannot silently drop or rename a literal value.

    PASS-ELIGIBLE: the alias is a static type contract, not a runtime
    validation contract.
    """
    from leaders_db.sources import contracts as _contracts

    expected = {"offline_only", "prefer_cache", "refresh", "no_cache"}
    actual = set(get_args(_contracts.CachePolicy))
    assert actual == expected, (
        f"CachePolicy alias must enumerate exactly {expected}, got {actual}"
    )


def test_ingest_request_output_format_literal_alias_enumerates_documented_values() -> None:
    """The ``OutputFormat`` ``Literal`` alias enumerates exactly the two documented values.

    docs/architecture/sources.md §5.3 and the ``contracts.OutputFormat``
    ``TypeAlias`` define the two values ``parquet`` and ``csv``. The
    runtime dataclass does NOT enforce this alias; request validity is
    the runner's responsibility. The test pins the alias content so a
    future refactor cannot silently drop or rename a literal value.

    PASS-ELIGIBLE: the alias is a static type contract, not a runtime
    validation contract.
    """
    from leaders_db.sources import contracts as _contracts

    expected = {"parquet", "csv"}
    actual = set(get_args(_contracts.OutputFormat))
    assert actual == expected, (
        f"OutputFormat alias must enumerate exactly {expected}, got {actual}"
    )


# ---------------------------------------------------------------------------
# SourceDescriptor shape
# ---------------------------------------------------------------------------


def test_descriptor_carries_documented_fields() -> None:
    """``SourceDescriptor`` exposes every documented field.

    SRC-ID-003 / docs/architecture/sources.md §5.2.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceDescriptor

    expected = {
        "source_id",
        "display_name",
        "source_type",
        "supported_observation_families",
        "default_version",
        "homepage_url",
        "attribution_key",
        "coverage_hint",
        "requires_manual_approval",
        "requires_network",
    }
    actual = {f.name for f in dataclasses.fields(SourceDescriptor)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


def test_descriptor_source_type_accepts_documented_values() -> None:
    """``source_type`` accepts every documented literal.

    docs/architecture/sources.md §5.2 enumerates the seven types.

    PASS-ELIGIBLE.
    """
    expected_types = {
        "dataset",
        "api",
        "manual",
        "derived",
        "document",
        "knowledge_base",
        "validation_only",
    }
    # The runtime TypeAlias resolves through the contracts module.
    from leaders_db.sources import contracts as _contracts

    actual_types = set(get_args(_contracts.SourceType))
    assert expected_types.issubset(actual_types), (
        f"missing source_type values: {expected_types - actual_types}"
    )


def test_descriptor_with_coverage_hint_stores_all_documented_fields() -> None:
    """``CoverageHint`` exposes the documented fields.

    SRC-COV-001: every source declares a coverage hint.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import CoverageHint

    expected = {"start_year", "end_year", "countries", "leaders", "notes"}
    actual = {f.name for f in dataclasses.fields(CoverageHint)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


# ---------------------------------------------------------------------------
# NormalizedObservation shape
# ---------------------------------------------------------------------------


def _make_observation(**overrides):  # type: ignore[no-untyped-def]
    """Build a minimal valid ``NormalizedObservation`` for shape tests."""
    from leaders_db.sources import (
        NormalizedObservation,
        RawLocator,
        SourceId,
        TransformLocator,
    )

    fields = {
        "source_id": SourceId(slug="obs_source"),
        "observation_id": "obs-1",
        "observation_family": "test_family",
        "indicator_code": "test_ind",
        "value": 1,
        "value_type": "numeric",
        "year": 2023,
        "country_code": "USA",
        "country_name": None,
        "leader_id": None,
        "leader_name": None,
        "unit": None,
        "scale": None,
        "source_version": None,
        "raw_locator": RawLocator(asset_id="asset-1"),
        "transform_locator": TransformLocator(),
        "quality_flags": (),
        "warnings": (),
        "extension": {},
    }
    fields.update(overrides)
    return NormalizedObservation(**fields)


def test_normalized_observation_carries_documented_fields() -> None:
    """``NormalizedObservation`` has the documented field set.

    SRC-OBS-002 / docs/architecture/sources.md §5.5.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import NormalizedObservation

    expected = {
        "source_id",
        "observation_id",
        "observation_family",
        "indicator_code",
        "value",
        "value_type",
        "year",
        "country_code",
        "country_name",
        "leader_id",
        "leader_name",
        "unit",
        "scale",
        "source_version",
        "raw_locator",
        "transform_locator",
        "quality_flags",
        "warnings",
        "extension",
    }
    actual = {f.name for f in dataclasses.fields(NormalizedObservation)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


def test_normalized_observation_carries_provenance_locators() -> None:
    """The raw and transform locators round-trip through the observation.

    SRC-PROV-001: every observation is traceable via a raw locator and
    a transform locator.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import RawLocator, TransformLocator

    observation = _make_observation(
        raw_locator=RawLocator(
            asset_id="asset-42",
            path="sheet1.csv",
            row_number=7,
            column_name="gdp",
        ),
        transform_locator=TransformLocator(
            adapter_version="v1",
            transform_name="row_to_obs",
            catalog_key="gdp_pc",
            rule_id="R-001",
        ),
    )
    assert observation.raw_locator.asset_id == "asset-42"
    assert observation.raw_locator.row_number == 7
    assert observation.raw_locator.column_name == "gdp"
    assert observation.transform_locator.adapter_version == "v1"
    assert observation.transform_locator.rule_id == "R-001"


def test_normalized_observation_carries_quality_flags_and_warnings() -> None:
    """Quality flags and warnings are tuple-typed and round-trip."""
    from leaders_db.sources import SourceWarning

    warning = SourceWarning(code="country_absent", message="missing")
    observation = _make_observation(
        quality_flags=("stale_year_proxy",),
        warnings=(warning,),
    )
    assert observation.quality_flags == ("stale_year_proxy",)
    assert observation.warnings == (warning,)


def test_normalized_observation_extension_is_a_mapping() -> None:
    """``extension`` is a mapping carrying source-specific structured data.

    SRC-OBS-005: source-specific extension fields are structured and
    documented per source.

    PASS-ELIGIBLE.
    """
    observation = _make_observation(extension={"confidence_band": "high"})
    assert observation.extension["confidence_band"] == "high"


def test_normalized_observation_is_immutable() -> None:
    """``NormalizedObservation`` is frozen; mutation raises ``FrozenInstanceError``."""
    observation = _make_observation()
    with pytest.raises(dataclasses.FrozenInstanceError):
        observation.value = 99  # type: ignore[misc]


def test_normalized_observation_value_type_accepts_documented_literals() -> None:
    """``value_type`` accepts the six documented values.

    docs/architecture/sources.md §5.5 enumerates the six literals.

    PASS-ELIGIBLE.
    """
    expected = {"numeric", "categorical", "text", "boolean", "json", "missing"}
    from leaders_db.sources import contracts as _contracts

    actual = set(get_args(_contracts.ObservationValueType))
    assert expected.issubset(actual), (
        f"missing value_type values: {expected - actual}"
    )


# ---------------------------------------------------------------------------
# RawAsset, RawLocator, TransformLocator shapes
# ---------------------------------------------------------------------------


def test_raw_asset_carries_documented_fields() -> None:
    """``RawAsset`` exposes the documented fields.

    SRC-PROV-002: asset id, source id, media type, path/URL, source
    version, retrieval timestamp, checksum where available.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import RawAsset

    expected = {
        "asset_id",
        "source_id",
        "version",
        "media_type",
        "path",
        "url",
        "checksum_sha256",
        "retrieved_at",
        "immutable",
    }
    actual = {f.name for f in dataclasses.fields(RawAsset)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


def test_raw_asset_defaults_immutable_true() -> None:
    """``RawAsset.immutable`` defaults to ``True`` (SRC-PROV-003)."""
    from leaders_db.sources import RawAsset, SourceId

    asset = RawAsset(
        asset_id="a1",
        source_id=SourceId(slug="x"),
        version="v1",
        media_type="text/csv",
        path=Path("/data/raw/x/file.csv"),
    )
    assert asset.immutable is True


def test_raw_asset_with_path_url_checksum_timestamp() -> None:
    """``RawAsset`` round-trips path, URL, checksum, and retrieval timestamp."""
    from leaders_db.sources import RawAsset, SourceId

    asset = RawAsset(
        asset_id="a1",
        source_id=SourceId(slug="x"),
        version="v1",
        media_type="text/csv",
        path=Path("/data/raw/x/file.csv"),
        url="https://example.org/file.csv",
        checksum_sha256="abc123",
        retrieved_at=datetime(2023, 6, 1, 12, 0, 0),
    )
    assert asset.path == Path("/data/raw/x/file.csv")
    assert str(asset.url) == "https://example.org/file.csv"
    assert asset.checksum_sha256 == "abc123"
    assert asset.retrieved_at == datetime(2023, 6, 1, 12, 0, 0)


def test_raw_locator_carries_documented_fields() -> None:
    """``RawLocator`` exposes every documented locator field.

    SRC-PROV-001: path, URL, sheet, row, column, page, HTML selector,
    JSON pointer, API endpoint + params hash.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import RawLocator

    expected = {
        "asset_id",
        "path",
        "url",
        "sheet",
        "row_number",
        "column_name",
        "page_number",
        "html_selector",
        "json_pointer",
        "api_endpoint",
        "api_params_hash",
    }
    actual = {f.name for f in dataclasses.fields(RawLocator)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


def test_raw_locator_round_trips_documented_pointer_fields() -> None:
    """Every RawLocator pointer field round-trips through construction."""
    from leaders_db.sources import RawLocator

    locator = RawLocator(
        asset_id="a1",
        path="sheet1.csv",
        url="https://example.org/x",
        sheet="Sheet1",
        row_number=42,
        column_name="gdp_per_capita",
        page_number=3,
        html_selector="table.data tr:nth-of-type(2)",
        json_pointer="/rows/3/gdp",
        api_endpoint="/v1/observations",
        api_params_hash="deadbeef",
    )
    assert locator.asset_id == "a1"
    assert locator.sheet == "Sheet1"
    assert locator.row_number == 42
    assert locator.column_name == "gdp_per_capita"
    assert locator.page_number == 3
    assert locator.html_selector == "table.data tr:nth-of-type(2)"
    assert locator.json_pointer == "/rows/3/gdp"
    assert locator.api_endpoint == "/v1/observations"
    assert locator.api_params_hash == "deadbeef"


def test_transform_locator_carries_documented_fields() -> None:
    """``TransformLocator`` exposes the documented fields."""
    from leaders_db.sources import TransformLocator

    expected = {"adapter_version", "transform_name", "catalog_key", "rule_id"}
    actual = {f.name for f in dataclasses.fields(TransformLocator)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


# ---------------------------------------------------------------------------
# SourceManifest shape
# ---------------------------------------------------------------------------


def test_source_manifest_carries_documented_fields() -> None:
    """``SourceManifest`` exposes the documented manifest fields.

    SRC-PERSIST-004 / docs/architecture/sources.md §5.6.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceManifest

    expected = {
        "source_id",
        "run_id",
        "request",
        "source_version",
        "raw_assets",
        "output_assets",
        "observation_count",
        "coverage",
        "warnings",
        "attribution",
        "adapter_version",
        "content_hash",
        "idempotency_key",
    }
    actual = {f.name for f in dataclasses.fields(SourceManifest)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


def test_source_manifest_round_trips_request_run_id_and_assets() -> None:
    """Manifest round-trips run id, request reference, raw and output assets."""
    from leaders_db.sources import (
        RawAsset,
        SourceId,
        SourceIngestRequest,
        SourceManifest,
    )

    request = SourceIngestRequest(source_id=SourceId(slug="x"), run_id="r-1")
    raw = RawAsset(
        asset_id="a", source_id=request.source_id, version="v1",
        media_type="text/csv", path=Path("/data/raw/x/file.csv"),
    )
    manifest = SourceManifest(
        source_id=request.source_id,
        run_id="r-1",
        request=request,
        source_version="v1",
        raw_assets=(raw,),
        observation_count=0,
    )
    assert manifest.run_id == "r-1"
    assert manifest.request is request
    assert manifest.raw_assets == (raw,)
    assert manifest.observation_count == 0
    assert manifest.coverage == {}


# ---------------------------------------------------------------------------
# SourceAttribution shape
# ---------------------------------------------------------------------------


def test_source_attribution_carries_documented_fields() -> None:
    """``SourceAttribution`` exposes the documented fields.

    SRC-PROV-005: machine-readable normative attribution registry.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceAttribution

    expected = {
        "attribution_key",
        "source_id",
        "text",
        "citation_url",
        "license_name",
    }
    actual = {f.name for f in dataclasses.fields(SourceAttribution)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


def test_source_attribution_round_trips_citation_and_license() -> None:
    """Attribution round-trips citation URL and license name."""
    from leaders_db.sources import SourceAttribution, SourceId

    attribution = SourceAttribution(
        attribution_key="pwt",
        source_id=SourceId(slug="pwt"),
        text="Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015).",
        citation_url="https://doi.org/10.15141/S5Q94M1178873",
        license_name="CC-BY 4.0",
    )
    assert attribution.attribution_key == "pwt"
    assert attribution.license_name == "CC-BY 4.0"
    assert attribution.citation_url == "https://doi.org/10.15141/S5Q94M1178873"
    assert "Feenstra" in attribution.text


# ---------------------------------------------------------------------------
# SourceWarning shape
# ---------------------------------------------------------------------------


def test_source_warning_carries_documented_fields() -> None:
    """``SourceWarning`` exposes the documented fields.

    docs/architecture/sources.md §5.3 / SRC-COV-005.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceWarning

    expected = {"code", "message", "severity", "source_id", "context"}
    actual = {f.name for f in dataclasses.fields(SourceWarning)}
    assert expected.issubset(actual), f"missing fields: {expected - actual}"


def test_source_warning_default_severity_is_warning() -> None:
    """Default ``severity`` is ``"warning"``."""
    from leaders_db.sources import SourceWarning

    warning = SourceWarning(code="country_absent", message="missing")
    assert warning.severity == "warning"


def test_source_warning_accepts_severity_literals() -> None:
    """``severity`` accepts the three documented values.

    docs/architecture/sources.md §5.3 enumerates ``info`` /
    ``warning`` / ``error``.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceWarning

    for severity in ("info", "warning", "error"):
        warning = SourceWarning(
            code="x", message="m", severity=severity,
        )
        assert warning.severity == severity


def test_source_warning_carries_source_id_and_context() -> None:
    """Warnings carry source id and a context mapping for machine parsing."""
    from leaders_db.sources import SourceId, SourceWarning

    warning = SourceWarning(
        code="year_absent",
        message="year 1990 not in coverage",
        severity="warning",
        source_id=SourceId(slug="pwt"),
        context={"year": 1990, "coverage_end": 2019},
    )
    assert warning.source_id == SourceId(slug="pwt")
    assert warning.context == {"year": 1990, "coverage_end": 2019}


# ---------------------------------------------------------------------------
# Frozen / immutability invariants
# ---------------------------------------------------------------------------


def test_ingest_request_is_frozen() -> None:
    """``SourceIngestRequest`` is immutable.

    Mutation raises ``FrozenInstanceError``; this protects request
    provenance across runner dispatch.
    """
    from leaders_db.sources import SourceId, SourceIngestRequest

    request = SourceIngestRequest(source_id=SourceId(slug="x"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.run_id = "mutated"  # type: ignore[misc]


def test_raw_asset_is_frozen() -> None:
    """``RawAsset`` is immutable (raw provenance must not change post-capture)."""
    from leaders_db.sources import RawAsset, SourceId

    asset = RawAsset(
        asset_id="a", source_id=SourceId(slug="x"), version="v1",
        media_type="text/csv", path=Path("/data/raw/x/file.csv"),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        asset.asset_id = "mutated"  # type: ignore[misc]


def test_source_manifest_is_frozen() -> None:
    """``SourceManifest`` is immutable (run record must not change post-write)."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
        SourceManifest,
    )

    manifest = SourceManifest(
        source_id=SourceId(slug="x"),
        run_id="r-1",
        request=SourceIngestRequest(source_id=SourceId(slug="x")),
        source_version=None,
        raw_assets=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.run_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Warning-code constants
# ---------------------------------------------------------------------------


def test_warning_code_constants_match_documented_codes() -> None:
    """``leaders_db.sources.warnings`` exposes the documented missingness codes.

    SRC-COV-005 enumerates the codes; the test pins them so a future
    refactor cannot silently drop a constant.
    """
    from leaders_db.sources import warnings as w

    expected = {
        "MISSING_RAW",
        "MISSING_METADATA",
        "COUNTRY_ABSENT",
        "YEAR_ABSENT",
        "INDICATOR_NULL",
        "UNSUPPORTED_FILTER",
        "MANUAL_GATE",
        "NETWORK_CACHE_UNAVAILABLE",
        "SOURCE_NOT_IMPLEMENTED",
    }
    actual = set(dir(w))
    assert expected.issubset(actual), f"missing codes: {expected - actual}"


__all__ = [
    "_make_observation",
    "test_descriptor_carries_documented_fields",
    "test_descriptor_source_type_accepts_documented_values",
    "test_descriptor_with_coverage_hint_stores_all_documented_fields",
    "test_ingest_request_cache_policy_accepts_documented_values",
    "test_ingest_request_cache_policy_literal_alias_enumerates_documented_values",
    "test_ingest_request_countries_and_leaders_roundtrip",
    "test_ingest_request_db_url_and_db_session_roundtrip",
    "test_ingest_request_default_cache_policy_is_prefer_cache",
    "test_ingest_request_default_dry_run_and_overwrite_are_false",
    "test_ingest_request_default_output_format_is_parquet",
    "test_ingest_request_exposes_all_documented_fields",
    "test_ingest_request_output_format_literal_alias_enumerates_documented_values",
    "test_ingest_request_output_formats_accept_documented_values",
    "test_ingest_request_roots_default_to_documented_paths",
    "test_ingest_request_run_id_and_source_version_roundtrip",
    "test_ingest_request_years_none_is_preserved_as_all_years",
    "test_ingest_request_years_tuple_preserves_order",
    "test_normalized_observation_carries_documented_fields",
    "test_normalized_observation_carries_provenance_locators",
    "test_normalized_observation_carries_quality_flags_and_warnings",
    "test_normalized_observation_extension_is_a_mapping",
    "test_normalized_observation_is_immutable",
    "test_normalized_observation_value_type_accepts_documented_literals",
    "test_raw_asset_carries_documented_fields",
    "test_raw_asset_defaults_immutable_true",
    "test_raw_asset_is_frozen",
    "test_raw_asset_with_path_url_checksum_timestamp",
    "test_raw_locator_carries_documented_fields",
    "test_raw_locator_round_trips_documented_pointer_fields",
    "test_source_attribution_carries_documented_fields",
    "test_source_attribution_round_trips_citation_and_license",
    "test_source_manifest_carries_documented_fields",
    "test_source_manifest_is_frozen",
    "test_source_manifest_round_trips_request_run_id_and_assets",
    "test_source_warning_accepts_severity_literals",
    "test_source_warning_carries_documented_fields",
    "test_source_warning_carries_source_id_and_context",
    "test_source_warning_default_severity_is_warning",
    "test_transform_locator_carries_documented_fields",
    "test_warning_code_constants_match_documented_codes",
]
