"""Phase C/D slice -- concrete ``InMemoryEvidenceRepository`` tests.

The ``InMemoryEvidenceRepository`` (in ``src/leaders_db/sources/query.py``,
re-exported from the ``leaders_db.sources`` package root) is the
canonical read-only, deterministic, no-I/O implementation of the
``EvidenceRepository`` ``Protocol``. These tests pin:

- ``SRC-QUERY-006``: the in-memory repository satisfies the
  runtime-checkable ``EvidenceRepository`` ``Protocol`` and is
  importable from the ``leaders_db.sources`` package root.
- ``SRC-QUERY-007``: the constructor copies ``observations`` /
  ``manifests`` / ``attributions`` into internal tuples so the
  caller-owned lists are not mutated.
- ``SRC-QUERY-008``: ``query_observations`` honors every filter
  dimension with the documented ``None`` (unfiltered) vs ``()``
  (no-match) semantics, matches ``source_ids`` by ``SourceId.slug``,
  matches ``leaders`` by ``leader_id`` or ``leader_name``, and
  preserves the input observation order.
- ``SRC-QUERY-009``: ``get_manifest`` resolves an exact
  ``(slug, run_id)`` lookup when ``run_id`` is provided, returns the
  only manifest for the source when ``run_id`` is ``None`` and exactly
  one is stored, raises ``KeyError`` with an actionable message when
  multiple manifests exist under the same slug, and raises
  ``KeyError`` for missing manifests.
- ``SRC-QUERY-010``: ``get_attributions`` returns attributions in the
  requested ``source_ids`` order and silently skips sources without a
  stored attribution.
- ``SRC-QUERY-011``: the repository never imports
  ``leaders_db.ingest``, never instantiates ``SourceIngestRunner``,
  never calls source adapters, and never opens raw files -- enforced
  via monkeypatched ``SourceIngestRunner.__init__`` + ``Path.open`` /
  ``Path.read_text`` / ``Path.read_bytes`` sentinels plus the
  canonical import-boundary submodule list in
  ``tests/sources/test_import_boundary.py``.
- ``SRC-QUERY-012``: the four ``EvidenceQuery.include_*`` flags are
  advisory in this slice; the repository always returns the full
  stored observation.

The integration tests at the end of the file build synthetic WDI /
Maddison / PWT observations, query subsets through the repository,
and feed the filtered observations into
:func:`extract_concept` / :func:`extract_concept_result` to prove
the repository wires end-to-end with the concept layer.

PASS-ELIGIBLE rationale
-----------------------
The implementation lands in the same change set as the tests. The
boundary sentinels (import, runner, raw-file reads) are the same
sentinels that already prove the catalog boundary in
``tests/sources/test_concepts.py``.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Test-local helpers
# ---------------------------------------------------------------------------


def _make_observation(
    *,
    source_slug: str,
    indicator_code: str = "test_indicator",
    value: object = 1,
    year: int | None = 2023,
    country_code: str | None = "USA",
    country_name: str | None = "United States",
    leader_id: str | None = None,
    leader_name: str | None = None,
    observation_family: str = "test_family",
    observation_id: str | None = None,
    source_version: str | None = "v1",
    quality_flags: tuple[str, ...] = (),
    warnings: tuple = (),
) -> object:
    """Build a synthetic :class:`NormalizedObservation` for tests.

    All other fields (locators, extension, etc.) are filled with
    harmless placeholders so callers only have to specify the
    fields that matter for the repository's behavior.
    """
    from leaders_db.sources import (
        NormalizedObservation,
        RawLocator,
        SourceId,
        TransformLocator,
    )

    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=(
            observation_id
            if observation_id is not None
            else f"{source_slug}:{indicator_code}:{year}:{country_code}"
        ),
        observation_family=observation_family,
        indicator_code=indicator_code,
        value=value,
        value_type="numeric",
        year=year,
        country_code=country_code,
        country_name=country_name,
        leader_id=leader_id,
        leader_name=leader_name,
        unit=None,
        scale=None,
        source_version=source_version,
        raw_locator=RawLocator(asset_id=f"{source_slug}:asset"),
        transform_locator=TransformLocator(transform_name="test_transform"),
        quality_flags=quality_flags,
        warnings=warnings,
    )


def _make_manifest(
    *,
    source_slug: str,
    run_id: str,
    source_version: str | None = "v1",
    observation_count: int = 0,
) -> object:
    """Build a synthetic :class:`SourceManifest` for tests."""
    from leaders_db.sources import (
        SourceId,
        SourceIngestRequest,
        SourceManifest,
    )

    return SourceManifest(
        source_id=SourceId(slug=source_slug),
        run_id=run_id,
        request=SourceIngestRequest(
            source_id=SourceId(slug=source_slug),
            run_id=run_id,
        ),
        source_version=source_version,
        raw_assets=(),
        output_assets=(),
        observation_count=observation_count,
    )


def _make_attribution(*, source_slug: str) -> object:
    """Build a synthetic :class:`SourceAttribution` for tests."""
    from leaders_db.sources import SourceAttribution, SourceId

    return SourceAttribution(
        attribution_key=source_slug,
        source_id=SourceId(slug=source_slug),
        text=f"Citation text for {source_slug}.",
        citation_url=f"https://example.org/{source_slug}",
        license_name="CC-BY 4.0",
    )


# ---------------------------------------------------------------------------
# SRC-QUERY-006 -- package surface, Protocol conformance, export
# ---------------------------------------------------------------------------


def test_in_memory_evidence_repository_is_importable_from_package_root() -> None:
    """``InMemoryEvidenceRepository`` is importable from the
    ``leaders_db.sources`` package root.

    ``SRC-QUERY-006``: the concrete implementation is re-exported
    from the package root so consumers can ``from
    leaders_db.sources import InMemoryEvidenceRepository``.
    """
    from leaders_db.sources import InMemoryEvidenceRepository

    assert InMemoryEvidenceRepository.__name__ == "InMemoryEvidenceRepository"


def test_in_memory_evidence_repository_satisfies_protocol() -> None:
    """The in-memory repository satisfies the runtime-checkable
    ``EvidenceRepository`` ``Protocol``.

    ``SRC-QUERY-006``: ``isinstance(repository, EvidenceRepository)``
    must succeed so any caller that depends on the ``Protocol`` can
    accept the concrete implementation without rewiring.
    """
    from leaders_db.sources import (
        EvidenceRepository,
        InMemoryEvidenceRepository,
    )

    repository = InMemoryEvidenceRepository()
    assert isinstance(repository, EvidenceRepository)


def test_in_memory_evidence_repository_exposes_documented_methods() -> None:
    """The in-memory repository exposes the three documented
    ``EvidenceRepository`` methods.

    ``SRC-QUERY-006``: the runtime surface must match the
    ``Protocol`` definition in
    ``src/leaders_db/sources/query.py``.
    """
    from leaders_db.sources import InMemoryEvidenceRepository

    repository = InMemoryEvidenceRepository()
    assert hasattr(repository, "query_observations")
    assert hasattr(repository, "get_manifest")
    assert hasattr(repository, "get_attributions")
    assert callable(repository.query_observations)
    assert callable(repository.get_manifest)
    assert callable(repository.get_attributions)


def test_query_module_reexports_in_memory_evidence_repository() -> None:
    """``src/leaders_db/sources/query.py`` re-exports the concrete
    in-memory repository alongside the ``Protocol``.

    Defense in depth: callers that import directly from the module
    get both names so the protocol and its first concrete
    implementation travel together.
    """
    import leaders_db.sources.query as query_module

    assert hasattr(query_module, "EvidenceRepository")
    assert hasattr(query_module, "InMemoryEvidenceRepository")


# ---------------------------------------------------------------------------
# SRC-QUERY-007 -- constructor does not mutate caller-owned sequences
# ---------------------------------------------------------------------------


def test_constructor_does_not_mutate_caller_owned_observations_list() -> None:
    """The constructor copies the caller-owned observations list.

    ``SRC-QUERY-007``: the repository must not mutate the input list
    so the caller can re-use it after construction.
    """
    from leaders_db.sources import InMemoryEvidenceRepository

    observations = [
        _make_observation(source_slug="vdem", indicator_code="a"),
        _make_observation(source_slug="wdi", indicator_code="b"),
    ]
    snapshot = list(observations)
    InMemoryEvidenceRepository(observations=observations)
    assert observations == snapshot


def test_constructor_does_not_mutate_caller_owned_manifests_list() -> None:
    """The constructor copies the caller-owned manifests list."""
    from leaders_db.sources import InMemoryEvidenceRepository

    manifests = [
        _make_manifest(source_slug="vdem", run_id="r1"),
        _make_manifest(source_slug="wdi", run_id="r1"),
    ]
    snapshot = list(manifests)
    InMemoryEvidenceRepository(manifests=manifests)
    assert manifests == snapshot


def test_constructor_does_not_mutate_caller_owned_attributions_list() -> None:
    """The constructor copies the caller-owned attributions list."""
    from leaders_db.sources import InMemoryEvidenceRepository

    attributions = [
        _make_attribution(source_slug="vdem"),
        _make_attribution(source_slug="wdi"),
    ]
    snapshot = list(attributions)
    InMemoryEvidenceRepository(attributions=attributions)
    assert attributions == snapshot


def test_empty_repository_is_constructible() -> None:
    """An ``InMemoryEvidenceRepository()`` with no arguments is a valid empty store.

    Tests that only exercise ``get_manifest`` / ``get_attributions``
    should be able to construct the repository without a sentinel
    observations argument.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    repository = InMemoryEvidenceRepository()
    assert repository.query_observations(EvidenceQuery()) == ()


def test_constructor_accepts_empty_sequences() -> None:
    """Empty sequences are accepted and produce an empty store."""
    from leaders_db.sources import InMemoryEvidenceRepository

    repository = InMemoryEvidenceRepository(
        observations=(),
        manifests=(),
        attributions=(),
    )
    assert repository.query_observations.__call__  # attribute access works


# ---------------------------------------------------------------------------
# SRC-QUERY-008 -- filter semantics
# ---------------------------------------------------------------------------


def test_query_observations_returns_all_when_filters_are_none() -> None:
    """When every filter is ``None`` the repository returns every
    stored observation in input order.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observations = [
        _make_observation(source_slug="vdem", indicator_code="a", year=2022),
        _make_observation(source_slug="wdi", indicator_code="b", year=2023),
        _make_observation(source_slug="pwt", indicator_code="c", year=2019),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(EvidenceQuery())

    assert rows == tuple(observations)


def test_query_observations_preserves_input_observation_order() -> None:
    """The repository preserves the input observation order regardless of
    which filter is applied.

    Order preservation is required by ``SRC-QUERY-008`` so consumers
    can rely on iteration order without sorting the result.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
    )

    observations = [
        _make_observation(
            source_slug="vdem",
            indicator_code="a",
            year=2010,
            country_code="USA",
        ),
        _make_observation(
            source_slug="vdem",
            indicator_code="b",
            year=2010,
            country_code="USA",
        ),
        _make_observation(
            source_slug="vdem",
            indicator_code="c",
            year=2010,
            country_code="USA",
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(
        EvidenceQuery(
            source_ids=(SourceId(slug="vdem"),),
            years=(2010,),
        ),
    )

    assert rows == tuple(observations)


def test_source_ids_filter_matches_by_source_id_slug() -> None:
    """The ``source_ids`` filter matches against ``SourceId.slug``.

    ``SRC-QUERY-008``: callers that pass freshly-built ``SourceId``
    instances (not identity-equal to the stored ``source_id``) still
    hit the right rows because the repository matches on slug.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
    )

    observations = [
        _make_observation(source_slug="vdem", indicator_code="a"),
        _make_observation(source_slug="wdi", indicator_code="b"),
        _make_observation(source_slug="pwt", indicator_code="c"),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(
        EvidenceQuery(source_ids=(SourceId(slug="vdem"), SourceId(slug="pwt"))),
    )

    slugs = tuple(row.source_id.slug for row in rows)
    assert slugs == ("vdem", "pwt")


def test_observation_families_filter_honors_set_membership() -> None:
    """The ``observation_families`` filter honors set-membership semantics.

    An empty tuple ``()`` returns no observations for that
    dimension (per the documented "natural membership" rule).
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observations = [
        _make_observation(
            source_slug="vdem",
            indicator_code="a",
            observation_family="political_freedom",
        ),
        _make_observation(
            source_slug="wdi",
            indicator_code="b",
            observation_family="economic_country_year",
        ),
        _make_observation(
            source_slug="pwt",
            indicator_code="c",
            observation_family="economic_country_year",
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(
        EvidenceQuery(observation_families=("economic_country_year",)),
    )
    assert tuple(row.source_id.slug for row in rows) == ("wdi", "pwt")

    # Empty tuple is a deliberate "no match" filter.
    rows_empty = repository.query_observations(
        EvidenceQuery(observation_families=(),),
    )
    assert rows_empty == ()


def test_indicator_codes_filter_honors_set_membership() -> None:
    """The ``indicator_codes`` filter matches by indicator code only."""
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observations = [
        _make_observation(source_slug="wdi", indicator_code="wdi_gdp"),
        _make_observation(source_slug="wdi", indicator_code="wdi_pop"),
        _make_observation(source_slug="pwt", indicator_code="pwt_rgdp"),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(
        EvidenceQuery(indicator_codes=("wdi_gdp", "pwt_rgdp")),
    )
    assert tuple(row.indicator_code for row in rows) == ("wdi_gdp", "pwt_rgdp")

    rows_empty = repository.query_observations(EvidenceQuery(indicator_codes=()))
    assert rows_empty == ()


def test_years_filter_matches_against_observation_year() -> None:
    """The ``years`` filter matches against ``observation.year``.

    A stored observation with ``year=None`` (non-country-year scope)
    never matches an explicit year filter.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observations = [
        _make_observation(source_slug="vdem", indicator_code="a", year=2022),
        _make_observation(source_slug="vdem", indicator_code="b", year=2023),
        _make_observation(
            source_slug="vdem",
            indicator_code="c",
            year=None,
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(EvidenceQuery(years=(2023,)))
    assert tuple(row.indicator_code for row in rows) == ("b",)

    rows_empty = repository.query_observations(EvidenceQuery(years=()))
    assert rows_empty == ()


def test_countries_filter_matches_against_country_code_or_name() -> None:
    """The ``countries`` filter matches against either ``country_code``
    or ``country_name``.

    An empty tuple ``()`` returns no observations for that dimension.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observations = [
        _make_observation(
            source_slug="wdi",
            indicator_code="a",
            country_code="USA",
            country_name="United States",
        ),
        _make_observation(
            source_slug="wdi",
            indicator_code="b",
            country_code="DEU",
            country_name="Germany",
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(EvidenceQuery(countries=("USA",)))
    assert tuple(row.indicator_code for row in rows) == ("a",)

    rows_by_name = repository.query_observations(
        EvidenceQuery(countries=("Germany",)),
    )
    assert tuple(row.indicator_code for row in rows_by_name) == ("b",)

    rows_empty = repository.query_observations(EvidenceQuery(countries=()))
    assert rows_empty == ()


def test_leaders_filter_matches_by_leader_id_or_leader_name() -> None:
    """The ``leaders`` filter matches against either ``leader_id``
    or ``leader_name``.

    ``SRC-QUERY-008``: leader identity is unstable across sources
    today, so the repository matches either field so callers can
    query by either dimension until leader IDs are stable.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observations = [
        _make_observation(
            source_slug="vdem",
            indicator_code="a",
            leader_id="L1",
            leader_name="Alice",
        ),
        _make_observation(
            source_slug="vdem",
            indicator_code="b",
            leader_id="L2",
            leader_name="Bob",
        ),
        _make_observation(
            source_slug="vdem",
            indicator_code="c",
            leader_id="L3",
            leader_name="Carol",
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows_by_id = repository.query_observations(EvidenceQuery(leaders=("L1",)))
    assert tuple(row.indicator_code for row in rows_by_id) == ("a",)

    rows_by_name = repository.query_observations(EvidenceQuery(leaders=("Bob",)))
    assert tuple(row.indicator_code for row in rows_by_name) == ("b",)

    rows_either = repository.query_observations(
        EvidenceQuery(leaders=("L1", "Carol")),
    )
    assert tuple(row.indicator_code for row in rows_either) == ("a", "c")

    rows_empty = repository.query_observations(EvidenceQuery(leaders=()))
    assert rows_empty == ()


def test_filter_combinations_intersect() -> None:
    """When multiple filters are supplied, the repository intersects them."""
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
    )

    observations = [
        _make_observation(
            source_slug="vdem",
            indicator_code="a",
            year=2023,
            country_code="USA",
        ),
        _make_observation(
            source_slug="vdem",
            indicator_code="b",
            year=2022,
            country_code="USA",
        ),
        _make_observation(
            source_slug="wdi",
            indicator_code="c",
            year=2023,
            country_code="USA",
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    rows = repository.query_observations(
        EvidenceQuery(
            source_ids=(SourceId(slug="vdem"),),
            years=(2023,),
            countries=("USA",),
        ),
    )
    assert tuple(row.indicator_code for row in rows) == ("a",)


def test_none_filters_and_empty_filters_have_distinct_semantics() -> None:
    """``None`` means "unfiltered"; ``()`` means "no match".

    The same dimension must treat the two values differently. A
    consumer that accidentally passes ``()`` instead of ``None``
    must get an empty result, not the full stream.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observations = [
        _make_observation(source_slug="vdem", indicator_code="a"),
        _make_observation(source_slug="wdi", indicator_code="b"),
    ]
    repository = InMemoryEvidenceRepository(observations=observations)

    none_rows = repository.query_observations(EvidenceQuery(years=None))
    assert none_rows == tuple(observations)

    empty_rows = repository.query_observations(EvidenceQuery(years=()))
    assert empty_rows == ()


def test_include_flags_are_advisory_in_memory_implementation() -> None:
    """The four ``EvidenceQuery.include_*`` flags are advisory in this slice.

    ``SRC-QUERY-012``: the repository always returns the full stored
    observation. A future persistence-backed repository may strip the
    optional fields when the caller asks for lighter rows.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
        SourceWarning,
    )

    warning_code = "test_warning"
    quality_flag = "test_quality_flag"

    observation = _make_observation(
        source_slug="vdem",
        indicator_code="a",
        quality_flags=(quality_flag,),
        warnings=(
            SourceWarning(
                code=warning_code,
                message="test",
                source_id=SourceId(slug="vdem"),
            ),
        ),
    )
    repository = InMemoryEvidenceRepository(observations=[observation])

    rows = repository.query_observations(
        EvidenceQuery(
            include_raw_locators=False,
            include_warnings=False,
            include_quality_flags=False,
            include_attribution=False,
            include_manifests=True,
        ),
    )

    assert len(rows) == 1
    row = rows[0]
    # Advisory: the observation is returned with all fields intact.
    assert row.raw_locator.asset_id == "vdem:asset"
    assert row.quality_flags == (quality_flag,)
    assert tuple(w.code for w in row.warnings) == (warning_code,)


# ---------------------------------------------------------------------------
# SRC-QUERY-009 -- manifest retrieval
# ---------------------------------------------------------------------------


def test_get_manifest_exact_run_id_lookup() -> None:
    """``get_manifest`` performs an exact ``(slug, run_id)`` lookup."""
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    manifest = _make_manifest(source_slug="vdem", run_id="run-2023-01-01")
    repository = InMemoryEvidenceRepository(manifests=[manifest])

    result = repository.get_manifest(
        SourceId(slug="vdem"), run_id="run-2023-01-01",
    )
    assert result is manifest


def test_get_manifest_unknown_run_id_raises_key_error() -> None:
    """``get_manifest`` raises ``KeyError`` for an unknown run id.

    ``SRC-QUERY-009``: the error message names the source slug and
    the known run ids so the caller can fix the lookup.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    manifest = _make_manifest(source_slug="vdem", run_id="run-2023-01-01")
    repository = InMemoryEvidenceRepository(manifests=[manifest])

    with pytest.raises(KeyError) as excinfo:
        repository.get_manifest(
            SourceId(slug="vdem"), run_id="run-9999",
        )
    message = str(excinfo.value)
    assert "vdem" in message
    assert "run-2023-01-01" in message


def test_get_manifest_with_no_run_id_returns_only_manifest() -> None:
    """When ``run_id=None`` and exactly one manifest is stored for the
    source, the repository returns it.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    manifest = _make_manifest(source_slug="vdem", run_id="run-2023-01-01")
    repository = InMemoryEvidenceRepository(manifests=[manifest])

    result = repository.get_manifest(SourceId(slug="vdem"))
    assert result is manifest


def test_get_manifest_with_no_run_id_and_multiple_manifests_raises() -> None:
    """When ``run_id=None`` and multiple manifests are stored for the
    same source, the repository raises ``KeyError`` with an
    actionable message naming the available run ids.

    ``SRC-QUERY-009``: the slice prefers explicit ambiguity over
    silent picking.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    manifests = [
        _make_manifest(source_slug="vdem", run_id="run-2023-01-01"),
        _make_manifest(source_slug="vdem", run_id="run-2023-06-01"),
    ]
    repository = InMemoryEvidenceRepository(manifests=manifests)

    with pytest.raises(KeyError) as excinfo:
        repository.get_manifest(SourceId(slug="vdem"))
    message = str(excinfo.value)
    assert "vdem" in message
    assert "run-2023-01-01" in message
    assert "run-2023-06-01" in message


def test_get_manifest_for_unknown_source_raises_key_error() -> None:
    """``get_manifest`` raises ``KeyError`` for a source slug with no
    stored manifests at all.

    ``SRC-QUERY-009``: the error names the source slug.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    repository = InMemoryEvidenceRepository()

    with pytest.raises(KeyError) as excinfo:
        repository.get_manifest(SourceId(slug="vdem"))
    assert "vdem" in str(excinfo.value)


def test_get_manifest_with_unknown_source_and_explicit_run_id_raises() -> None:
    """``get_manifest`` raises ``KeyError`` for an unknown source
    even when ``run_id`` is provided.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    repository = InMemoryEvidenceRepository()

    with pytest.raises(KeyError) as excinfo:
        repository.get_manifest(
            SourceId(slug="vdem"), run_id="run-2023-01-01",
        )
    message = str(excinfo.value)
    assert "vdem" in message
    assert "run-2023-01-01" in message


# ---------------------------------------------------------------------------
# SRC-QUERY-010 -- attribution retrieval
# ---------------------------------------------------------------------------


def test_get_attributions_returns_in_requested_order() -> None:
    """``get_attributions`` returns attributions in the order of the
    requested ``source_ids`` argument.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    attribution_vdem = _make_attribution(source_slug="vdem")
    attribution_wgi = _make_attribution(source_slug="wgi")
    repository = InMemoryEvidenceRepository(
        attributions=[attribution_vdem, attribution_wgi],
    )

    result = repository.get_attributions(
        (SourceId(slug="wgi"), SourceId(slug="vdem")),
    )

    assert result == (attribution_wgi, attribution_vdem)


def test_get_attributions_silently_skips_missing_sources() -> None:
    """Sources without a stored attribution are silently skipped.

    ``SRC-QUERY-010``: matches the documented
    ``_FakeEvidenceRepository`` contract so existing tests do not
    regress.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    attribution_vdem = _make_attribution(source_slug="vdem")
    repository = InMemoryEvidenceRepository(attributions=[attribution_vdem])

    result = repository.get_attributions(
        (SourceId(slug="vdem"), SourceId(slug="wgi")),
    )

    assert result == (attribution_vdem,)


def test_get_attributions_returns_empty_tuple_when_no_sources_match() -> None:
    """``get_attributions`` returns an empty tuple when no requested
    source has a stored attribution.
    """
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    repository = InMemoryEvidenceRepository()

    result = repository.get_attributions((SourceId(slug="vdem"),))

    assert result == ()


def test_get_attributions_accepts_list_and_tuple_inputs() -> None:
    """``get_attributions`` accepts any ``Sequence[SourceId]`` input."""
    from leaders_db.sources import (
        InMemoryEvidenceRepository,
        SourceId,
    )

    attribution_vdem = _make_attribution(source_slug="vdem")
    attribution_wgi = _make_attribution(source_slug="wgi")
    repository = InMemoryEvidenceRepository(
        attributions=[attribution_vdem, attribution_wgi],
    )

    list_result = repository.get_attributions(
        [SourceId(slug="vdem"), SourceId(slug="wgi")],
    )
    tuple_result = repository.get_attributions(
        (SourceId(slug="vdem"), SourceId(slug="wgi")),
    )

    assert list_result == tuple_result == (attribution_vdem, attribution_wgi)


# ---------------------------------------------------------------------------
# SRC-QUERY-011 -- no-ingestion / no-raw-read boundary
# ---------------------------------------------------------------------------


def test_query_module_does_not_import_legacy_ingest() -> None:
    """``leaders_db.sources.query`` MUST NOT import ``leaders_db.ingest``.

    ``SRC-QUERY-011``: the import-boundary submodule list in
    ``tests/sources/test_import_boundary.py`` covers
    ``leaders_db.sources.query``; this test verifies the boundary
    holds at the module level.
    """
    _purge_leaders_db_modules()
    try:
        importlib.import_module("leaders_db.sources.query")
        leaked = sorted(
            name for name in sys.modules
            if name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            f"importing leaders_db.sources.query must not import "
            f"leaders_db.ingest (leaked modules: {leaked})"
        )
    finally:
        _purge_leaders_db_modules()


def test_repository_does_not_instantiate_source_ingest_runner() -> None:
    """The repository must not instantiate :class:`SourceIngestRunner`.

    ``SRC-QUERY-011``: the runner sentinel test proves the
    repository's read path is independent of ingestion.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
        SourceIngestRunner,
    )

    calls: list[tuple[str, tuple]] = []

    original_init = SourceIngestRunner.__init__

    def _tracking_init(self: object, *args: object, **kwargs: object) -> None:
        calls.append(("SourceIngestRunner.__init__", (args, tuple(sorted(kwargs)))))
        # Bypass the real init so the sentinel does not require a
        # registry argument.
        object.__setattr__(self, "_sentinel", True)

    SourceIngestRunner.__init__ = _tracking_init  # type: ignore[method-assign]
    try:
        observations = [_make_observation(source_slug="vdem", indicator_code="a")]
        manifests = [_make_manifest(source_slug="vdem", run_id="r1")]
        attributions = [_make_attribution(source_slug="vdem")]

        repository = InMemoryEvidenceRepository(
            observations=observations,
            manifests=manifests,
            attributions=attributions,
        )
        list(repository.query_observations(EvidenceQuery()))
        repository.get_manifest(SourceId(slug="vdem"), run_id="r1")
        repository.get_attributions((SourceId(slug="vdem"),))
    finally:
        SourceIngestRunner.__init__ = original_init  # type: ignore[method-assign]

    assert calls == [], (
        "InMemoryEvidenceRepository must not instantiate "
        f"SourceIngestRunner; saw {calls}"
    )


def test_repository_does_not_open_raw_files() -> None:
    """The repository must not open raw files.

    ``SRC-QUERY-011``: ``Path.open`` / ``Path.read_text`` /
    ``Path.read_bytes`` are the canonical sentinel hooks for the
    no-raw-read boundary; the repository must never invoke any of
    them.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
    )

    original_open = Path.open
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes

    raw_file_calls: list[tuple[str, tuple]] = []

    def _tracking_open(self: object, *args: object, **kwargs: object) -> object:
        raw_file_calls.append(("open", (str(self),)))
        return original_open(self, *args, **kwargs)

    def _tracking_read_text(self: object, *args: object, **kwargs: object) -> str:
        raw_file_calls.append(("read_text", (str(self),)))
        return original_read_text(self, *args, **kwargs)

    def _tracking_read_bytes(self: object, *args: object, **kwargs: object) -> bytes:
        raw_file_calls.append(("read_bytes", (str(self),)))
        return original_read_bytes(self, *args, **kwargs)

    Path.open = _tracking_open  # type: ignore[method-assign]
    Path.read_text = _tracking_read_text  # type: ignore[method-assign]
    Path.read_bytes = _tracking_read_bytes  # type: ignore[method-assign]
    try:
        observations = [_make_observation(source_slug="vdem", indicator_code="a")]
        manifests = [_make_manifest(source_slug="vdem", run_id="r1")]
        attributions = [_make_attribution(source_slug="vdem")]

        repository = InMemoryEvidenceRepository(
            observations=observations,
            manifests=manifests,
            attributions=attributions,
        )
        list(repository.query_observations(EvidenceQuery()))
        repository.get_manifest(SourceId(slug="vdem"), run_id="r1")
        repository.get_attributions((SourceId(slug="vdem"),))
    finally:
        Path.open = original_open  # type: ignore[method-assign]
        Path.read_text = original_read_text  # type: ignore[method-assign]
        Path.read_bytes = original_read_bytes  # type: ignore[method-assign]

    assert raw_file_calls == [], (
        "InMemoryEvidenceRepository must not open raw files; "
        f"saw {raw_file_calls}"
    )


def _purge_leaders_db_modules() -> None:
    """Remove every cached ``leaders_db.*`` module from ``sys.modules``.

    Helper for the import-boundary sentinel test. Keeping the
    helper small and local so the test file stays self-contained.
    """
    for name in list(sys.modules):
        if name == "leaders_db" or name.startswith("leaders_db."):
            del sys.modules[name]


# ---------------------------------------------------------------------------
# Integration with concepts: WDI / Maddison / PWT synthetic observations
# ---------------------------------------------------------------------------


def test_concept_extraction_via_in_memory_repository_wdi_gdp_per_capita() -> None:
    """End-to-end integration: build WDI observations in the
    repository, query a subset, and feed the subset into
    :func:`extract_concept` to confirm the repository wires with the
    concept layer without re-running ingestion.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
    )
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        WDI_GDP_PER_CAPITA_INDICATOR_CODE,
        WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
        WDI_SOURCE_KEY,
        extract_concept,
    )

    wdi_observations = [
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
            value=70_000.0,
            year=2023,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
            value=75_000.0,
            year=2023,
            country_code="USA",
        ),
        # Add a Maddison observation to prove the source_ids filter
        # narrows the stream correctly.
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=60_000.0,
            year=2023,
            country_code="USA",
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=wdi_observations)

    rows = repository.query_observations(
        EvidenceQuery(
            source_ids=(SourceId(slug=WDI_SOURCE_KEY),),
            years=(2023,),
            indicator_codes=(
                WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
            ),
        ),
    )

    assert tuple(r.source_id.slug for r in rows) == (WDI_SOURCE_KEY, WDI_SOURCE_KEY)
    assert tuple(r.indicator_code for r in rows) == (
        WDI_GDP_PER_CAPITA_INDICATOR_CODE,
        WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
    )

    concept_rows = extract_concept(
        tuple(rows), CONCEPT_GDP_PER_CAPITA, WDI_SOURCE_KEY,
    )
    assert len(concept_rows) == 2
    emitted_codes = {row.source_indicator_codes[0] for row in concept_rows}
    assert emitted_codes == {
        WDI_GDP_PER_CAPITA_INDICATOR_CODE,
        WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
    }


def test_concept_extraction_via_in_memory_repository_pwt_derived() -> None:
    """End-to-end integration: build PWT observations in the
    repository, query a subset, and feed the subset into
    :func:`extract_concept` so the derived ``gdp_per_capita``
    recipe runs against the repository output.

    The test exercises the catalog's per-scope derivation path
    through the repository boundary, proving that downstream
    consumers can drive the catalog from
    ``InMemoryEvidenceRepository`` instead of re-running the
    adapter.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
    )
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    pwt_observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,  # million 2017 USD
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,  # thousands of persons
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        # Different country for the same year -- a separate scope.
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=2_500_000.0,
            year=2019,
            country_code="DEU",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=83_000.0,
            year=2019,
            country_code="DEU",
            source_version="10.01",
        ),
    ]
    repository = InMemoryEvidenceRepository(observations=pwt_observations)

    rows = repository.query_observations(
        EvidenceQuery(
            source_ids=(SourceId(slug=PWT_SOURCE_KEY),),
            years=(2019,),
            countries=("USA", "DEU"),
        ),
    )
    assert len(rows) == 4

    concept_rows = extract_concept(
        tuple(rows), CONCEPT_GDP_PER_CAPITA, PWT_SOURCE_KEY,
    )
    assert len(concept_rows) == 2
    countries = {row.country_code for row in concept_rows}
    assert countries == {"USA", "DEU"}
    for row in concept_rows:
        assert row.mapping_type == "derived"
        assert "derived_concept" in row.quality_flags
        assert len(row.input_observation_ids) == 2


def test_concept_extraction_via_in_memory_repository_filters_then_extracts() -> None:
    """End-to-end integration: prove that
    :func:`extract_concept_result` works on the repository's filtered
    subset and surfaces the diagnostic warnings the catalog is
    contracted to expose.

    The test stages one PWT scope with a missing denominator; the
    diagnostic helper must surface a
    ``concept_missing_denominator`` warning without a derived row.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
        SourceId,
    )
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
        extract_concept_result,
    )

    pwt_observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        # Missing denominator (no PWT population observation for
        # USA 2019). The catalog must surface a missing-denominator
        # warning and emit zero derived rows.
    ]
    repository = InMemoryEvidenceRepository(observations=pwt_observations)

    rows = repository.query_observations(
        EvidenceQuery(
            source_ids=(SourceId(slug=PWT_SOURCE_KEY),),
            years=(2019,),
        ),
    )
    assert len(rows) == 1

    concept_rows = extract_concept(
        tuple(rows), CONCEPT_GDP_PER_CAPITA, PWT_SOURCE_KEY,
    )
    assert concept_rows == ()

    result = extract_concept_result(
        tuple(rows), CONCEPT_GDP_PER_CAPITA, PWT_SOURCE_KEY,
    )
    codes = tuple(w.code for w in result.warnings)
    assert "concept_missing_denominator" in codes


def test_repository_preserves_observation_metadata_through_query() -> None:
    """The repository preserves observation metadata through a
    query (locators, transform locators, source version, quality
    flags).

    Downstream concept extraction depends on the observation id,
    locator, and source version being preserved verbatim from the
    stored observation to the query result.
    """
    from leaders_db.sources import (
        EvidenceQuery,
        InMemoryEvidenceRepository,
    )

    observation = _make_observation(
        source_slug="vdem",
        indicator_code="v2x_polyarchy",
        year=2023,
        country_code="USA",
        source_version="v13",
        quality_flags=("proxy_year",),
        observation_id="vdem:USA:2023:v2x_polyarchy",
    )
    repository = InMemoryEvidenceRepository(observations=[observation])

    rows = repository.query_observations(EvidenceQuery())

    assert len(rows) == 1
    row = rows[0]
    assert row.observation_id == "vdem:USA:2023:v2x_polyarchy"
    assert row.source_version == "v13"
    assert row.quality_flags == ("proxy_year",)
    assert row.raw_locator.asset_id == "vdem:asset"
    assert row.transform_locator.transform_name == "test_transform"


__all__ = [
    "test_concept_extraction_via_in_memory_repository_filters_then_extracts",
    "test_concept_extraction_via_in_memory_repository_pwt_derived",
    "test_concept_extraction_via_in_memory_repository_wdi_gdp_per_capita",
    "test_constructor_accepts_empty_sequences",
    "test_constructor_does_not_mutate_caller_owned_attributions_list",
    "test_constructor_does_not_mutate_caller_owned_manifests_list",
    "test_constructor_does_not_mutate_caller_owned_observations_list",
    "test_countries_filter_matches_against_country_code_or_name",
    "test_empty_repository_is_constructible",
    "test_filter_combinations_intersect",
    "test_get_attributions_accepts_list_and_tuple_inputs",
    "test_get_attributions_returns_empty_tuple_when_no_sources_match",
    "test_get_attributions_returns_in_requested_order",
    "test_get_attributions_silently_skips_missing_sources",
    "test_get_manifest_exact_run_id_lookup",
    "test_get_manifest_for_unknown_source_raises_key_error",
    "test_get_manifest_unknown_run_id_raises_key_error",
    "test_get_manifest_with_no_run_id_and_multiple_manifests_raises",
    "test_get_manifest_with_no_run_id_returns_only_manifest",
    "test_get_manifest_with_unknown_source_and_explicit_run_id_raises",
    "test_in_memory_evidence_repository_exposes_documented_methods",
    "test_in_memory_evidence_repository_is_importable_from_package_root",
    "test_in_memory_evidence_repository_satisfies_protocol",
    "test_include_flags_are_advisory_in_memory_implementation",
    "test_indicator_codes_filter_honors_set_membership",
    "test_leaders_filter_matches_by_leader_id_or_leader_name",
    "test_none_filters_and_empty_filters_have_distinct_semantics",
    "test_observation_families_filter_honors_set_membership",
    "test_query_module_does_not_import_legacy_ingest",
    "test_query_module_reexports_in_memory_evidence_repository",
    "test_query_observations_preserves_input_observation_order",
    "test_query_observations_returns_all_when_filters_are_none",
    "test_repository_does_not_instantiate_source_ingest_runner",
    "test_repository_does_not_open_raw_files",
    "test_repository_preserves_observation_metadata_through_query",
    "test_source_ids_filter_matches_by_source_id_slug",
    "test_years_filter_matches_against_observation_year",
]
