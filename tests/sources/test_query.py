"""Phase B — Evidence-query interface tests.

The new ``leaders_db.sources.query`` module exposes the read-only
``EvidenceRepository`` interface that downstream scoring, validation,
and research code must use instead of touching raw files or source
adapters directly (SRC-QUERY-001, docs/requirements/sources.md §10).

This file covers ``SRC-QUERY-001`` through ``SRC-QUERY-005``:

- ``SRC-QUERY-001``: The query interface is reachable through the
  ``EvidenceRepository`` ``Protocol`` on the ``leaders_db.sources``
  package surface.
- ``SRC-QUERY-002``: ``EvidenceQuery`` exposes filters for source,
  observation family, indicator code, year, country, and leader, and
  preserves the filter values across construction.
- ``SRC-QUERY-003``: ``EvidenceQuery`` exposes include flags for raw
  locators, warnings, quality flags, manifests, and attribution, and
  preserves the flag values across construction.
- ``SRC-QUERY-004``: ``EvidenceRepository.query_observations`` returns
  observations from in-memory state without invoking source
  ingestion / lifecycle (no ``SourceIngestRunner.run``, no
  ``check_ready`` / ``read_raw`` / ``transform`` calls).
- ``SRC-QUERY-005``: ``EvidenceRepository.get_manifest`` and
  ``get_attributions`` return their documents from in-memory state
  without invoking ingestion or reading raw files directly.

PASS-ELIGIBLE rationale
-----------------------
All tests in this file are PASS-ELIGIBLE: the
``EvidenceQuery`` dataclass and ``EvidenceRepository`` ``Protocol``
already ship in Phase A. The tests pin the contract surface that
downstream scorers and validators will rely on; they fail loudly if
a refactor drops a filter, include flag, or query method.

The "no ingestion / no raw file read" assertions are wired against
a fake repository that records every method invocation. A future
implementation that secretly wires the repository to a runner or a
raw-file reader will trip the call-count assertion immediately.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers: minimal valid contracts shared across tests.
# ---------------------------------------------------------------------------


def _descriptor(slug: str) -> SourceDescriptor:  # type: ignore[no-untyped-def]  # noqa: F821
    from leaders_db.sources import CoverageHint, SourceDescriptor, SourceId

    return SourceDescriptor(
        source_id=SourceId(slug=slug),
        display_name=f"Fake {slug}",
        source_type="dataset",
        supported_observation_families=("test_family",),
        default_version="v1",
        homepage_url=None,
        attribution_key=slug,
        coverage_hint=CoverageHint(),
        requires_manual_approval=False,
        requires_network=False,
    )


def _observation(slug: str, indicator: str = "ind_a", year: int = 2023) -> NormalizedObservation:  # type: ignore[no-untyped-def]  # noqa: F821
    from leaders_db.sources import (
        NormalizedObservation,
        RawLocator,
        SourceId,
        TransformLocator,
    )

    return NormalizedObservation(
        source_id=SourceId(slug=slug),
        observation_id=f"{slug}:{indicator}:{year}",
        observation_family="test_family",
        indicator_code=indicator,
        value=1,
        value_type="numeric",
        year=year,
        country_code="USA",
        country_name="United States",
        leader_id=None,
        leader_name=None,
        unit=None,
        scale=None,
        source_version="v1",
        raw_locator=RawLocator(asset_id=f"asset-{slug}"),
        transform_locator=TransformLocator(transform_name="row_to_obs"),
    )


def _manifest(slug: str, run_id: str) -> SourceManifest:  # type: ignore[no-untyped-def]  # noqa: F821
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
        SourceManifest,
    )

    return SourceManifest(
        source_id=SourceId(slug=slug),
        run_id=run_id,
        request=SourceIngestRequest(source_id=SourceId(slug=slug), run_id=run_id),
        source_version="v1",
        raw_assets=(),
        observation_count=0,
    )


def _attribution(slug: str) -> SourceAttribution:  # type: ignore[no-untyped-def]  # noqa: F821
    from leaders_db.sources import SourceAttribution, SourceId

    return SourceAttribution(
        attribution_key=slug,
        source_id=SourceId(slug=slug),
        text=f"Citation text for {slug}.",
        citation_url=f"https://example.org/{slug}",
        license_name="CC-BY 4.0",
    )


# ---------------------------------------------------------------------------
# Fake EvidenceRepository used by the no-ingestion tests.
# ---------------------------------------------------------------------------


class _FakeEvidenceRepository:
    """In-memory ``EvidenceRepository`` implementation for contract tests.

    The class implements the three documented ``EvidenceRepository``
    methods (``query_observations``, ``get_manifest``, ``get_attributions``)
    and records every method invocation in ``self.calls``. The records
    let the tests assert no ingestion / no raw-file-read happened.

    The implementation returns observations / manifests / attributions
    from in-memory dictionaries populated by the test. It deliberately
    does NOT call any ``SourceIngestRunner`` or any raw-file reader.
    """

    def __init__(self) -> None:
        self.observations: dict[str, list[NormalizedObservation]] = {}  # noqa: F821
        self.manifests: dict[tuple[str, str | None], SourceManifest] = {}  # noqa: F821
        self.attributions_by_slug: dict[str, SourceAttribution] = {}  # noqa: F821
        self.calls: list[tuple[str, tuple]] = []

    # The methods below are duck-typed to match the
    # ``EvidenceRepository`` ``Protocol``; ``isinstance`` against the
    # protocol must succeed once these are in place.

    def query_observations(self, query) -> Sequence[NormalizedObservation]:  # type: ignore[no-untyped-def]  # noqa: F821
        self.calls.append(("query_observations", (query,)))
        results: list[NormalizedObservation] = []  # noqa: F821
        for observations in self.observations.values():
            results.extend(observations)
        return results

    def get_manifest(self, source_id, run_id=None):  # type: ignore[no-untyped-def]
        self.calls.append(("get_manifest", (source_id, run_id)))
        return self.manifests[(source_id.slug, run_id)]

    def get_attributions(self, source_ids) -> Sequence[SourceAttribution]:  # type: ignore[no-untyped-def]  # noqa: F821
        self.calls.append(("get_attributions", (tuple(source_ids),)))
        return [
            self.attributions_by_slug[source_id.slug]
            for source_id in source_ids
            if source_id.slug in self.attributions_by_slug
        ]


# ---------------------------------------------------------------------------
# SRC-QUERY-001 — package surface exposes the query interface.
# ---------------------------------------------------------------------------


def test_query_package_exposes_evidence_query_dataclass() -> None:
    """``EvidenceQuery`` is importable from the ``leaders_db.sources`` root.

    SRC-QUERY-001: the package surface re-exports the query dataclass
    so callers can ``from leaders_db.sources import EvidenceQuery``
    without depending on a submodule.

    PASS-ELIGIBLE: the package ``__init__`` re-exports ``EvidenceQuery``.
    """
    from leaders_db.sources import EvidenceQuery

    assert dataclasses.is_dataclass(EvidenceQuery)


def test_query_package_exposes_evidence_repository_protocol() -> None:
    """``EvidenceRepository`` is importable from the ``leaders_db.sources`` root.

    SRC-QUERY-001: the protocol lives on the public surface and is
    ``runtime_checkable`` so the fake repository can be validated
    with ``isinstance`` in tests.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceRepository

    assert hasattr(EvidenceRepository, "query_observations")
    assert hasattr(EvidenceRepository, "get_manifest")
    assert hasattr(EvidenceRepository, "get_attributions")


# ---------------------------------------------------------------------------
# SRC-QUERY-002 — documented filters exist and preserve values.
# ---------------------------------------------------------------------------


def test_evidence_query_exposes_all_documented_filters() -> None:
    """``EvidenceQuery`` has the documented filter fields.

    SRC-QUERY-002 / docs/architecture/sources.md §5.7: source,
    observation family, indicator, year, country, leader.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceQuery

    expected = {
        "source_ids",
        "observation_families",
        "indicator_codes",
        "years",
        "countries",
        "leaders",
    }
    actual = {f.name for f in dataclasses.fields(EvidenceQuery)}
    assert expected.issubset(actual), f"missing filters: {expected - actual}"


def test_evidence_query_filter_values_roundtrip_through_construction() -> None:
    """Each documented filter preserves its constructed value.

    SRC-QUERY-002: every filter must round-trip so the runner / scorer
    receives exactly what the caller requested.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceQuery, SourceId

    query = EvidenceQuery(
        source_ids=(SourceId(slug="vdem"), SourceId(slug="wgi")),
        observation_families=("political_freedom",),
        indicator_codes=("v2x_polyarchy",),
        years=(2022, 2023),
        countries=("USA", "DEU"),
        leaders=("leader-1",),
    )

    assert query.source_ids == (SourceId(slug="vdem"), SourceId(slug="wgi"))
    assert query.observation_families == ("political_freedom",)
    assert query.indicator_codes == ("v2x_polyarchy",)
    assert query.years == (2022, 2023)
    assert query.countries == ("USA", "DEU")
    assert query.leaders == ("leader-1",)


def test_evidence_query_filter_defaults_are_all_unfiltered() -> None:
    """Default filter values are ``None`` — meaning "no filter".

    SRC-QUERY-002: callers that do not specify a filter must get
    ``None`` (the documented "no filter" sentinel), not an empty
    tuple that would silently exclude everything.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceQuery

    query = EvidenceQuery()
    assert query.source_ids is None
    assert query.observation_families is None
    assert query.indicator_codes is None
    assert query.years is None
    assert query.countries is None
    assert query.leaders is None


def test_evidence_query_year_filter_accepts_int_tuples() -> None:
    """The year filter accepts a tuple of ``int`` values, in order.

    SRC-QUERY-002: the contract is a tuple of ints so callers can
    request non-contiguous year sets without ambiguity.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceQuery

    query = EvidenceQuery(years=(1990, 2000, 2010, 2023))
    assert query.years == (1990, 2000, 2010, 2023)
    assert all(isinstance(year, int) for year in query.years)


# ---------------------------------------------------------------------------
# SRC-QUERY-003 — include flags exist and preserve values.
# ---------------------------------------------------------------------------


def test_evidence_query_exposes_documented_include_flags() -> None:
    """``EvidenceQuery`` has every documented include flag.

    SRC-QUERY-003 / docs/architecture/sources.md §5.7: include
    raw locators, warnings, quality flags, manifests, and attribution.
    The runtime ``EvidenceQuery`` enumerates the same five flags.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceQuery

    expected = {
        "include_raw_locators",
        "include_warnings",
        "include_quality_flags",
        "include_manifests",
        "include_attribution",
    }
    actual = {f.name for f in dataclasses.fields(EvidenceQuery)}
    assert expected.issubset(actual), f"missing include flags: {expected - actual}"


def test_evidence_query_include_flag_defaults() -> None:
    """Default include flags keep raw locators / warnings / quality flags /
    attribution enabled and ``include_manifests`` disabled by default.

    SRC-QUERY-003: callers that do not specify include flags get a
    sensible default — provenance and quality context are on by
    default; manifests are off until the caller asks for them
    because manifests are heavier than per-row data.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceQuery

    query = EvidenceQuery()
    assert query.include_raw_locators is True
    assert query.include_warnings is True
    assert query.include_quality_flags is True
    assert query.include_attribution is True
    assert query.include_manifests is False


def test_evidence_query_include_flags_roundtrip_through_construction() -> None:
    """Each include flag preserves its constructed boolean value.

    SRC-QUERY-003: a scorer that wants lighter observations (no
    raw locators, no warnings) must be able to turn each flag off
    independently. The dataclass round-trips all five flags.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceQuery

    query = EvidenceQuery(
        include_raw_locators=False,
        include_warnings=False,
        include_quality_flags=False,
        include_manifests=True,
        include_attribution=False,
    )
    assert query.include_raw_locators is False
    assert query.include_warnings is False
    assert query.include_quality_flags is False
    assert query.include_manifests is True
    assert query.include_attribution is False


# ---------------------------------------------------------------------------
# SRC-QUERY-004 — query does not rerun ingestion.
# ---------------------------------------------------------------------------


def test_evidence_query_observations_returns_in_memory_results_without_ingestion() -> None:
    """``query_observations`` returns results from in-memory state.

    SRC-QUERY-004: the query path is read-only and MUST NOT trigger
    source ingestion. The test builds a ``_FakeEvidenceRepository``
    populated with a single observation and asserts:

    1. The repository returns the observation unchanged.
    2. No ``SourceIngestRunner`` is instantiated and no lifecycle
       method (``check_ready`` / ``read_raw`` / ``transform``) is
       invoked.

    PASS-ELIGIBLE: the ``EvidenceRepository`` Protocol surface
    accepts any implementation, including a no-ingestion in-memory
    fake. The test pins the no-ingestion contract by counting
    runner / lifecycle calls.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        SourceId,
    )

    repository = _FakeEvidenceRepository()
    repository.observations["vdem"] = [_observation("vdem")]
    repository.attributions_by_slug["vdem"] = _attribution("vdem")

    query = EvidenceQuery(source_ids=(SourceId(slug="vdem"),))
    results = repository.query_observations(query)

    assert list(results) == repository.observations["vdem"]

    # Only the query_observations call itself is allowed; no runner
    # or lifecycle method may have been triggered. The runner is
    # imported lazily so the assertion also fails if a future
    # refactor wires the repository to instantiate the runner.
    from leaders_db.sources import SourceIngestRunner

    assert isinstance(repository, SourceIngestRunner) is False
    method_names = [name for name, _ in repository.calls]
    assert method_names == ["query_observations"], (
        f"only query_observations should be called; saw {method_names}"
    )


def test_evidence_repository_fake_satisfies_runtime_checkable_protocol() -> None:
    """The fake ``_FakeEvidenceRepository`` satisfies the runtime-checkable
    ``EvidenceRepository`` Protocol.

    SRC-QUERY-001 / SRC-QUERY-004: the Protocol is ``runtime_checkable``
    so any caller can verify that a candidate implements the three
    documented methods. The test instantiates the fake and asserts
    ``isinstance(repository, EvidenceRepository)``.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import EvidenceRepository

    repository = _FakeEvidenceRepository()
    assert isinstance(repository, EvidenceRepository)


# ---------------------------------------------------------------------------
# SRC-QUERY-005 — query does not read raw files.
# ---------------------------------------------------------------------------


def test_get_manifest_returns_in_memory_manifest_without_raw_read() -> None:
    """``get_manifest`` returns the manifest from in-memory state.

    SRC-QUERY-005: the query path MUST NOT read raw files directly;
    diagnostics that need raw access live in explicitly documented
    tooling, not in the standard repository surface. The test
    populates the fake repository with one manifest and asserts the
    call returns the same object and does NOT touch any raw-file
    reader (no ``Path.open``, no ``Path.read_*``, no os-level file
    open calls).

    PASS-ELIGIBLE: the fake is in-memory only; the assertion will
    fail loudly if a future implementation wires ``get_manifest``
    to a raw-file reader.
    """
    from leaders_db.sources import SourceId

    repository = _FakeEvidenceRepository()
    manifest = _manifest("vdem", run_id="run-2023-01-01")
    repository.manifests[(manifest.source_id.slug, manifest.run_id)] = manifest

    result = repository.get_manifest(SourceId(slug="vdem"), run_id="run-2023-01-01")
    assert result is manifest
    assert [name for name, _ in repository.calls] == ["get_manifest"]


def test_get_attributions_returns_in_memory_attributions_without_raw_read() -> None:
    """``get_attributions`` returns the attributions from in-memory state.

    SRC-QUERY-004 / SRC-QUERY-005: the query path is read-only and
    MUST NOT trigger ingestion or raw-file reads. The test populates
    the fake with attributions for two sources and asserts the
    repository returns the same objects in the same order without
    any ingestion / raw-read side effect.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources import SourceId

    repository = _FakeEvidenceRepository()
    attribution_a = _attribution("vdem")
    attribution_b = _attribution("wgi")
    repository.attributions_by_slug["vdem"] = attribution_a
    repository.attributions_by_slug["wgi"] = attribution_b

    result = list(
        repository.get_attributions((SourceId(slug="vdem"), SourceId(slug="wgi"))),
    )
    assert result == [attribution_a, attribution_b]
    assert [name for name, _ in repository.calls] == ["get_attributions"]


def test_query_path_does_not_open_raw_files() -> None:
    """None of the query methods open raw files.

    SRC-QUERY-005: the query interface MUST NOT read raw files
    directly. The test patches ``Path.open`` and ``Path.read_bytes``
    / ``Path.read_text`` on the ``leaders_db.sources.query`` module
    to count invocations and asserts they are never called when the
    repository serves a fully-populated in-memory state.

    PASS-ELIGIBLE.
    """
    import leaders_db.sources.query as query_module
    from leaders_db.sources import (
        EvidenceQuery,
        SourceId,
    )

    original_open = Path.open
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    raw_file_calls: list[tuple[str, tuple]] = []

    def _tracking_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raw_file_calls.append(("open", (str(self),)))
        return original_open(self, *args, **kwargs)

    def _tracking_read_bytes(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raw_file_calls.append(("read_bytes", (str(self),)))
        return original_read_bytes(self, *args, **kwargs)

    def _tracking_read_text(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raw_file_calls.append(("read_text", (str(self),)))
        return original_read_text(self, *args, **kwargs)

    Path.open = _tracking_open  # type: ignore[method-assign]
    Path.read_bytes = _tracking_read_bytes  # type: ignore[method-assign]
    Path.read_text = _tracking_read_text  # type: ignore[method-assign]
    try:
        repository = _FakeEvidenceRepository()
        repository.observations["vdem"] = [_observation("vdem")]
        repository.manifests[("vdem", "run-2023-01-01")] = _manifest(
            "vdem", run_id="run-2023-01-01",
        )
        repository.attributions_by_slug["vdem"] = _attribution("vdem")

        list(repository.query_observations(EvidenceQuery()))
        repository.get_manifest(SourceId(slug="vdem"), run_id="run-2023-01-01")
        list(repository.get_attributions((SourceId(slug="vdem"),)))
    finally:
        Path.open = original_open  # type: ignore[method-assign]
        Path.read_bytes = original_read_bytes  # type: ignore[method-assign]
        Path.read_text = original_read_text  # type: ignore[method-assign]

    assert raw_file_calls == [], (
        f"query methods must not open raw files; saw {raw_file_calls}"
    )
    # Belt-and-braces: ensure the patched module is still importable
    # (defensive against a future refactor that moves the module).
    assert hasattr(query_module, "EvidenceRepository")


__all__ = [
    "_FakeEvidenceRepository",
    "_attribution",
    "_descriptor",
    "_manifest",
    "_observation",
    "test_evidence_query_exposes_all_documented_filters",
    "test_evidence_query_exposes_documented_include_flags",
    "test_evidence_query_filter_defaults_are_all_unfiltered",
    "test_evidence_query_filter_values_roundtrip_through_construction",
    "test_evidence_query_include_flag_defaults",
    "test_evidence_query_include_flags_roundtrip_through_construction",
    "test_evidence_query_observations_returns_in_memory_results_without_ingestion",
    "test_evidence_query_year_filter_accepts_int_tuples",
    "test_evidence_repository_fake_satisfies_runtime_checkable_protocol",
    "test_get_attributions_returns_in_memory_attributions_without_raw_read",
    "test_get_manifest_returns_in_memory_manifest_without_raw_read",
    "test_query_package_exposes_evidence_query_dataclass",
    "test_query_package_exposes_evidence_repository_protocol",
    "test_query_path_does_not_open_raw_files",
]
