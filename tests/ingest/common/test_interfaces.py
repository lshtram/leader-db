"""Phase B Increment A -- shared Stage 2 ingestion interface tests.

This file covers the typed contract exposed by
``leaders_db.ingest.interfaces``:

- :class:`IngestRequest` -- year/years validation, durable
  fields (country_filter, raw_root, processed_root,
  database_url, force_refresh, allow_network).
- :class:`SourceReadiness` -- ``ready`` / ``blocker`` /
  ``attribution`` semantics.
- :class:`IngestResult` -- Pydantic validators (non-negative
  counts, sorted/unique years) + durable fields
  (``manifest_path``, ``warnings``, ``attribution``).
- :class:`SourceAdapter` Protocol -- the 5-method shape
  (``check_ready`` / ``read`` / ``transform`` / ``write`` /
  ``ingest``) including the request-scoped ``check_ready``.

Per the ``docs/source-ingestion-plan.md`` mirrored layout
(see the Increment A design), the tests for the new shared
Stage 2 interface live in
``tests/ingest/common/test_interfaces.py``; the registry
tests live in ``tests/ingest/common/test_registry.py``.

PASS-ELIGIBLE / DOMAIN-RED conventions
--------------------------------------

Every test in this file is ``PASS-ELIGIBLE``: the test
exercises the Pydantic / dataclass contract surface that is
already implemented in the Phase A stub. The tests are
regression guards -- they must keep passing once the
production code lands.

Coverage
--------

- ``IngestRequest`` validates the ``year`` vs ``years``
  argument pair; calling code cannot accidentally pass
  conflicting years.
- ``IngestRequest`` durable fields (country_filter,
  raw_root, processed_root, database_url, force_refresh,
  allow_network) round-trip through the model.
- ``SourceReadiness`` represents a blocked source as
  ``ready=False`` with a non-empty ``blocker``; a ready
  source may carry an attribution block.
- ``IngestResult`` (Pydantic) round-trips the durable
  Phase B fields ``manifest_path``, ``warnings``, and
  ``attribution``; rejects negative counts and
  unsorted/duplicate ``years`` entries.
- The :class:`SourceAdapter` Protocol requires all five
  methods (``check_ready``, ``read``, ``transform``,
  ``write``, ``ingest``) and ``check_ready`` receives the
  :class:`IngestRequest` so the readiness gate can resolve
  request-scoped ``raw_root`` overrides.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# IngestRequest validation
# ---------------------------------------------------------------------------


def test_ingest_request_year_only_returns_single_tuple() -> None:
    """``year=2019`` with empty ``years`` -> ``effective_years == (2019,)``.

    Contract: ``IngestRequest(year=2019).effective_years == (2019,)``.

    PASS-ELIGIBLE: the model handles the year-only case.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    request = IngestRequest(source_key="pwt", year=2019)
    assert request.effective_years == (2019,)


def test_ingest_request_years_only_returns_sorted_unique() -> None:
    """``years=[2019, 2018]`` with ``year=None`` -> sorted unique.

    Contract: ``IngestRequest(years=(2019, 2018)).effective_years ==
    (2018, 2019)`` (sorted ascending; duplicates dropped).

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    request = IngestRequest(source_key="pwt", years=(2019, 2018))
    assert request.effective_years == (2018, 2019)


def test_ingest_request_both_set_consistent_keeps_years() -> None:
    """``year in years`` -> ``effective_years`` is the years tuple.

    Contract: when both ``year`` and ``years`` are set AND the
    single ``year`` is contained in ``years``, ``effective_years``
    returns the explicit ``years`` tuple (sorted, deduplicated).

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    request = IngestRequest(source_key="pwt", year=2019, years=(2018, 2019))
    assert request.effective_years == (2018, 2019)


def test_ingest_request_both_set_disagree_raises_validation_error() -> None:
    """``year=2020`` with ``years=(2018, 2019)`` (year not in years)
    -> ``ValidationError`` at request construction time.

    Contract: when both ``year`` and ``years`` are set AND the
    single ``year`` is NOT contained in ``years``, the request
    fails validation. This prevents an adapter from silently
    receiving a year filter that contradicts the years list.

    PASS-ELIGIBLE: the model validator rejects inconsistent
    year / years pairs.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    with pytest.raises(ValidationError):
        IngestRequest(source_key="pwt", year=2020, years=(2018, 2019))


def test_ingest_request_years_dedupe_and_sort() -> None:
    """``years`` is sorted ascending and duplicates are dropped.

    Contract: passing ``years=(2019, 2018, 2019, 2020, 2018)``
    normalizes to ``(2018, 2019, 2020)``.

    PASS-ELIGIBLE: the model normalizes ``years`` deterministically;
    the Phase B stub satisfies this contract.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    request = IngestRequest(
        source_key="pwt", years=(2019, 2018, 2019, 2020, 2018),
    )
    assert request.effective_years == (2018, 2019, 2020)


# ---------------------------------------------------------------------------
# IngestRequest durable fields (country_filter / raw_root / processed_root
# / database_url / force_refresh / allow_network)
# ---------------------------------------------------------------------------


def test_ingest_request_country_filter_roundtrips() -> None:
    """``IngestRequest.country_filter`` carries the supplied ISO3
    tuple unchanged (no normalization in the stub).

    PASS-ELIGIBLE: the field is part of the typed request
    contract; the stub round-trips it. Future production work
    that adds normalization (e.g. uppercase ISO3) must update
    this test.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    request = IngestRequest(
        source_key="pwt", country_filter=("MEX", "USA"),
    )
    assert request.country_filter == ("MEX", "USA")


def test_ingest_request_country_filter_default_is_empty_tuple() -> None:
    """``country_filter`` defaults to ``()`` (no country filter).

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    request = IngestRequest(source_key="pwt")
    assert request.country_filter == ()


def test_ingest_request_raw_root_and_processed_root_roundtrip() -> None:
    """``raw_root`` / ``processed_root`` round-trip through the
    request model.

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    raw = Path("/tmp/raw")
    processed = Path("/tmp/processed")
    request = IngestRequest(
        source_key="pwt",
        raw_root=raw,
        processed_root=processed,
    )
    assert request.raw_root == raw
    assert request.processed_root == processed


def test_ingest_request_database_url_roundtrips() -> None:
    """``database_url`` round-trips through the request model.

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    request = IngestRequest(
        source_key="pwt", database_url="sqlite:///test.db",
    )
    assert request.database_url == "sqlite:///test.db"


def test_ingest_request_force_refresh_default_false_and_true() -> None:
    """``force_refresh`` defaults to ``False``; setting it to
    ``True`` is preserved.

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    assert IngestRequest(source_key="pwt").force_refresh is False
    assert (
        IngestRequest(source_key="pwt", force_refresh=True).force_refresh
        is True
    )


def test_ingest_request_allow_network_default_false_and_true() -> None:
    """``allow_network`` defaults to ``False`` (Stage 2 is
    local-first per ``docs/local-data-store.md``); setting it to
    ``True`` is preserved.

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import IngestRequest

    assert IngestRequest(source_key="pwt").allow_network is False
    assert (
        IngestRequest(source_key="pwt", allow_network=True).allow_network
        is True
    )


# ---------------------------------------------------------------------------
# SourceReadiness
# ---------------------------------------------------------------------------


def test_source_readiness_missing_metadata_blocks() -> None:
    """``SourceReadiness(ready=False, blocker=...)`` is the
    representation for "metadata missing; do not read the raw
    bundle".

    Contract: when an adapter's ``check_ready()`` finds the
    bundle's ``metadata.json`` absent, it returns a
    ``SourceReadiness`` with ``ready=False`` and a non-empty
    ``blocker`` string. The registry runner must refuse to call
    ``read()`` when ``ready=False``.

    PASS-ELIGIBLE: ``SourceReadiness`` is a dataclass with the
    documented fields; the model satisfies the contract.
    """
    from leaders_db.ingest.interfaces import SourceReadiness

    readiness = SourceReadiness(
        ready=False,
        blocker="metadata.json missing at data/raw/pwt/",
    )
    assert readiness.ready is False
    assert readiness.blocker
    assert "metadata" in readiness.blocker.lower()


def test_source_adapter_protocol_includes_ingest_method() -> None:
    """The :class:`SourceAdapter` Protocol includes
    ``check_ready``, ``read``, ``transform``, ``write``, AND
    ``ingest``.

    Per the source-ingestion-plan Increment A design, the
    convenience ``ingest`` method wraps the full pipeline on
    a single adapter instance; the registry runner is the
    primary entry point. The Protocol MUST list ``ingest``
    so a class claiming to implement ``SourceAdapter`` (via
    ``runtime_checkable``) is forced to provide it.

    The test builds a minimal adapter that implements all five
    methods and asserts it satisfies the Protocol. A class
    that omits ``ingest`` fails the ``isinstance`` check
    (the Protocol is ``runtime_checkable``).

    PASS-ELIGIBLE: the contract surface is part of the
    public Phase A stub; the test does not depend on
    production adapter behavior.
    """
    from leaders_db.ingest.interfaces import (
        IngestRequest,
        IngestResult,
        NormalizedSourceFrame,
        RawSourceBundle,
        SourceAdapter,
        SourceReadiness,
    )

    class _FiveMethodAdapter:
        """Minimal adapter that implements all 5 Protocol methods.

        Per the Increment A protocol revision, ``check_ready``
        receives the :class:`IngestRequest` so the readiness
        gate can resolve request-scoped ``raw_root`` overrides.
        The fake adapter records the ``request.raw_root`` so
        the protocol test can assert the runner passed it.
        """

        source_key = "five_method_test"

        def __init__(self) -> None:
            self.last_request: IngestRequest | None = None
            self.last_raw_root: object = None

        def check_ready(self, request: IngestRequest) -> SourceReadiness:
            self.last_request = request
            self.last_raw_root = request.raw_root
            return SourceReadiness(ready=True, blocker=None)

        def read(self, request: IngestRequest) -> RawSourceBundle:
            return RawSourceBundle(source_key=self.source_key, payload={})

        def transform(
            self,
            bundle: RawSourceBundle,
            request: IngestRequest,
        ) -> NormalizedSourceFrame:
            return NormalizedSourceFrame(
                source_key=bundle.source_key, rows=(),
            )

        def write(
            self,
            frame: NormalizedSourceFrame,
            request: IngestRequest,
        ) -> IngestResult:
            return IngestResult(
                source_key=frame.source_key,
                years=request.effective_years,
            )

        def ingest(self, request: IngestRequest) -> IngestResult:
            # Convenience method: drive the full pipeline.
            readiness = self.check_ready(request)
            if not readiness.ready:
                raise RuntimeError(readiness.blocker or "not ready")
            bundle = self.read(request)
            frame = self.transform(bundle, request)
            return self.write(frame, request)

    adapter = _FiveMethodAdapter()
    # ``runtime_checkable`` Protocol allows isinstance() to
    # verify the class implements the full set of methods.
    assert isinstance(adapter, SourceAdapter), (
        "SourceAdapter Protocol requires check_ready + read + "
        "transform + write + ingest"
    )

    # The convenience ``ingest`` method also works end-to-end.
    result = adapter.ingest(
        IngestRequest(source_key="five_method_test", year=2023)
    )
    assert isinstance(result, IngestResult)
    assert result.source_key == "five_method_test"
    assert result.years == (2023,)


def test_ingest_result_round_trips_manifest_path_warnings_attribution() -> None:
    """``IngestResult`` (Pydantic) round-trips the durable
    Phase B fields ``manifest_path``, ``warnings``, and
    ``attribution``.

    Per the source-ingestion-plan Increment A design, the
    end-of-run summary carries:

    - ``manifest_path`` -- the run-manifest JSON path the
      writer emits; ``None`` until the production writer
      lands.
    - ``warnings`` -- a tuple of structured warning dicts
      (e.g. ``{"code": "requested_year_out_of_coverage", ...}``)
      the runner surfaces in the CLI end-of-run echo.
    - ``attribution`` -- the canonical citation text
      (Rule #15) the runner surfaces in the CLI end-of-run
      echo.

    The default values are ``None``, ``()``, ``None``; the
    test exercises all three default paths AND the
    round-trip path.

    PASS-ELIGIBLE: the contract surface is part of the
    public Phase A stub; the test does not depend on
    production adapter behavior.
    """
    from leaders_db.ingest.interfaces import IngestResult

    # Defaults.
    result = IngestResult(source_key="pwt")
    assert result.manifest_path is None
    assert result.warnings == ()
    assert result.attribution is None

    # Round-trip with concrete values.
    manifest = Path("/tmp/run_manifest.json")
    result2 = IngestResult(
        source_key="pwt",
        manifest_path=manifest,
        warnings=({"code": "requested_year_out_of_coverage", "year": 2023},),
        attribution="Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015).",
    )
    assert result2.manifest_path == manifest
    assert len(result2.warnings) == 1
    assert result2.warnings[0]["code"] == "requested_year_out_of_coverage"
    assert result2.warnings[0]["year"] == 2023
    assert "Feenstra" in result2.attribution


def test_ingest_result_validates_non_negative_counts() -> None:
    """``IngestResult`` (Pydantic) rejects negative counts.

    Contract: ``source_id``, ``observation_rows``, ``countries``,
    and ``indicators`` are all non-negative integers. The Pydantic
    ``Field(..., ge=0)`` validator raises ``ValidationError`` on
    negative inputs.

    PASS-ELIGIBLE: the Pydantic validators are part of the
    public Phase A stub contract.
    """
    from leaders_db.ingest.interfaces import IngestResult

    # Negative observation_rows: rejected.
    with pytest.raises(ValidationError):
        IngestResult(source_key="pwt", observation_rows=-1)
    # Negative source_id: rejected.
    with pytest.raises(ValidationError):
        IngestResult(source_key="pwt", source_id=-1)
    # Negative countries: rejected.
    with pytest.raises(ValidationError):
        IngestResult(source_key="pwt", countries=-1)
    # Negative indicators: rejected.
    with pytest.raises(ValidationError):
        IngestResult(source_key="pwt", indicators=-1)


def test_ingest_result_validates_years_are_sorted_unique_ints() -> None:
    """``IngestResult`` (Pydantic) rejects unsorted / duplicate
    ``years`` entries.

    PASS-ELIGIBLE: the validator is part of the Phase A stub.
    """
    from leaders_db.ingest.interfaces import IngestResult

    # Unsorted.
    with pytest.raises(ValidationError):
        IngestResult(source_key="pwt", years=(2019, 2018))
    # Duplicate.
    with pytest.raises(ValidationError):
        IngestResult(source_key="pwt", years=(2018, 2018))


def test_source_readiness_ready_carries_attribution() -> None:
    """A ready ``SourceReadiness`` may carry an attribution block
    (Rule #15).

    Contract: when ``ready=True`` the readiness payload surfaces
    enough provenance to attribute downstream output (e.g. the
    canonical citation text from ``docs/source-attributions.md``).

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest.interfaces import SourceReadiness

    readiness = SourceReadiness(
        ready=True,
        blocker=None,
        attribution=(
            "Penn World Table 10.01 (Feenstra, Inklaar, Timmer 2015)."
        ),
    )
    assert readiness.ready is True
    assert readiness.blocker is None
    assert readiness.attribution


__all__ = []
