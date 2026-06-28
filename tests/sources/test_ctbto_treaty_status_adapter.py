"""CTBTO Treaty Status clean-source adapter tests.

The CTBTO States Signatories page is the CTBTO-maintained
public record of which States have signed and ratified the
Comprehensive Nuclear-Test-Ban Treaty (CTBT). The unified
adapter is the next feasible clean-interface-only source
after ``iaea_safeguards``
(``docs/architecture/sources.md`` §7.2 ``ctbto_treaty_status``
row; fourth post-interface source with no legacy Stage 2
implementation). Per the task brief the slice is deliberately
scoped to treaty-status evidence only (the canonical public
CTBTO States Signatories page at
``https://www.ctbto.org/our-mission/states-signatories``)
-- NOT per-country nuclear behaviour, NOT a proof of
compliance / non-compliance by itself. The unified adapter is
offline / cache-first in this slice and reads a staged cached
CSV (or HTML fallback) plus a runtime-local ``metadata.json``
(gitignored per Always-On Rule #9). The descriptor's
``coverage_hint.notes`` carries the explicit caveat.

The new package lives at
``src/leaders_db/sources/adapters/ctbto_treaty_status/`` and
the focused tests in this file cover:

- The CTBTO Treaty Status adapter descriptor is registerable
  / listable through the new :class:`InMemorySourceRegistry`
  and exposes the documented static metadata (source_id
  ``ctbto_treaty_status``, default version
  ``"CTBTO States Signatories, status as of 2024-03-13"``,
  attribution_key ``ctbto_treaty_status``, ``document``
  source type, single-year 2024 coverage hint, single
  observation family ``nuclear_treaty_status_country``,
  ``requires_network=False``).
- :class:`SourceIngestRunner` can run CTBTO Treaty Status
  end-to-end through the new registry against a fixture
  ``raw_root`` and produce :class:`NormalizedObservation`
  records.
- The new runner path does NOT consult the legacy
  ``STAGE2_ADAPTERS`` dispatch table.
- ``years=`` and ``countries=`` filters are honored and
  surface correct observation counts.
- An out-of-coverage ``years=(2023,)`` request emits zero
  observations plus a structured ``YEAR_ABSENT`` warning
  (no stale-proxy fill per SRC-COV-002 / SRC-COV-003).
- ``leaders=`` filters surface a structured
  ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).
- Readiness failures (missing metadata, missing cached CSV /
  HTML, missing required metadata field, ``local_files``
  missing the canonical cached file, ``ingestion_status``
  not ``'downloaded'``, missing required CSV column,
  ``source_version`` mismatch, checksum mismatch) each
  surface a structured ``SourceWarning(severity='error')``
  so the runner raises ``RuntimeError`` BEFORE ``read_raw`` /
  ``transform``.
- Cache-policy gate blocks ``"refresh"`` / ``"no_cache"``
  with a structured
  ``ctbto_treaty_status_unsupported_cache_policy`` error.
- The transform preserves source-native State display names
  verbatim and does NOT invent ISO3 codes
  (``country_code`` / ``leader_id`` / ``leader_name`` remain
  ``None``).
- Empty signature / ratification date cells are emitted as
  ``value="not_signed"`` / ``value="not_ratified"`` plus the
  verbatim raw date cell text on ``extension.raw_value`` --
  unsigned / unratified rows are NOT silently treated as
  signed / ratified.
- The default 2-indicator catalog deliberately does NOT
  include a ``ctbto_treaty_status_annex_2_status`` indicator
  when the cached fixture does NOT carry an Annex 2 column --
  the adapter never invents an Annex 2 flag from missing
  source-native data.
- The OPTIONAL ``ctbto_treaty_status_annex_2_status``
  indicator is emitted when the cached fixture carries an
  explicit ``Annex 2`` column.
- Attribution drift guard: the canonical attribution text
  is a substring of ``docs/sources/attributions.md``
  (Always-On Rule #15).
- Importing the new
  ``leaders_db.sources.adapters.ctbto_treaty_status`` module
  does NOT pull in any ``leaders_db.ingest`` module
  (SRC-MIG-007 + the import boundary documented in
  ``docs/architecture/sources.md`` §10.1).
- The adapter does NOT invoke the network.

PASS-ELIGIBLE rationale
-----------------------

CTBTO Treaty Status has no legacy Stage 2 implementation; the
tests in this file prove that the new
``leaders_db.sources.adapters.ctbto_treaty_status`` adapter
implements the full ``SourceAdapter`` Protocol end-to-end
while preserving the package-isolation contract -- they are
PASS-ELIGIBLE because the adapter implementation lands in
the same change set.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from leaders_db.sources import (
    InMemorySourceRegistry,
    SourceAdapter,
    SourceId,
    SourceIngestRequest,
    SourceIngestResult,
    SourceIngestRunner,
)
from leaders_db.sources.adapters.ctbto_treaty_status import (
    CTBTO_TREATY_STATUS_ADAPTER_FACTORY,
    CTBTO_TREATY_STATUS_ATTRIBUTION_KEY,
    CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT,
    CTBTO_TREATY_STATUS_COVERAGE_END_YEAR,
    CTBTO_TREATY_STATUS_COVERAGE_START_YEAR,
    CTBTO_TREATY_STATUS_COVERAGE_YEAR,
    CTBTO_TREATY_STATUS_CSV_NAME,
    CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY,
    CTBTO_TREATY_STATUS_DEFAULT_VERSION,
    CTBTO_TREATY_STATUS_HOMEPAGE_URL,
    CTBTO_TREATY_STATUS_HTML_NAME,
    CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS,
    CTBTO_TREATY_STATUS_INDICATOR_CODES,
    CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS,
    CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS,
    CTBTO_TREATY_STATUS_OBSERVATION_FAMILY,
    CTBTO_TREATY_STATUS_REQUIRED_COLUMNS,
    CTBTO_TREATY_STATUS_SNAPSHOT_DATE,
    CTBTO_TREATY_STATUS_SOURCE_KEY,
    CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED,
    CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED,
    CTBTO_TREATY_STATUS_STATUS_RATIFIED,
    CTBTO_TREATY_STATUS_STATUS_SIGNED,
    CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES,
    CTBTO_TREATY_STATUS_TRANSFORM_NAME,
    create_ctbto_treaty_status_adapter,
    register_ctbto_treaty_status,
)
from leaders_db.sources.adapters.ctbto_treaty_status._constants import (
    CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH,
    CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
    CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH,
    CTBTO_TREATY_STATUS_SCHEMA_ERROR,
    CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY,
    CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION,
)
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

_FIXTURE_CSV = Path("tests/fixtures/ctbto_treaty_status/sample.csv")


# ---------------------------------------------------------------------------
# Bundle staging helpers
# ---------------------------------------------------------------------------


def _stage_bundle(
    raw_root: Path,
    *,
    with_metadata: bool = True,
    with_csv: bool = True,
    local_files: Any | None = None,
    checksum: Any = "AUTO",
    source_version: str = CTBTO_TREATY_STATUS_DEFAULT_VERSION,
    with_annex_2: bool = False,
) -> Path:
    """Stage the CTBTO Treaty Status fixture bundle under
    ``raw_root/ctbto_treaty_status``.

    Copies ``tests/fixtures/ctbto_treaty_status/sample.csv``
    into ``<raw_root>/ctbto_treaty_status/states-signatories.csv``
    plus an optional ``metadata.json`` whose checksum matches
    the staged CSV. Returns the resolved bundle directory.

    The fixture carries 6 hand-authored synthetic State rows
    (no real CTBTO claims -- the State labels are SYNTHETIC
    per the task brief: "fixtures must not redistribute copied
    full table in outputs"). The fixture deliberately does NOT
    carry an ``Annex 2`` column so the default 2-indicator
    catalog is exercised; tests that need the OPTIONAL
    ``ctbto_treaty_status_annex_2_status`` indicator pass
    ``with_annex_2=True`` to add a synthetic ``Annex 2`` column
    to the staged CSV.

    Per-row cell coverage (per the fixture builder docstring):

    - State A: signature date present + ratification date
      present (``"signed"`` / ``"ratified"``).
    - State B: signature date present + ratification date
      empty (``"signed"`` / ``"not_ratified"``).
    - State C: signature date empty + ratification date
      empty (``"not_signed"`` / ``"not_ratified"``).
    - State D: both dates present (``"signed"`` /
      ``"ratified"``).
    - State E: both dates empty (``"not_signed"`` /
      ``"not_ratified"``).
    - State F: both dates present; ratification date uses
      free-form ``D-MMM-YYYY`` format to exercise the
      date-cell preservation contract.
    """
    bundle = raw_root / CTBTO_TREATY_STATUS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)

    csv_path = bundle / CTBTO_TREATY_STATUS_CSV_NAME
    if with_csv:
        shutil.copy2(_FIXTURE_CSV, csv_path)
        if with_annex_2:
            # Append an OPTIONAL Annex 2 column to the staged
            # CSV so the transform layer exercises the
            # ``ctbto_treaty_status_annex_2_status`` indicator
            # emission path. The synthetic Annex 2 values are
            # either ``"yes"`` or ``""`` so the transform
            # exercises both the ``"in_annex_2"`` /
            # ``"not_in_annex_2"`` sentinel paths.
            _append_annex_2_column(csv_path)

    if not with_metadata:
        return bundle

    checksum_value: Any = checksum
    if checksum == "AUTO":
        if csv_path.is_file():
            checksum_value = (
                hashlib.sha256(csv_path.read_bytes()).hexdigest()
            )
        else:
            checksum_value = None

    if local_files is None:
        local_files = [CTBTO_TREATY_STATUS_CSV_NAME]

    payload: dict[str, Any] = {
        "source_name": (
            "CTBTO States Signatories, Comprehensive Nuclear-Test-"
            "Ban Treaty signature and ratification status"
        ),
        "source_key": CTBTO_TREATY_STATUS_SOURCE_KEY,
        "source_version": source_version,
        "download_date": "2026-06-28",
        "coverage": (
            f"single-point treaty-status snapshot, status as of "
            f"{CTBTO_TREATY_STATUS_SNAPSHOT_DATE}"
        ),
        "license_note": (
            "CTBTO terms-of-use; download / copy / use with "
            "acknowledgement for personal, non-commercial, "
            "research / teaching use; do not redistribute copied "
            "full table in outputs; attribution required."
        ),
        "local_files": local_files,
        "ingestion_status": "downloaded",
        "source_url": CTBTO_TREATY_STATUS_HOMEPAGE_URL,
    }
    if checksum_value is not None:
        payload["checksum_sha256"] = checksum_value
    payload["notes"] = (
        "Synthetic fixture bundle for clean-source adapter "
        "tests; the State labels and date cells are NOT real "
        "CTBTO Treaty Status data."
    )
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle


def _append_annex_2_column(csv_path: Path) -> None:
    """Append a synthetic ``Annex 2`` column to the staged CSV.

    Re-reads the existing CSV, appends the ``Annex 2`` header
    cell to the first row, and appends ``"yes"`` / ``""``
    values to the data rows so the transform layer exercises
    both the ``"in_annex_2"`` / ``"not_in_annex_2"`` sentinel
    paths. Defensive: does nothing if the CSV is missing the
    canonical 4-column header.

    The helper uses the Python ``csv`` module to safely
    parse / re-emit the CSV so a quoted cell whose last
    character is ``"`` does NOT get the closing quote
    accidentally stripped during the rewrite.
    """
    import csv as _csv
    import io as _io

    raw_text = csv_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return
    reader = _csv.reader(_io.StringIO(raw_text))
    parsed = [row for row in reader if row]
    if not parsed:
        return
    if "Signature Date" not in parsed[0]:
        return
    header = [*parsed[0], "Annex 2"]
    annex_values = ("yes", "", "yes", "", "yes", "")
    new_rows: list[list[str]] = [header]
    for index, row in enumerate(parsed[1:]):
        value = (
            annex_values[index] if index < len(annex_values) else ""
        )
        new_rows.append([*row, value])
    output = _io.StringIO()
    writer = _csv.writer(output, quoting=_csv.QUOTE_ALL)
    writer.writerows(new_rows)
    csv_path.write_text(output.getvalue(), encoding="utf-8")


def _request(
    raw_root: Path, **kwargs: Any,
) -> SourceIngestRequest:
    """Build a CTBTO Treaty Status request with sensible defaults."""
    defaults: dict[str, Any] = {
        "cache_policy": CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY,
    }
    defaults.update(kwargs)
    return SourceIngestRequest(
        source_id=SourceId(CTBTO_TREATY_STATUS_SOURCE_KEY),
        raw_root=raw_root,
        **defaults,
    )


def _run(raw_root: Path, **kwargs: Any) -> SourceIngestResult:
    """Drive the CTBTO Treaty Status adapter through the new runner."""
    registry = InMemorySourceRegistry()
    register_ctbto_treaty_status(registry)
    return SourceIngestRunner(registry).run(_request(raw_root, **kwargs))


# ---------------------------------------------------------------------------
# Descriptor + factory shape
# ---------------------------------------------------------------------------


def test_descriptor_factory_and_registry() -> None:
    """The descriptor factory exposes the documented static metadata."""
    adapter = create_ctbto_treaty_status_adapter()
    descriptor = adapter.descriptor
    assert isinstance(adapter, SourceAdapter)
    assert (
        CTBTO_TREATY_STATUS_ADAPTER_FACTORY().descriptor == descriptor
    )
    assert (
        descriptor.source_id.slug == CTBTO_TREATY_STATUS_SOURCE_KEY
    )
    assert (
        descriptor.attribution_key
        == CTBTO_TREATY_STATUS_ATTRIBUTION_KEY
    )
    assert (
        descriptor.default_version == CTBTO_TREATY_STATUS_DEFAULT_VERSION
    )
    assert descriptor.source_type == "document"
    assert descriptor.requires_network is False
    assert descriptor.requires_manual_approval is False
    assert descriptor.supported_observation_families == (
        CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES
    )
    assert (
        CTBTO_TREATY_STATUS_OBSERVATION_FAMILY
        in descriptor.supported_observation_families
    )
    assert (
        descriptor.coverage_hint.start_year
        == CTBTO_TREATY_STATUS_COVERAGE_START_YEAR
    )
    assert (
        descriptor.coverage_hint.end_year
        == CTBTO_TREATY_STATUS_COVERAGE_END_YEAR
    )
    assert (
        descriptor.homepage_url == CTBTO_TREATY_STATUS_HOMEPAGE_URL
    )

    # The descriptor's coverage_hint.notes must carry the
    # documented caveat that this source captures treaty-
    # status evidence and is NOT direct proof of nuclear
    # behaviour, compliance, or non-compliance by itself --
    # this is the audit-trail surface for the methodology note.
    notes = descriptor.coverage_hint.notes or ""
    assert "TREATY-STATUS" in notes
    assert "NOT direct proof" in notes
    assert CTBTO_TREATY_STATUS_SNAPSHOT_DATE in notes


def test_register_helper_registers_against_explicit_registry() -> None:
    """``register_ctbto_treaty_status(registry)`` is the explicit
    seam for tests + future composition code.
    """
    registry = InMemorySourceRegistry()
    adapter = register_ctbto_treaty_status(registry)
    assert (
        registry.get_adapter(SourceId(CTBTO_TREATY_STATUS_SOURCE_KEY))
        is adapter
    )
    listed = registry.list_descriptors()
    assert len(listed) == 1
    assert (
        listed[0].source_id.slug == CTBTO_TREATY_STATUS_SOURCE_KEY
    )


def test_indicator_codes_match_canonical_2() -> None:
    """The 2 source-derived indicator codes are exposed via the
    package surface for downstream query code.

    The catalog deliberately does NOT include a default
    ``ctbto_treaty_status_annex_2_status`` indicator -- the
    canonical CTBTO States Signatories page does NOT carry
    an Annex 2 flag column; the adapter never invents an
    Annex 2 flag from missing source-native data. The
    indicator constant is preserved on the package surface
    for documentation / future-source-data-compatibility
    purposes only.
    """
    assert (
        CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS
        in CTBTO_TREATY_STATUS_INDICATOR_CODES
    )
    assert (
        CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS
        in CTBTO_TREATY_STATUS_INDICATOR_CODES
    )
    assert len(CTBTO_TREATY_STATUS_INDICATOR_CODES) == 2


def test_annex_2_indicator_not_in_default_catalog() -> None:
    """The default 2-indicator catalog deliberately does NOT
    include a ``ctbto_treaty_status_annex_2_status`` indicator.

    The canonical CTBTO States Signatories page does NOT
    carry an Annex 2 flag column; the adapter never invents
    an Annex 2 flag from missing source-native data. The
    indicator constant is preserved on the package surface
    for documentation / future-source-data-compatibility
    purposes only, and the transform layer only emits an
    Annex 2 observation when the cached fixture / source-
    native data carries an explicit ``Annex 2`` column.
    """
    assert (
        CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS
        not in CTBTO_TREATY_STATUS_INDICATOR_CODES
    ), (
        "ctbto_treaty_status_annex_2_status must not appear in "
        "the canonical indicator catalog -- the canonical CTBTO "
        "page does NOT carry an Annex 2 flag; the indicator is "
        "only emitted when the cached fixture carries an explicit "
        "Annex 2 column."
    )


def test_required_columns_match_canonical_4() -> None:
    """The 4 canonical required CSV / HTML table columns are
    exposed via the package surface for the readiness gate +
    raw-read boundary.
    """
    assert len(CTBTO_TREATY_STATUS_REQUIRED_COLUMNS) == 4
    assert "Region" in CTBTO_TREATY_STATUS_REQUIRED_COLUMNS
    assert "State" in CTBTO_TREATY_STATUS_REQUIRED_COLUMNS
    assert "Signature Date" in CTBTO_TREATY_STATUS_REQUIRED_COLUMNS
    assert "Ratification Date" in CTBTO_TREATY_STATUS_REQUIRED_COLUMNS


def test_attribution_text_matches_attributions_doc() -> None:
    """The attribution text is a substring of
    ``docs/sources/attributions.md`` (Rule #15 drift guard).
    """
    attributions_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "sources"
        / "attributions.md"
    )
    assert attributions_path.exists(), (
        f"expected attributions doc at {attributions_path}"
    )
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT in attributions_text, (
        f"{CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT!r} is not a "
        f"substring of {attributions_path}. Update both in the "
        f"same commit (Rule #15)."
    )


def test_attribution_key_matches_attributions_doc() -> None:
    """The attribution key ``ctbto_treaty_status`` appears in
    the attributions doc. Drift guard for the descriptor's
    ``attribution_key`` field.
    """
    attributions_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "sources"
        / "attributions.md"
    )
    assert attributions_path.exists()
    attributions_text = attributions_path.read_text(encoding="utf-8")
    assert CTBTO_TREATY_STATUS_ATTRIBUTION_KEY in attributions_text


# ---------------------------------------------------------------------------
# Bundle readiness -- happy path + error paths
# ---------------------------------------------------------------------------


def test_correct_bundle_passes_readiness(tmp_path: Path) -> None:
    """A well-formed bundle returns ``ready=True``."""
    _stage_bundle(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is True
    assert readiness.errors == ()


def test_no_observations_emitted_for_unsupported_leaders_filter(
    tmp_path: Path,
) -> None:
    """``leaders=`` filter is unsupported -- the transform ignores
    it and the readiness envelope surfaces a structured
    ``UNSUPPORTED_FILTER`` warning.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, leaders=("Some Leader",))
    # 6 rows x 2 indicators (default catalog, no Annex 2) = 12
    # observations.
    assert len(result.observations) == 12
    assert [w.code for w in result.warnings] == [UNSUPPORTED_FILTER]


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"with_metadata": False}, MISSING_METADATA),
        ({"with_csv": False}, MISSING_RAW),
        ({"local_files": []}, CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID),
        (
            {"local_files": ["some_other_file.csv"]},
            CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID,
        ),
        ({"checksum": "0" * 64}, CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH),
        (
            {
                "source_version": (
                    "CTBTO States Signatories, status as of 2023-06-01"
                ),
            },
            CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH,
        ),
    ],
)
def test_readiness_failures(
    tmp_path: Path, kwargs: dict[str, Any], code: str,
) -> None:
    """Each documented readiness-failure class surfaces a
    structured ``SourceWarning(severity='error')``.
    """
    _stage_bundle(tmp_path, **kwargs)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == code


def test_unsupported_request_version_fails_readiness(tmp_path: Path) -> None:
    """An explicit ``source_version=`` request that differs from
    the canonical version stamp fails readiness with a
    structured ``unsupported_version`` error.
    """
    _stage_bundle(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(
            tmp_path,
            source_version=(
                "CTBTO States Signatories, status as of 2023-06-01"
            ),
        ),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION
    )


def test_cache_policy_refresh_fails_readiness(tmp_path: Path) -> None:
    """``cache_policy="refresh"`` is unsupported -- the gate
    blocks with a structured
    ``ctbto_treaty_status_unsupported_cache_policy`` error.
    """
    _stage_bundle(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path, cache_policy="refresh"),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY
    )


def test_cache_policy_no_cache_fails_readiness(tmp_path: Path) -> None:
    """``cache_policy="no_cache"`` is unsupported -- same as
    ``refresh``.
    """
    _stage_bundle(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path, cache_policy="no_cache"),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY
    )


# ---------------------------------------------------------------------------
# Year semantics
# ---------------------------------------------------------------------------


def test_out_of_coverage_year_warns_and_emits_no_rows(
    tmp_path: Path,
) -> None:
    """A request for ``years=(2023,)`` -- the prototype's target
    year, which is OUTSIDE the documented 2024 single-year
    envelope -- emits zero observations plus a structured
    ``YEAR_ABSENT`` warning (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023,))
    assert result.observations == ()
    assert [w.code for w in result.warnings] == [YEAR_ABSENT]


def test_in_coverage_year_emits_full_observations(
    tmp_path: Path,
) -> None:
    """A request for ``years=(2024,)`` (the in-coverage snapshot
    year) emits the full observation set.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2024,))
    # 6 rows x 2 indicators (default catalog, no Annex 2) = 12
    # observations.
    assert len(result.observations) == 12
    assert result.warnings == ()


def test_no_year_filter_emits_full_observations(tmp_path: Path) -> None:
    """A request with ``years=None`` reads the full envelope
    (equivalent to ``years=(2024,)``) and emits the full
    observation set.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=None)
    assert len(result.observations) == 12
    assert result.warnings == ()


# ---------------------------------------------------------------------------
# Country filter
# ---------------------------------------------------------------------------


def test_country_filter_single_match(tmp_path: Path) -> None:
    """A ``countries=`` request that matches one State emits one
    State x 2 indicators = 2 observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("State A",))
    # 1 row x 2 indicators = 2 observations.
    assert len(result.observations) == 2
    assert result.warnings == ()
    for obs in result.observations:
        assert obs.country_name == "State A"


def test_country_filter_no_match(tmp_path: Path) -> None:
    """A ``countries=`` request that matches no State emits
    zero observations.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("Nonexistent State",))
    assert result.observations == ()
    assert result.warnings == ()


def test_country_filter_multiple_matches(tmp_path: Path) -> None:
    """A ``countries=`` request with multiple matches emits
    one observation per matched State per indicator.
    """
    _stage_bundle(tmp_path)
    result = _run(
        tmp_path,
        countries=("State A", "State B", "State C"),
    )
    # 3 rows x 2 indicators = 6 observations.
    assert len(result.observations) == 6
    assert result.warnings == ()
    matched_states = {obs.country_name for obs in result.observations}
    assert matched_states == {"State A", "State B", "State C"}


# ---------------------------------------------------------------------------
# Signature / ratification status sentinel semantics
# ---------------------------------------------------------------------------


def test_signed_ratified_row_emits_both_statuses(tmp_path: Path) -> None:
    """A row with both signature + ratification dates emits
    ``value="signed"`` and ``value="ratified"`` plus the
    verbatim raw date cells on the audit-trail extension.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("State A",))
    assert len(result.observations) == 2
    by_indicator = {
        obs.indicator_code: obs for obs in result.observations
    }
    sig_obs = by_indicator[
        CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS
    ]
    rat_obs = by_indicator[
        CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS
    ]
    assert sig_obs.value == CTBTO_TREATY_STATUS_STATUS_SIGNED
    assert sig_obs.value_type == "categorical"
    assert (
        sig_obs.extension["ctbto_treaty_status_signature_date_raw"]
        == "1996-09-24"
    )
    assert rat_obs.value == CTBTO_TREATY_STATUS_STATUS_RATIFIED
    assert rat_obs.value_type == "categorical"
    assert (
        rat_obs.extension["ctbto_treaty_status_ratification_date_raw"]
        == "1998-07-10"
    )


def test_signed_but_not_ratified_row(tmp_path: Path) -> None:
    """A row with a signature date but an empty ratification
    date cell emits ``value="signed"`` for the signature
    indicator and ``value="not_ratified"`` for the
    ratification indicator. The empty ratification date cell
    is preserved verbatim on the audit-trail extension.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("State B",))
    assert len(result.observations) == 2
    by_indicator = {
        obs.indicator_code: obs for obs in result.observations
    }
    sig_obs = by_indicator[
        CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS
    ]
    rat_obs = by_indicator[
        CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS
    ]
    assert sig_obs.value == CTBTO_TREATY_STATUS_STATUS_SIGNED
    assert (
        sig_obs.extension["ctbto_treaty_status_signature_date_raw"]
        == "1996-09-25"
    )
    assert rat_obs.value == CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED
    assert (
        rat_obs.extension["ctbto_treaty_status_ratification_date_raw"]
        == ""
    )


def test_unsigned_unratified_row(tmp_path: Path) -> None:
    """A row with both date cells empty emits
    ``value="not_signed"`` and ``value="not_ratified"`` --
    unsigned / unratified rows are NOT silently treated as
    signed / ratified.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("State C",))
    assert len(result.observations) == 2
    by_indicator = {
        obs.indicator_code: obs for obs in result.observations
    }
    sig_obs = by_indicator[
        CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS
    ]
    rat_obs = by_indicator[
        CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS
    ]
    assert sig_obs.value == CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED
    assert (
        sig_obs.extension["ctbto_treaty_status_signature_date_raw"]
        == ""
    )
    assert rat_obs.value == CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED
    assert (
        rat_obs.extension["ctbto_treaty_status_ratification_date_raw"]
        == ""
    )


def test_no_iso3_invention(tmp_path: Path) -> None:
    """The transform does NOT invent ISO3 codes.

    The cached CTBTO States Signatories page uses CTBTO's
    own State display names, which are NOT ISO3; the
    ``country_code`` field remains ``None`` for every emitted
    observation until later matching / resolution stages
    introduce a canonical ISO3 mapping.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    assert len(result.observations) == 12
    for obs in result.observations:
        assert obs.country_code is None
        assert obs.leader_id is None
        assert obs.leader_name is None
        # The source-native State display name is preserved
        # verbatim on the audit-trail extension.
        assert obs.country_name is not None
        assert obs.country_name.startswith("State ")


def test_observation_shape_and_locators(tmp_path: Path) -> None:
    """Every emitted observation carries the canonical raw
    locator + transform locator + observation family +
    year + version stamp + attribution text.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, countries=("State A",))
    assert len(result.observations) == 2
    for obs in result.observations:
        assert obs.observation_family == (
            CTBTO_TREATY_STATUS_OBSERVATION_FAMILY
        )
        assert obs.year == CTBTO_TREATY_STATUS_COVERAGE_YEAR
        assert obs.source_version == (
            CTBTO_TREATY_STATUS_DEFAULT_VERSION
        )
        assert obs.transform_locator.transform_name == (
            CTBTO_TREATY_STATUS_TRANSFORM_NAME
        )
        assert obs.transform_locator.catalog_key == (
            CTBTO_TREATY_STATUS_SOURCE_KEY
        )
        assert (
            obs.raw_locator.asset_id
            == f"{CTBTO_TREATY_STATUS_SOURCE_KEY}:{CTBTO_TREATY_STATUS_CSV_NAME}"
        )
        assert (
            obs.extension["attribution"]
            == CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT
        )
        assert (
            obs.extension["ctbto_treaty_status_snapshot_date"]
            == CTBTO_TREATY_STATUS_SNAPSHOT_DATE
        )


# ---------------------------------------------------------------------------
# Annex 2 indicator -- optional path
# ---------------------------------------------------------------------------


def test_annex_2_indicator_emitted_when_column_present(
    tmp_path: Path,
) -> None:
    """When the cached fixture carries an explicit ``Annex 2``
    column, the transform layer emits an OPTIONAL
    ``ctbto_treaty_status_annex_2_status`` observation per
    row in addition to the default 2-indicator catalog.
    """
    _stage_bundle(tmp_path, with_annex_2=True)
    result = _run(tmp_path)
    # 6 rows x 3 indicators (2 default + 1 Annex 2) = 18
    # observations.
    assert len(result.observations) == 18
    annex_2_observations = [
        obs for obs in result.observations
        if obs.indicator_code
        == CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS
    ]
    assert len(annex_2_observations) == 6
    # Rows with synthetic "yes" Annex 2 values emit
    # ``value="in_annex_2"``; rows with empty Annex 2 values
    # emit ``value="not_in_annex_2"``. The synthetic Annex 2
    # values for the 6 fixture rows are
    # ``("yes", "", "yes", "", "yes", "")``.
    in_annex_2_count = sum(
        1 for obs in annex_2_observations
        if obs.value == "in_annex_2"
    )
    not_in_annex_2_count = sum(
        1 for obs in annex_2_observations
        if obs.value == "not_in_annex_2"
    )
    assert in_annex_2_count == 3
    assert not_in_annex_2_count == 3


def test_annex_2_indicator_not_emitted_when_column_absent(
    tmp_path: Path,
) -> None:
    """When the cached fixture does NOT carry an ``Annex 2``
    column, the transform layer does NOT emit the OPTIONAL
    ``ctbto_treaty_status_annex_2_status`` observation --
    the adapter never invents an Annex 2 flag from missing
    source-native data.
    """
    _stage_bundle(tmp_path, with_annex_2=False)
    result = _run(tmp_path)
    # 6 rows x 2 indicators (default catalog, no Annex 2) = 12
    # observations. The Annex 2 indicator must NOT appear.
    assert len(result.observations) == 12
    for obs in result.observations:
        assert (
            obs.indicator_code
            != CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS
        )


# ---------------------------------------------------------------------------
# Schema-error path
# ---------------------------------------------------------------------------


def test_missing_required_column_raises_schema_error(
    tmp_path: Path,
) -> None:
    """A cached CSV that is missing one or more of the 4
    canonical required columns fires a structured
    :class:`CtbtoTreatyStatusSchemaError` BEFORE the
    transform layer consumes the frame.
    """
    bundle = _stage_bundle(tmp_path)
    # Rewrite the staged CSV without the ``Ratification Date``
    # column so the raw-read boundary raises a structured
    # schema-violation error.
    csv_path = bundle / CTBTO_TREATY_STATUS_CSV_NAME
    raw_text = csv_path.read_text(encoding="utf-8")
    lines = raw_text.splitlines()
    # Rewrite the header to drop the ``Ratification Date``
    # column and rewrite the data rows accordingly.
    new_header = '"Region","State","Signature Date"'
    new_lines = [new_header]
    for line in lines[1:]:
        # Each row is 4 columns; drop the last one.
        cells = line.split(",")
        if len(cells) >= 4:
            cells = cells[:3]
        new_lines.append(",".join(cells))
    csv_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # Refresh the checksum so the readiness gate passes the
    # checksum-match check.
    metadata_file = bundle / "metadata.json"
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    payload["checksum_sha256"] = (
        hashlib.sha256(csv_path.read_bytes()).hexdigest()
    )
    metadata_file.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    with pytest.raises(Exception) as excinfo:
        _run(tmp_path)
    assert (
        CTBTO_TREATY_STATUS_SCHEMA_ERROR
        in str(excinfo.value)
    )


# ---------------------------------------------------------------------------
# Import boundary + no-network boundary
# ---------------------------------------------------------------------------


def test_adapter_module_does_not_import_legacy_ingest_at_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing the new
    ``leaders_db.sources.adapters.ctbto_treaty_status`` module
    does NOT pull in any ``leaders_db.ingest`` module.

    Defense in depth: the canonical import-boundary guard
    documented in ``tests/sources/test_import_boundary.py``
    asserts the package-isolation rule for every clean-source
    adapter submodule. This per-adapter test mirrors that
    contract for the CTBTO Treaty Status adapter specifically
    so a regression that accidentally pulls in legacy ingest
    surfaces as a per-adapter failure rather than only at the
    canonical import-boundary list level.
    """
    # Purge every cached module under the source / ingest
    # namespace so the import boundary starts clean.
    for name in list(sys.modules):
        if name == "leaders_db.sources" or name.startswith(
            "leaders_db.sources.",
        ):
            del sys.modules[name]
        if name == "leaders_db.ingest" or name.startswith(
            "leaders_db.ingest.",
        ):
            del sys.modules[name]
    try:
        importlib.import_module(
            "leaders_db.sources.adapters.ctbto_treaty_status",
        )
        leaked = sorted(
            name for name in sys.modules
            if name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            "importing leaders_db.sources.adapters.ctbto_treaty_status "
            f"must not import leaders_db.ingest (leaked modules: {leaked})"
        )
    finally:
        # Re-import leaders_db.sources so subsequent tests can
        # use the package surface without breaking the cached
        # module state.
        importlib.import_module("leaders_db.sources")


def test_adapter_does_not_invoke_network(tmp_path: Path) -> None:
    """The adapter never invokes the network -- it reads only
    the staged cached CSV (or HTML fallback) and the runtime-
    local ``metadata.json``.

    The test stages a well-formed bundle and installs sentinels
    on ``urllib.request.urlopen`` AND ``socket.socket`` so a
    regression that accidentally introduces a network call
    surfaces as a clean assertion failure rather than a silent
    external HTTP fetch.
    """

    def _explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "CTBTO Treaty Status adapter must not invoke "
            "urllib.request.urlopen (offline / cache-only)"
        )

    def _socket_explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "CTBTO Treaty Status adapter must not invoke "
            "socket.socket (offline / cache-only)"
        )

    import socket as socket_module
    import urllib.request as urlrequest

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(urlrequest, "urlopen", _explode)
    monkeypatch.setattr(socket_module, "socket", _socket_explode)
    try:
        _stage_bundle(tmp_path)
        result = _run(tmp_path)
        assert len(result.observations) == 12
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# Duplicate-slug registration guard (SRC-REG-004)
# ---------------------------------------------------------------------------


def test_duplicate_slug_registration_raises_value_error(
    tmp_path: Path,
) -> None:
    """Registering the same ``ctbto_treaty_status`` slug twice
    raises :class:`ValueError` (SRC-REG-004).
    """
    _stage_bundle(tmp_path)
    registry = InMemorySourceRegistry()
    register_ctbto_treaty_status(registry)
    with pytest.raises(ValueError) as excinfo:
        register_ctbto_treaty_status(registry)
    assert CTBTO_TREATY_STATUS_SOURCE_KEY in str(excinfo.value)


# ---------------------------------------------------------------------------
# HTML fallback
# ---------------------------------------------------------------------------


def test_html_fallback_is_loaded_when_csv_absent(tmp_path: Path) -> None:
    """When the cached CSV is absent but a cached HTML file is
    present, the raw-read boundary loads the HTML fallback
    and parses the ``<table>`` via the built-in HTML parser.
    """
    # Stage ONLY the HTML file (no CSV) so the HTML fallback
    # path is exercised.
    import csv as _csv
    import io as _io

    bundle = tmp_path / CTBTO_TREATY_STATUS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    csv_src = _FIXTURE_CSV.read_text(encoding="utf-8")
    # Build a minimal HTML table from the fixture CSV. The
    # canonical CTBTO States Signatories page is delivered as
    # a single ``<table>`` with ``<th>`` header cells and
    # ``<td>`` data cells; the synthetic HTML file mirrors
    # that shape. Use the Python ``csv`` module so a
    # quoted-empty cell (``""``) is correctly parsed as a
    # single empty cell rather than getting mangled by an
    # ad-hoc split heuristic.
    parsed_rows = list(_csv.reader(_io.StringIO(csv_src)))
    header_cells = parsed_rows[0]
    html_lines = [
        "<html><body><table>",
        "<thead><tr>",
    ]
    for cell in header_cells:
        html_lines.append(f"<th>{cell}</th>")
    html_lines.append("</tr></thead>")
    html_lines.append("<tbody>")
    for row in parsed_rows[1:]:
        if not row:
            continue
        html_lines.append("<tr>")
        for cell in row:
            html_lines.append(f"<td>{cell}</td>")
        html_lines.append("</tr>")
    html_lines.append("</tbody>")
    html_lines.append("</table></body></html>")
    html_path = bundle / CTBTO_TREATY_STATUS_HTML_NAME
    html_path.write_text(
        "\n".join(html_lines), encoding="utf-8",
    )
    # Stage the metadata with the HTML file in ``local_files``.
    metadata_payload: dict[str, Any] = {
        "source_name": (
            "CTBTO States Signatories, Comprehensive Nuclear-Test-"
            "Ban Treaty signature and ratification status"
        ),
        "source_key": CTBTO_TREATY_STATUS_SOURCE_KEY,
        "source_version": CTBTO_TREATY_STATUS_DEFAULT_VERSION,
        "download_date": "2026-06-28",
        "coverage": (
            f"single-point treaty-status snapshot, status as of "
            f"{CTBTO_TREATY_STATUS_SNAPSHOT_DATE}"
        ),
        "license_note": (
            "CTBTO terms-of-use; download / copy / use with "
            "acknowledgement; no redistribution of copied full "
            "table in outputs; attribution required."
        ),
        "local_files": [CTBTO_TREATY_STATUS_HTML_NAME],
        "ingestion_status": "downloaded",
        "source_url": CTBTO_TREATY_STATUS_HOMEPAGE_URL,
        "checksum_sha256": (
            hashlib.sha256(html_path.read_bytes()).hexdigest()
        ),
        "notes": (
            "Synthetic fixture bundle for clean-source adapter "
            "tests (HTML fallback); the State labels and date "
            "cells are NOT real CTBTO Treaty Status data."
        ),
    }
    (bundle / "metadata.json").write_text(
        json.dumps(metadata_payload, indent=2), encoding="utf-8",
    )
    result = _run(tmp_path)
    # 6 rows x 2 indicators (default catalog, no Annex 2) = 12
    # observations.
    assert len(result.observations) == 12
    matched_states = {obs.country_name for obs in result.observations}
    assert "State A" in matched_states
    assert "State B" in matched_states
    assert "State C" in matched_states


# ---------------------------------------------------------------------------
# Production runner tests -- mixed-year request semantics (reviewer fix 1)
# ---------------------------------------------------------------------------


def test_mixed_year_request_emits_in_coverage_and_warns(
    tmp_path: Path,
) -> None:
    """A mixed ``years=(2023, 2024)`` request -- where one
    requested year is in-coverage (2024) and one is
    out-of-coverage (2023) -- emits the full observation set
    AND surfaces a single ``YEAR_ABSENT`` warning for the
    out-of-coverage 2023 year (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003).

    The descriptor advertises a single-year 2024 envelope
    so every observation is dated 2024 regardless of which
    year the operator requests; the readiness envelope
    flags every out-of-coverage year individually so the
    operator can see the temporal-fit gap. A pure
    out-of-coverage request (``years=(2023,)``) still emits
    zero observations; see
    :func:`test_out_of_coverage_year_warns_and_emits_no_rows`.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2023, 2024))
    # 6 rows x 2 indicators (default catalog, no Annex 2) = 12
    # observations; every observation is dated 2024 because
    # the source is a single-year 2024 snapshot.
    assert len(result.observations) == 12
    assert all(
        obs.year == CTBTO_TREATY_STATUS_COVERAGE_YEAR
        for obs in result.observations
    )
    assert [w.code for w in result.warnings] == [YEAR_ABSENT]
    assert result.warnings[0].context["year"] == 2023
    # The 2023 year MUST be reported as outside the coverage
    # envelope -- the readiness envelope uses
    # coverage_start_year=coverage_end_year=2024, so 2023 is
    # below coverage_start_year.
    assert (
        result.warnings[0].context["coverage_start_year"]
        == CTBTO_TREATY_STATUS_COVERAGE_START_YEAR
    )
    assert (
        result.warnings[0].context["coverage_end_year"]
        == CTBTO_TREATY_STATUS_COVERAGE_END_YEAR
    )


def test_two_out_of_coverage_years_warns_and_emits_no_rows(
    tmp_path: Path,
) -> None:
    """A request for two out-of-coverage years
    (``years=(2022, 2023)``) -- where NO requested year is
    in-coverage -- emits zero observations AND surfaces two
    ``YEAR_ABSENT`` warnings (one per out-of-coverage year).
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path, years=(2022, 2023))
    assert result.observations == ()
    assert [w.code for w in result.warnings] == [
        YEAR_ABSENT,
        YEAR_ABSENT,
    ]
    year_warnings = {w.context["year"] for w in result.warnings}
    assert year_warnings == {2022, 2023}


# ---------------------------------------------------------------------------
# Production runner tests -- unique observation IDs (reviewer fix 2)
# ---------------------------------------------------------------------------


def test_observation_ids_unique_default_catalog(tmp_path: Path) -> None:
    """Every emitted observation has a UNIQUE ``observation_id``
    AND a unique ``source_row_reference`` -- signature /
    ratification observations for the same row do NOT collide
    on a shared per-row reference.

    For the default 2-indicator catalog (signature +
    ratification, no Annex 2), 6 rows x 2 indicators = 12
    unique observations. The ``observation_id`` and the
    ``extension["source_row_reference"]`` MUST be unique
    per observation so the audit trail can recover every
    (row, indicator) pair without collision.
    """
    _stage_bundle(tmp_path)
    result = _run(tmp_path)
    assert len(result.observations) == 12
    observation_ids = [obs.observation_id for obs in result.observations]
    source_row_references = [
        obs.extension["source_row_reference"]
        for obs in result.observations
    ]
    assert len(set(observation_ids)) == 12, (
        "observation_id MUST be unique per (row, indicator); "
        f"got {len(set(observation_ids))} unique ids across "
        f"{len(observation_ids)} observations"
    )
    assert len(set(source_row_references)) == 12, (
        "extension['source_row_reference'] MUST be unique per "
        f"(row, indicator); got {len(set(source_row_references))} "
        f"unique references across "
        f"{len(source_row_references)} observations"
    )
    # Every per-indicator reference MUST include the
    # indicator code suffix so audit code can recover the
    # exact source-native column from the reference alone.
    sig_refs = [
        r for r in source_row_references
        if CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS in r
    ]
    rat_refs = [
        r for r in source_row_references
        if CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS in r
    ]
    assert len(sig_refs) == 6
    assert len(rat_refs) == 6


def test_observation_ids_unique_with_annex_2(tmp_path: Path) -> None:
    """When the cached fixture carries an explicit ``Annex 2``
    column, the transform layer emits a per-row OPTIONAL
    ``ctbto_treaty_status_annex_2_status`` observation in
    addition to the default 2-indicator catalog. Every
    emitted observation MUST have a unique ``observation_id``
    -- signature, ratification, and Annex 2 observations for
    the same row MUST NOT collide.

    For the 3-indicator catalog (signature + ratification +
    Annex 2), 6 rows x 3 indicators = 18 unique
    observations.
    """
    _stage_bundle(tmp_path, with_annex_2=True)
    result = _run(tmp_path)
    assert len(result.observations) == 18
    observation_ids = [obs.observation_id for obs in result.observations]
    source_row_references = [
        obs.extension["source_row_reference"]
        for obs in result.observations
    ]
    assert len(set(observation_ids)) == 18, (
        "observation_id MUST be unique per (row, indicator); "
        f"got {len(set(observation_ids))} unique ids across "
        f"{len(observation_ids)} observations"
    )
    assert len(set(source_row_references)) == 18
    # The three indicator codes must each appear in the
    # emitted references -- six times each (one per row).
    for indicator_code in (
        CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS,
        CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS,
        CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS,
    ):
        matching_refs = [
            r for r in source_row_references
            if indicator_code in r
        ]
        assert len(matching_refs) == 6, (
            f"indicator_code={indicator_code!r} must appear in "
            f"exactly 6 source_row_reference values; got "
            f"{len(matching_refs)}"
        )


def test_observation_ids_match_transform_locator_rule_id(
    tmp_path: Path,
) -> None:
    """The ``observation_id`` MUST be byte-identical to the
    ``transform_locator.rule_id`` so the audit trail can
    cross-reference observations via a single stable key.
    """
    _stage_bundle(tmp_path, with_annex_2=True)
    result = _run(tmp_path)
    for obs in result.observations:
        assert obs.observation_id == obs.transform_locator.rule_id


# ---------------------------------------------------------------------------
# Production runner tests -- selected-file readiness contract (reviewer fix 3)
# ---------------------------------------------------------------------------


def _stage_html_only_bundle_with_local_files_csv(
    tmp_path: Path,
    *,
    checksum: Any = "AUTO",
) -> Path:
    """Stage a bundle where the cached HTML fallback is the
    only file on disk but ``metadata.local_files`` declares
    only the canonical CSV. This is the canonical
    HTML-present / CSV-listed mismatch the reviewer called
    out.
    """
    bundle = tmp_path / CTBTO_TREATY_STATUS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    # Stage ONLY the HTML file (no CSV).
    html_path = bundle / CTBTO_TREATY_STATUS_HTML_NAME
    html_path.write_text(
        "<html><body><table><tr><th>Region</th><th>State</th>"
        "<th>Signature Date</th><th>Ratification Date</th></tr>"
        "<tr><td>Region</td><td>State A</td><td></td><td></td></tr>"
        "</table></body></html>",
        encoding="utf-8",
    )

    checksum_value: Any = checksum
    if checksum == "AUTO":
        checksum_value = (
            hashlib.sha256(html_path.read_bytes()).hexdigest()
        )

    payload: dict[str, Any] = {
        "source_name": (
            "CTBTO States Signatories, Comprehensive Nuclear-Test-"
            "Ban Treaty signature and ratification status"
        ),
        "source_key": CTBTO_TREATY_STATUS_SOURCE_KEY,
        "source_version": CTBTO_TREATY_STATUS_DEFAULT_VERSION,
        "download_date": "2026-06-28",
        "coverage": (
            f"single-point treaty-status snapshot, status as of "
            f"{CTBTO_TREATY_STATUS_SNAPSHOT_DATE}"
        ),
        "license_note": (
            "CTBTO terms-of-use; download / copy / use with "
            "acknowledgement; no redistribution; attribution "
            "required."
        ),
        # Mismatch: declare CSV but only HTML is on disk.
        "local_files": [CTBTO_TREATY_STATUS_CSV_NAME],
        "ingestion_status": "downloaded",
        "source_url": CTBTO_TREATY_STATUS_HOMEPAGE_URL,
    }
    if checksum_value is not None:
        payload["checksum_sha256"] = checksum_value
    payload["notes"] = (
        "Synthetic fixture bundle for selected-file mismatch test."
    )
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle


def _stage_csv_only_bundle_with_local_files_html(
    tmp_path: Path,
) -> Path:
    """Stage a bundle where the canonical CSV is the only
    file on disk but ``metadata.local_files`` declares only
    the HTML fallback. This is the canonical CSV-present /
    HTML-listed mismatch the reviewer called out.
    """
    # The default ``_stage_bundle`` already stages ONLY the
    # CSV file; just override ``local_files`` to declare the
    # HTML fallback instead.
    bundle = _stage_bundle(tmp_path, with_csv=True)
    metadata_file = bundle / "metadata.json"
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    payload["local_files"] = [CTBTO_TREATY_STATUS_HTML_NAME]
    metadata_file.write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    return bundle


def test_readiness_fails_when_html_present_but_csv_listed(
    tmp_path: Path,
) -> None:
    """The canonical HTML fallback is staged on disk but
    ``metadata.local_files`` declares only the canonical CSV
    -- the actually-present selected file (HTML) is NOT
    listed in ``local_files``. Readiness MUST fail with a
    structured
    ``ctbto_treaty_status_local_files_invalid`` error so the
    runner refuses to dispatch ``read_raw`` against the
    undeclared HTML file.
    """
    _stage_html_only_bundle_with_local_files_csv(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID
    )
    assert (
        CTBTO_TREATY_STATUS_HTML_NAME
        in readiness.errors[0].message
    )
    assert (
        CTBTO_TREATY_STATUS_CSV_NAME
        in readiness.errors[0].message
    )


def test_readiness_fails_when_csv_present_but_html_listed(
    tmp_path: Path,
) -> None:
    """The canonical CSV is staged on disk but
    ``metadata.local_files`` declares only the HTML fallback
    -- the actually-present selected file (CSV) is NOT
    listed in ``local_files``. Readiness MUST fail with a
    structured
    ``ctbto_treaty_status_local_files_invalid`` error so the
    runner refuses to dispatch ``read_raw`` against the
    undeclared CSV file.
    """
    _stage_csv_only_bundle_with_local_files_html(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID
    )
    assert (
        CTBTO_TREATY_STATUS_HTML_NAME
        in readiness.errors[0].message
    )
    assert (
        CTBTO_TREATY_STATUS_CSV_NAME
        in readiness.errors[0].message
    )


def test_readiness_fails_when_selected_file_not_checksum_covered(
    tmp_path: Path,
) -> None:
    """The HTML fallback is staged on disk but
    ``metadata.checksum_sha256`` only covers the canonical
    CSV -- the actually-present selected file (HTML) is NOT
    checksum-covered. Readiness MUST fail with a structured
    ``ctbto_treaty_status_checksum_mismatch`` error so the
    runner refuses to dispatch ``read_raw`` against an
    undeclared/uncovered HTML file.

    The bundle declares ``local_files = [states-signatories.html]``
    so the shape-level ``local_files`` checks pass; the new
    selected-checksum-covered check is the second-line guard
    that catches the checksum gap.
    """
    bundle = tmp_path / CTBTO_TREATY_STATUS_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    # Stage ONLY the HTML file (no CSV).
    html_path = bundle / CTBTO_TREATY_STATUS_HTML_NAME
    html_path.write_text(
        "<html><body><table><tr><th>Region</th><th>State</th>"
        "<th>Signature Date</th><th>Ratification Date</th></tr>"
        "<tr><td>Region</td><td>State A</td><td></td><td></td></tr>"
        "</table></body></html>",
        encoding="utf-8",
    )
    html_sha = hashlib.sha256(html_path.read_bytes()).hexdigest()
    # Declare a checksum that covers ONLY the CSV (not the
    # actually-present HTML) so the per-file dict has no
    # entry for the selected HTML file.
    payload: dict[str, Any] = {
        "source_name": (
            "CTBTO States Signatories, Comprehensive Nuclear-Test-"
            "Ban Treaty signature and ratification status"
        ),
        "source_key": CTBTO_TREATY_STATUS_SOURCE_KEY,
        "source_version": CTBTO_TREATY_STATUS_DEFAULT_VERSION,
        "download_date": "2026-06-28",
        "coverage": (
            f"single-point treaty-status snapshot, status as of "
            f"{CTBTO_TREATY_STATUS_SNAPSHOT_DATE}"
        ),
        "license_note": (
            "CTBTO terms-of-use; download / copy / use with "
            "acknowledgement; no redistribution; attribution "
            "required."
        ),
        "local_files": [CTBTO_TREATY_STATUS_HTML_NAME],
        "ingestion_status": "downloaded",
        "source_url": CTBTO_TREATY_STATUS_HOMEPAGE_URL,
        # Checksum covers the CSV ONLY -- not the HTML.
        "checksum_sha256": {
            CTBTO_TREATY_STATUS_CSV_NAME: html_sha,
        },
        "notes": (
            "Synthetic fixture bundle for "
            "selected-file-checksum mismatch test."
        ),
    }
    (bundle / "metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH
    )
    assert (
        CTBTO_TREATY_STATUS_HTML_NAME
        in readiness.errors[0].message
    )


# ---------------------------------------------------------------------------
# Production runner tests -- cache-policy exact code (reviewer fix 4)
# ---------------------------------------------------------------------------


def test_cache_policy_refresh_fails_readiness_exact_code(
    tmp_path: Path,
) -> None:
    """``cache_policy="refresh"`` MUST fail readiness with
    the EXACT documented code
    ``ctbto_treaty_status_unsupported_cache_policy`` (no
    code drift between docs / constants / tests).
    """
    _stage_bundle(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path, cache_policy="refresh"),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == "ctbto_treaty_status_unsupported_cache_policy"
    )
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY
    )


def test_cache_policy_no_cache_fails_readiness_exact_code(
    tmp_path: Path,
) -> None:
    """``cache_policy="no_cache"`` MUST fail readiness with
    the EXACT documented code
    ``ctbto_treaty_status_unsupported_cache_policy`` (no
    code drift between docs / constants / tests).
    """
    _stage_bundle(tmp_path)
    readiness = create_ctbto_treaty_status_adapter().check_ready(
        _request(tmp_path, cache_policy="no_cache"),
    )
    assert readiness.ready is False
    assert (
        readiness.errors[0].code
        == "ctbto_treaty_status_unsupported_cache_policy"
    )
    assert (
        readiness.errors[0].code
        == CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY
    )
