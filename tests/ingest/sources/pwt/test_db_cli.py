"""Phase B Increment B -- PWT registry E2E, CLI E2E, year behavior, idempotency.

This file covers the PWT Stage 2 boundary through the
registry runner (``registry.ingest_source``), the Typer CLI
(``leaders-db ingest-source``), the year behavior (per-year
canonical counts + the out-of-coverage manifest warning), and
the CLI idempotency contract (re-running for the same year
does not double ``source_observations`` rows).

PASS-ELIGIBLE / DOMAIN-RED conventions
--------------------------------------

- ``PASS-ELIGIBLE`` -- unused in this file; all tests are
  DOMAIN-RED.
- ``DOMAIN-RED`` -- every test in this file is intentionally
  RED at the domain layer until the production writer lands.
  Failure mode is an assertion failure on a wrong-shaped stub
  output (no parquet, no manifest, zero ``source_observations``
  rows) -- NOT ``ModuleNotFoundError``.

Coverage
--------

- ``ingest_pwt`` / ``registry.ingest_source`` for
  ``year=2019`` writes 15 ``source_observations`` rows
  (USA 6 + MEX 6 + SWE 3) and the per-country / per-year
  counts are derivable from the canonical locator
  ``pwt:Data:<iso3>:<year>:<raw_column>``.
- ``year=2019`` requests do NOT write 2018 rows (the registry
  runner scopes the request -- no leakage).
- ``year=2018`` writes 2 rows (USA rgdpe + USA pop).
- ``year=2023`` writes zero rows AND emits the
  ``requested_year_out_of_coverage`` manifest warning (PWT
  10.01 ends at 2019).
- The CLI ``leaders-db ingest-source --source pwt --year
  2019`` runs end-to-end through the Typer CLI runner
  against the isolated data lake + DB and writes the
  parquet, the manifest, the ``source_observations`` rows,
  and the attribution.
- Re-running the CLI for the same year does NOT duplicate
  ``source_observations`` rows (idempotency).
- No-year / all-years call emits rows for every observed
  year in the fixture (2018, 2019) and nothing else -- in
  particular NOT 2023.

Missing-cell emission semantics (documented per Phase B
review feedback): the transform drops a cell -- does NOT
emit an observation row -- when the raw cell is:

  1. ``None`` (the openpyxl default for empty cells), or
  2. A string sentinel (``""``, ``"  "``, ``"N/A"``, ``"NaN"``,
     ``"null"``, etc.) -- no observation row emitted at all, or
  3. A non-numeric, non-empty string -- no observation row
     emitted at all.

The fixture's blank / numeric / non-numeric cell pattern
(see ``tests/fixtures/pwt/build_sample_xlsx.py``) was chosen
to exercise this rule deterministically. The expected
observation counts are:

  - year=2018: 2 (USA 2018: rgdpe + pop = 2 cells; MEX 2018
    and SWE 2018 are entirely blank).
  - year=2019: 15 (USA 2019: 6 cells, MEX 2019: 6 cells, SWE
    2019: 3 cells).
  - all-years / no-year: 17 (USA 2018 = 2, USA 2019 = 6, MEX
    2018 = 0, MEX 2019 = 6, SWE 2018 = 0, SWE 2019 = 3).
  - year=2023: 0 (PWT 10.01 ends at 2019; the
    ``requested_year_out_of_coverage`` manifest warning
    surfaces the gap -- no 2019->2023 proxy / stale fill
    is allowed, per architecture §PWT).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest.interfaces import IngestRequest

from .conftest import PWT_SOURCE_KEY, PWT_XLSX_NAME

# Resolve the fixtures dir once for the second-pass regression
# proofs (test functions reference this module-level constant).
_PWT_FIXTURES_DIR: Path = (
    Path(__file__).resolve().parents[3] / "fixtures" / "pwt"
)


# ---------------------------------------------------------------------------
# 1. Year behavior
# ---------------------------------------------------------------------------


def test_pwt_year_2019_emits_expected_observations(
    pwt_xlsx_dir: Path,
) -> None:
    """``year=2019`` emits the expected number of long rows.

    The fixture emits 15 non-blank ``(countrycode, year,
    raw_column)`` triples for 2019 (USA 2019: 6 cells, MEX
    2019: 6 cells, SWE 2019: 3 cells). The transform must
    produce one long row per triple.

    DOMAIN-RED: ``ingest_pwt()`` returns an ``IngestResult``
    with ``observation_rows=0`` in the Phase B stub. The test
    fails at the ``observation_rows == 15`` assertion -- the
    production orchestrator must populate the count from the
    transformed long frame.
    """
    from leaders_db.ingest.sources.pwt import ingest_pwt

    result = ingest_pwt(
        year=2019, xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME,
    )
    assert result.observation_rows == 15, (
        f"expected 15 observations from year=2019 "
        f"(USA 6 + MEX 6 + SWE 3); got {result.observation_rows}"
    )
    assert 2019 in result.years


def test_pwt_year_2018_emits_expected_observations(
    pwt_xlsx_dir: Path,
) -> None:
    """``year=2018`` emits the expected number of long rows.

    The fixture emits 2 non-blank ``(countrycode, year,
    raw_column)`` triples for 2018 (USA 2018: 2 cells; MEX 2018
    and SWE 2018 are entirely blank). The transform must
    produce one long row per triple.

    DOMAIN-RED: ``ingest_pwt()`` returns an ``IngestResult``
    with ``observation_rows=0`` in the Phase B stub. The test
    fails at the ``observation_rows == 2`` assertion -- the
    production orchestrator must populate the count from the
    transformed long frame.
    """
    from leaders_db.ingest.sources.pwt import ingest_pwt

    result = ingest_pwt(
        year=2018, xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME,
    )
    assert result.observation_rows == 2, (
        f"expected 2 observations from year=2018 "
        f"(USA rgdpe + USA pop); got {result.observation_rows}"
    )
    assert 2018 in result.years


def test_pwt_year_2023_emits_zero_observations_with_warning(
    pwt_xlsx_dir: Path,
) -> None:
    """``year=2023`` emits ZERO observations AND surfaces a
    ``requested_year_out_of_coverage`` warning in the run
    manifest.

    DOMAIN-RED: ``ingest_pwt()`` returns an ``IngestResult``
    with ``observation_rows=0`` and writes a manifest with
    empty ``warnings`` in the Phase B stub. The test passes
    the ``observation_rows == 0`` assertion (the stub happens
    to return 0), then fails at the manifest-warning assertion
    (the stub manifest has no
    ``requested_year_out_of_coverage`` entry).
    """
    from leaders_db.ingest.sources.pwt import ingest_pwt

    result = ingest_pwt(
        year=2023, xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME,
    )
    assert result.observation_rows == 0
    assert 2023 not in result.years

    manifest_path = (
        pwt_xlsx_dir.parent.parent
        / "processed"
        / PWT_SOURCE_KEY
        / "pwt_run_manifest.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    warnings = payload.get("warnings", [])
    codes = {w.get("code") for w in warnings if isinstance(w, dict)}
    assert "requested_year_out_of_coverage" in codes, (
        f"manifest must record requested_year_out_of_coverage "
        f"warning for year=2023; got warnings={warnings!r}"
    )


def test_pwt_no_year_emits_all_fixture_observed_years(
    pwt_xlsx_dir: Path,
) -> None:
    """Calling the adapter with no year argument emits rows for
    every observed year in the fixture (2018, 2019) and nothing
    else -- in particular NOT 2023.

    The fixture's per-country / per-year counts are:
    USA 2018=2, USA 2019=6, MEX 2018=0, MEX 2019=6, SWE
    2018=0, SWE 2019=3, for a total of 17 observations
    across 2018+2019 (no-year / all-years).

    DOMAIN-RED: ``ingest_pwt()`` returns an ``IngestResult``
    with empty ``years`` and ``observation_rows=0`` in the Phase
    B stub. The test fails at the ``set(result.years) ==
    {2018, 2019}`` assertion -- the production orchestrator
    must populate the years from the transformed long frame.
    """
    from leaders_db.ingest.sources.pwt import ingest_pwt

    result = ingest_pwt(xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME)
    assert set(result.years) == {2018, 2019}, (
        f"no-year call must emit fixture observed years 2018,2019 "
        f"only; got {set(result.years)}"
    )
    assert result.observation_rows == 17, (
        f"expected 17 observations across 2018+2019 "
        f"(USA 2018=2, USA 2019=6, MEX 2018=0, MEX 2019=6, "
        f"SWE 2018=0, SWE 2019=3); got {result.observation_rows}"
    )


# ---------------------------------------------------------------------------
# 2. Registry-ready PWT E2E (shared protocol proof)
# ---------------------------------------------------------------------------
#
# The reviewer's Phase B blocker: prove the implementation
# cannot bypass ``PWTAdapter.read`` / ``.transform`` / ``.write``
# and only wire ``ingest_pwt`` / CLI directly. The test
# registers the real ``PWTAdapter`` with a well-formed
# staged PWT bundle, drives ``registry.ingest_source`` through
# the shared adapter ready path, and asserts the parquet /
# manifest / DB outputs. With current stubs:
#
# - ``PWTAdapter.check_ready`` returns ``ready=True`` (the
#   readiness gate is implemented as a stub).
# - ``PWTAdapter.read`` / ``.transform`` / ``.write`` return
#   wrong-shaped values (right type, wrong content -- no
#   parquet / no manifest / no DB rows).
# - ``registry.ingest_source`` drives the full pipeline and
#   returns the wrong ``IngestResult`` from ``write``.
#
# The test fails at the parquet / manifest / DB assertions --
# NOT at import, NOT at a generic ``Exception``. The
# readiness gate is the only stub "production-like" behavior;
# read / transform / write are still stubs that return wrong
# values, so the test stays DOMAIN-RED at the assertion level.


def test_registry_ready_pwt_e2e_through_shared_adapter(
    pwt_xlsx_dir: Path,
    pwt_init_test_db: str,
) -> None:
    """Register ``PWTAdapter`` with a well-formed staged PWT
    bundle and drive ``registry.ingest_source`` through the
    shared adapter ready path. Assert parquet / manifest / DB
    outputs.

    DOMAIN-RED: ``PWTAdapter.read`` / ``.transform`` / ``.write``
    return wrong-shaped values (no parquet, no manifest, no DB
    rows). The test fails at the parquet / manifest / DB
    assertions. The readiness gate passes (``ready=True``);
    the runner calls ``read`` / ``transform`` / ``write`` in
    order; the outputs are wrong. The test PROVES the
    implementation cannot bypass ``PWTAdapter.read`` /
    ``.transform`` / ``.write`` and only wire
    ``ingest_pwt`` / CLI directly.
    """
    from leaders_db.ingest.registry import (
        ingest_source,
        register,
        unregister,
    )
    from leaders_db.ingest.sources.pwt import PWTAdapter

    register("pwt", PWTAdapter())
    try:
        result = ingest_source(
            IngestRequest(
                source_key="pwt",
                year=2019,
                raw_root=pwt_xlsx_dir.parent,
            ),
        )
    finally:
        unregister("pwt")

    # The runner must have called the shared protocol methods
    # in order: check_ready (returned ready=True) -> read ->
    # transform -> write. The IngestResult is the write
    # method's return value.
    assert result.source_key == "pwt"

    # Parquet assertion: the write method's stub does NOT
    # persist a parquet. The test fails here -- the production
    # writer must persist the parquet.
    assert result.parquet_path is not None, (
        "registry.ingest_source did not persist a parquet; "
        "the shared PWTAdapter.write must persist the parquet "
        "(or the production must wire ingest_pwt -- but the "
        "test specifically exercises the registry path to "
        "prove the shared protocol is used)."
    )
    assert result.parquet_path.is_file(), (
        f"parquet path set but file missing at {result.parquet_path}"
    )

    # Manifest assertion.
    assert result.manifest_path is not None, (
        "registry.ingest_source did not set manifest_path"
    )
    assert result.manifest_path.is_file(), (
        f"manifest path set but file missing at {result.manifest_path}"
    )

    # DB assertion: a year=2019 run must write source_observations
    # rows (per the documented per-country/year indicator counts).
    with session_scope(pwt_init_test_db) as session:
        obs_count = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()
    assert obs_count == 15, (
        f"expected 15 source_observations rows from year=2019; "
        f"got {obs_count}"
    )

    # Per-country / per-year indicator-count assertions so the
    # totals are derivable (per Phase B review feedback).
    with session_scope(pwt_init_test_db) as session:
        # Total year=2019 observations (sums USA 6 + MEX 6 + SWE 3).
        year_2019_count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2019,
            )).scalar_one()
        # The DB doesn't carry an ISO3 column in the simple
        # prototype; the per-country split would need a
        # join to the countries table. For Phase B we assert
        # the total year=2019 count.
    assert year_2019_count == 15, (
        f"expected 15 year=2019 observations "
        f"(USA 6 + MEX 6 + SWE 3); got {year_2019_count}"
    )

    # Per-year breakdown: a year=2019 run must NOT write
    # 2018 rows (the request scope is honored). The all-years
    # behavior is exercised in
    # :func:`test_pwt_no_year_emits_all_fixture_observed_years`
    # (no-year call emits 2018+2019 = 17 rows).
    with session_scope(pwt_init_test_db) as session:
        year_2018_count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2018,
            )).scalar_one()
    assert year_2018_count == 0, (
        f"year=2019 run must not write 2018 observations "
        f"(no leakage across years); got {year_2018_count}"
    )

    # Per-country / per-year indicator-count assertions via
    # source_row_reference token grouping. The locator
    # ``pwt:Data:<iso3>:<year>:<raw_column>`` is the canonical
    # audit-trail token; the test groups DB rows by tokens
    # (iso3, year) to derive the per-country / per-year
    # counts without depending on a separate iso3 column.
    with session_scope(pwt_init_test_db) as session:
        refs = session.execute(
            select(SourceObservation.source_row_reference),
        ).scalars().all()
    counts: dict[tuple[str, int], int] = {}
    for ref in refs:
        # Token pattern: "pwt:Data:<iso3>:<year>:<raw_column>"
        parts = ref.split(":")
        assert len(parts) >= 5, (
            f"source_row_reference {ref!r} must follow "
            f"'pwt:Data:<iso3>:<year>:<raw_column>'"
        )
        iso3 = parts[2]
        year = int(parts[3])
        counts[(iso3, year)] = counts.get((iso3, year), 0) + 1
    # The year=2019 request must only produce 2019 rows -- no
    # 2018 leakage. The registry runner scopes the request.
    assert set(year for _, year in counts) == {2019}, (
        f"year=2019 request must not write other years; got "
        f"{sorted(set(year for _, year in counts))}"
    )
    assert counts.get(("USA", 2019), 0) == 6, (
        f"expected USA 2019 = 6 observations; got "
        f"{counts.get(('USA', 2019), 0)}"
    )
    assert counts.get(("MEX", 2019), 0) == 6, (
        f"expected MEX 2019 = 6 observations; got "
        f"{counts.get(('MEX', 2019), 0)}"
    )
    assert counts.get(("SWE", 2019), 0) == 3, (
        f"expected SWE 2019 = 3 observations; got "
        f"{counts.get(('SWE', 2019), 0)}"
    )


def test_registry_pwt_uses_request_scoped_raw_root_for_full_pipeline(
    isolated_data_lake: Path,
    pwt_custom_raw_root: Path,
    pwt_init_test_db: str,
) -> None:
    """The registry path carries ``request.raw_root`` through every
    shared-adapter stage, not only through ``check_ready``.

    The fixture stages ``pwt1001.xlsx`` + ``metadata.json`` only
    under ``<custom_raw_root>/pwt`` and deliberately leaves the
    default ``data/raw/pwt`` path absent. A production adapter that
    honors ``IngestRequest.raw_root`` in ``check_ready`` but then
    falls back to the default raw data-lake path in ``read`` cannot
    pass this test.

    DOMAIN-RED: the Phase B stub readiness gate passes for the
    custom raw root, but ``PWTAdapter.read`` / ``.transform`` /
    ``.write`` still return wrong-shaped values. The test fails at
    the parquet / manifest / DB assertions, not at import or at a
    generic readiness exception.
    """
    from leaders_db.ingest.registry import (
        ingest_source,
        register,
        unregister,
    )
    from leaders_db.ingest.sources.pwt import PWTAdapter

    default_bundle = isolated_data_lake / "data" / "raw" / PWT_SOURCE_KEY
    assert not default_bundle.exists(), (
        "test setup requires the default raw bundle to be absent so "
        "the registry path cannot accidentally pass by using it"
    )
    assert (pwt_custom_raw_root / PWT_SOURCE_KEY / PWT_XLSX_NAME).is_file()

    register("pwt", PWTAdapter())
    try:
        result = ingest_source(
            IngestRequest(
                source_key="pwt",
                year=2019,
                raw_root=pwt_custom_raw_root,
            ),
        )
    finally:
        unregister("pwt")

    assert result.source_key == "pwt"
    assert result.parquet_path is not None, (
        "registry.ingest_source must persist parquet when the PWT "
        "bundle exists only under request.raw_root; a missing path "
        "means read/write did not carry the custom raw root through "
        "the runtime registry pipeline."
    )
    assert result.parquet_path.is_file()
    assert result.manifest_path is not None
    assert result.manifest_path.is_file()

    with session_scope(pwt_init_test_db) as session:
        obs_count = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()
    assert obs_count == 15, (
        f"custom raw-root registry run must write the 15 year=2019 "
        f"fixture observations; got {obs_count}"
    )


def test_registry_ready_pwt_year_2023_writes_no_2023_observations(
    pwt_xlsx_dir: Path,
    pwt_init_test_db: str,
) -> None:
    """A ``year=2023`` run through the registry writes zero
    ``source_observations`` rows AND emits the
    ``requested_year_out_of_coverage`` manifest warning.

    DOMAIN-RED: ``PWTAdapter.write`` returns ``observation_rows=0``
    and no manifest. The test fails at the manifest-warning
    assertion -- the production writer must add the warning
    AND write zero rows for out-of-coverage years.
    """
    from leaders_db.ingest.registry import (
        ingest_source,
        register,
        unregister,
    )
    from leaders_db.ingest.sources.pwt import PWTAdapter

    register("pwt", PWTAdapter())
    try:
        result = ingest_source(
            IngestRequest(
                source_key="pwt",
                year=2023,
                raw_root=pwt_xlsx_dir.parent,
            ),
        )
    finally:
        unregister("pwt")

    # The PWT 10.01 bundle ends at 2019; a 2023 run must
    # produce zero source_observations rows.
    with session_scope(pwt_init_test_db) as session:
        obs_2023 = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2023,
            )).scalar_one()
    assert obs_2023 == 0, (
        f"year=2023 must produce zero observations; got {obs_2023}. "
        "The PWT 10.01 bundle ends at 2019; no 2019->2023 "
        "proxy / stale fill is allowed (architecture §PWT)."
    )

    # The manifest must record the out-of-coverage warning.
    assert result.manifest_path is not None
    payload = json.loads(
        result.manifest_path.read_text(encoding="utf-8"),
    )
    codes = {
        w.get("code")
        for w in payload.get("warnings", [])
        if isinstance(w, dict)
    }
    assert "requested_year_out_of_coverage" in codes, (
        f"manifest must record requested_year_out_of_coverage "
        f"warning for year=2023; got codes={codes}"
    )


# ---------------------------------------------------------------------------
# 3. CLI end-to-end through Typer isolated data lake
# ---------------------------------------------------------------------------


def test_cli_ingest_source_pwt_year_2019_end_to_end(
    pwt_xlsx_dir: Path,
    pwt_init_test_db: str,
) -> None:
    """``leaders-db ingest-source --source pwt --year 2019`` runs
    end-to-end through the Typer CLI runner.

    DOMAIN-RED: the CLI falls through to the legacy
    ``STAGE2_ADAPTERS['pwt'] = None`` stub path; no parquet /
    manifest / observations are written. The test fails at
    the parquet assertion; the production CLI shim must
    delegate to ``ingest_pwt``.
    """
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ingest-source",
            "--source", "pwt",
            "--year", "2019",
        ],
    )
    assert result.exit_code == 0, (
        f"CLI failed: exit={result.exit_code}, stdout={result.stdout!r}"
    )
    parquet_path = (
        pwt_xlsx_dir.parent.parent
        / "processed"
        / PWT_SOURCE_KEY
        / "pwt_country_year.parquet"
    )
    assert parquet_path.is_file(), (
        f"parquet not written at {parquet_path}"
    )
    table = pq.read_table(parquet_path)
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"pwt_attribution")
    assert attribution_bytes is not None, (
        "parquet missing pwt_attribution metadata"
    )
    assert b"Feenstra" in attribution_bytes

    manifest_path = parquet_path.parent / "pwt_run_manifest.json"
    assert manifest_path.is_file()
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"]
    assert "Feenstra" in manifest_payload["attribution"]

    with session_scope(pwt_init_test_db) as session:
        sources = session.execute(select(Source)).scalars().all()
        assert any(s.source_name == "Penn World Table" for s in sources)
        obs_count = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()
    assert obs_count == 15, (
        f"expected 15 year=2019 observations; got {obs_count}. "
        "Per-country/year counts: USA 2019 = 6, MEX 2019 = 6, "
        "SWE 2019 = 3; total = 15."
    )

    # Per-country / per-year count assertions via
    # source_row_reference token grouping. The locator
    # ``pwt:Data:<iso3>:<year>:<raw_column>`` is the canonical
    # audit-trail token; the test groups DB rows by tokens
    # (iso3, year) to derive the per-country / per-year
    # counts without depending on a separate iso3 column.
    with session_scope(pwt_init_test_db) as session:
        refs = session.execute(
            select(SourceObservation.source_row_reference).where(
                SourceObservation.year == 2019,
            ),
        ).scalars().all()
    counts: dict[tuple[str, int], int] = {}
    for ref in refs:
        # Token pattern: "pwt:Data:<iso3>:<year>:<raw_column>"
        parts = ref.split(":")
        assert len(parts) >= 5, (
            f"source_row_reference {ref!r} must follow "
            f"'pwt:Data:<iso3>:<year>:<raw_column>'"
        )
        iso3 = parts[2]
        year = int(parts[3])
        counts[(iso3, year)] = counts.get((iso3, year), 0) + 1
    assert counts.get(("USA", 2019), 0) == 6, (
        f"expected USA 2019 = 6 observations; got "
        f"{counts.get(('USA', 2019), 0)}"
    )
    assert counts.get(("MEX", 2019), 0) == 6, (
        f"expected MEX 2019 = 6 observations; got "
        f"{counts.get(('MEX', 2019), 0)}"
    )
    assert counts.get(("SWE", 2019), 0) == 3, (
        f"expected SWE 2019 = 3 observations; got "
        f"{counts.get(('SWE', 2019), 0)}"
    )

    # Per-row DB assertions (per Phase B review feedback).
    # A representative source_observations row must have the
    # documented year, variable_name, raw_value, and the
    # canonical locator ``pwt:Data:<iso3>:<year>:<raw_column>``.
    with session_scope(pwt_init_test_db) as session:
        # Pick a representative row: USA 2019 rgdpe.
        representative = session.execute(
            select(SourceObservation).where(
                SourceObservation.year == 2019,
            )
        ).scalars().first()
    assert representative is not None, (
        "no source_observations row for year=2019"
    )
    assert representative.year == 2019
    assert representative.variable_name, (
        "source_observations row missing variable_name"
    )
    assert representative.source_row_reference is not None
    assert representative.source_row_reference.startswith(
        "pwt:Data:"
    ), (
        f"source_row_reference must start with 'pwt:Data:'; got "
        f"{representative.source_row_reference!r}"
    )
    # raw_value must be preserved (not null/empty for a
    # non-blank cell).
    assert representative.raw_value, (
        f"raw_value must be preserved for a non-blank cell; got "
        f"{representative.raw_value!r}"
    )

    # No 2023 observations may be persisted (the year=2019
    # run must not write 2023 rows; architecture §PWT).
    with session_scope(pwt_init_test_db) as session:
        obs_2023 = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2023,
            )).scalar_one()
    assert obs_2023 == 0, (
        f"year=2019 run must not persist 2023 observations; "
        f"got {obs_2023}"
    )

    assert "Feenstra" in result.stdout or "Feenstra" in (
        getattr(result, "stderr", None) or ""
    )


# ---------------------------------------------------------------------------
# 4. Idempotency
# ---------------------------------------------------------------------------


def test_pwt_rerun_does_not_duplicate_observations(
    pwt_xlsx_dir: Path,
    pwt_init_test_db: str,
) -> None:
    """Re-running ``ingest_pwt`` (or the CLI ``ingest-source``)
    for the same year does NOT double the
    ``source_observations`` row count.

    The fixture contract is: year=2019 emits 15
    ``source_observations`` rows (USA 6 + MEX 6 + SWE 3);
    the re-run must leave the count unchanged.

    DOMAIN-RED: the CLI falls through to the legacy stub path;
    the DB has zero observations. The test fails at the
    first-run assertion that exactly 15 rows are written.
    """
    runner = CliRunner()
    first = runner.invoke(
        app,
        ["ingest-source", "--source", "pwt", "--year", "2019"],
    )
    assert first.exit_code == 0, first.stdout

    with session_scope(pwt_init_test_db) as session:
        first_count = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()
    assert first_count == 15, (
        f"first run must write 15 source_observations rows from "
        f"year=2019 (USA 6 + MEX 6 + SWE 3); got {first_count}. "
        f"(The CLI likely fell through to the 'not implemented "
        f"yet' stub -- the PWT adapter must be wired in "
        f"STAGE2_ADAPTERS before this test can pass.)"
    )

    second = runner.invoke(
        app,
        ["ingest-source", "--source", "pwt", "--year", "2019"],
    )
    assert second.exit_code == 0, second.stdout

    with session_scope(pwt_init_test_db) as session:
        second_count = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()

    assert second_count == first_count, (
        f"re-running PWT for the same year duplicated DB rows: "
        f"first={first_count}, second={second_count}"
    )


# ---------------------------------------------------------------------------
# 5. Phase B Increment B regression proofs
# ---------------------------------------------------------------------------
#
# Phase B Increment B reviewer feedback flagged two regressions in the
# original production code:
#
# - Out-of-coverage / empty-frame runs (year=2023 against a 1950-2019
#   PWT bundle) SKIPPED the DB write block entirely: the PWT ``sources``
#   row was NOT upserted and any pre-existing stale ``source_observations``
#   rows for the requested year(s) survived a corrective re-run.
# - The convenience path ``PWTAdapter.ingest(request)`` dropped the
#   request-scoped ``database_url``, ``processed_root``, ``years``, and
#   most other fields because it delegated to ``ingest_pwt()`` with only
#   ``year=`` and ``xlsx_override=``.
#
# The tests below are the regression proofs the reviewer demanded.


def _stage_pwt_bundle_for_regression(
    custom_raw_root: Path, fixtures_dir: Path,
) -> Path:
    """Stage a valid PWT bundle under ``custom_raw_root/pwt``.

    Helper used by the regression-proof tests. Copies the
    fixture xlsx, recomputes the SHA-256, and writes a
    well-formed ``metadata.json`` so the readiness gate
    passes.
    """
    bundle_target = custom_raw_root / PWT_SOURCE_KEY
    bundle_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        fixtures_dir / "sample.xlsx", bundle_target / PWT_XLSX_NAME,
    )
    staged_xlsx_path = bundle_target / PWT_XLSX_NAME
    sha = hashlib.sha256(staged_xlsx_path.read_bytes()).hexdigest()
    metadata_payload = {
        "source_name": "Penn World Table",
        "source_version": "10.01",
        "download_date": "2026-06-22",
        "coverage": "country-year economic accounts",
        "years_available": "1950-2019",
        "license_note": (
            "Creative Commons Attribution 4.0 International "
            "(CC BY 4.0); cite Feenstra, Inklaar, Timmer 2015."
        ),
        "local_files": [PWT_XLSX_NAME],
        "ingestion_status": "downloaded",
        "source_url": (
            "https://www.rug.nl/ggdc/productivity/pwt/"
            "pwt-releases/pwt1001"
        ),
        "checksum_sha256": sha,
    }
    (bundle_target / "metadata.json").write_text(
        json.dumps(metadata_payload, indent=2),
        encoding="utf-8",
    )
    return staged_xlsx_path


def test_pwt_year_2023_cleans_up_pre_existing_stale_observations(
    pwt_xlsx_dir: Path,
    pwt_init_test_db: str,
) -> None:
    """Phase B Increment B regression proof: ``year=2023`` MUST
    clean up any pre-existing stale ``source_observations``
    rows AND persist the ``sources`` row.

    Setup: seed a stale PWT 2023 observation directly via the
    ORM (simulating a previous bad run that wrote a 2023 row).
    Then run the production CLI ``ingest-source --source pwt
    --year 2023`` path. After the run, the 2023 row MUST be
    gone (the year=2023 corrective run cleans up its own
    scope) AND the ``sources`` row for "Penn World Table"
    MUST persist (so subsequent Stage 9+ joins can resolve
    the source_id).

    Manifest assertion: the run still records the
    ``requested_year_out_of_coverage`` warning so downstream
    Stage 12 manual-review queue can surface the gap.

    DOMAIN-RED: the original code skipped the DB write block
    entirely on an empty transformed frame, so the stale
    2023 row survived the corrective run AND the ``sources``
    row was not upserted. The test fails at the 2023 cleanup
    assertion; the production fix removes the ``if not
    long_df.empty:`` guard.
    """
    runner = CliRunner()

    # ---- Seed a stale PWT 2023 observation ------------------------
    with session_scope(pwt_init_test_db) as session:
        # Register the PWT source so the FK constraint is satisfied.
        from leaders_db.ingest.sources.pwt.db_helpers import (
            register_pwt_source,
        )
        source_id = register_pwt_source(session)

        # Insert a stale 2023 observation (simulating a previous
        # bad run that wrote a proxy / stale-fill row).
        stale_obs = SourceObservation(
            source_id=source_id,
            country_id=None,
            leader_id=None,
            year=2023,
            variable_name="pwt_real_gdp_expenditure_side",
            raw_value="stale_proxy_2019_value",
            normalized_value=12345.6,
            unit=None,
            source_row_reference="pwt:Data:USA:2023:rgdpe",
            confidence=None,
            notes="stale 2023 row seeded for regression test",
        )
        session.add(stale_obs)

    # Confirm the stale row is present before the run.
    with session_scope(pwt_init_test_db) as session:
        pre_count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2023,
            )).scalar_one()
    assert pre_count == 1, (
        f"test setup: expected 1 stale 2023 observation "
        f"before the corrective run; got {pre_count}"
    )

    # ---- Run the production CLI path ------------------------------
    result = runner.invoke(
        app,
        ["ingest-source", "--source", "pwt", "--year", "2023"],
    )
    assert result.exit_code == 0, (
        f"CLI failed: exit={result.exit_code}, stdout={result.stdout!r}"
    )

    # ---- Assert the stale 2023 row is gone ------------------------
    with session_scope(pwt_init_test_db) as session:
        post_count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2023,
            )).scalar_one()
    assert post_count == 0, (
        f"corrective year=2023 run must delete pre-existing "
        f"stale 2023 observations; got {post_count} after the run. "
        f"This is the Phase B Increment B reviewer regression: the "
        f"DB write block must NOT be skipped on an empty transformed "
        f"frame."
    )

    # ---- Assert the sources row persists --------------------------
    with session_scope(pwt_init_test_db) as session:
        pwt_sources = session.execute(
            select(Source).where(Source.source_name == "Penn World Table"),
        ).scalars().all()
    assert pwt_sources, (
        "corrective year=2023 run must still upsert the PWT "
        "sources row (idempotent source registration); got no "
        "Penn World Table rows"
    )
    pwt_source = pwt_sources[0]
    assert pwt_source.version == "10.01"
    assert pwt_source.coverage_start_year == 1950
    assert pwt_source.coverage_end_year == 2019

    # ---- Assert the manifest warning persists ---------------------
    manifest_path = (
        pwt_xlsx_dir.parent.parent
        / "processed"
        / PWT_SOURCE_KEY
        / "pwt_run_manifest.json"
    )
    assert manifest_path.is_file(), (
        f"manifest not written at {manifest_path}"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    codes = {
        w.get("code")
        for w in payload.get("warnings", [])
        if isinstance(w, dict)
    }
    assert "requested_year_out_of_coverage" in codes, (
        f"manifest must record requested_year_out_of_coverage "
        f"warning for year=2023; got codes={codes}"
    )


def test_pwt_registry_year_2023_cleans_up_pre_existing_stale_observations(
    pwt_xlsx_dir: Path,
    pwt_init_test_db: str,
) -> None:
    """Phase B Increment B regression proof: the registry
    path (``registry.ingest_source``) for ``year=2023`` MUST
    clean up any pre-existing stale ``source_observations``
    rows AND persist the ``sources`` row.

    Mirrors the CLI regression proof but exercises the
    registry runner path so the production path is covered
    end-to-end (CLI -> registry -> adapter).

    DOMAIN-RED: the original code skipped the DB write block
    entirely on an empty transformed frame, so the stale
    2023 row survived the corrective run AND the ``sources``
    row was not upserted.
    """
    from leaders_db.ingest.registry import (
        ingest_source,
        register,
        unregister,
    )
    from leaders_db.ingest.sources.pwt import PWTAdapter
    from leaders_db.ingest.sources.pwt.db_helpers import (
        register_pwt_source,
    )

    # ---- Seed a stale PWT 2023 observation ------------------------
    with session_scope(pwt_init_test_db) as session:
        source_id = register_pwt_source(session)
        stale_obs = SourceObservation(
            source_id=source_id,
            country_id=None,
            leader_id=None,
            year=2023,
            variable_name="pwt_real_gdp_expenditure_side",
            raw_value="stale_proxy_2019_value",
            normalized_value=12345.6,
            unit=None,
            source_row_reference="pwt:Data:USA:2023:rgdpe",
            confidence=None,
            notes="stale 2023 row seeded for regression test",
        )
        session.add(stale_obs)

    with session_scope(pwt_init_test_db) as session:
        pre_count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2023,
            )).scalar_one()
    assert pre_count == 1

    # ---- Run the production registry path -------------------------
    register("pwt", PWTAdapter())
    try:
        result = ingest_source(
            IngestRequest(
                source_key="pwt",
                year=2023,
                raw_root=pwt_xlsx_dir.parent,
            ),
        )
    finally:
        unregister("pwt")

    # ---- Assert the stale 2023 row is gone ------------------------
    with session_scope(pwt_init_test_db) as session:
        post_count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2023,
            )).scalar_one()
    assert post_count == 0, (
        f"corrective year=2023 registry run must delete "
        f"pre-existing stale 2023 observations; got {post_count} "
        f"after the run"
    )

    # ---- Assert the sources row persists --------------------------
    with session_scope(pwt_init_test_db) as session:
        pwt_sources = session.execute(
            select(Source).where(Source.source_name == "Penn World Table"),
        ).scalars().all()
    assert pwt_sources, (
        "corrective year=2023 registry run must still upsert the "
        "PWT sources row (idempotent source registration); got no "
        "Penn World Table rows"
    )

    # ---- Manifest warning persists -------------------------------
    assert result.manifest_path is not None
    payload = json.loads(
        result.manifest_path.read_text(encoding="utf-8"),
    )
    codes = {
        w.get("code")
        for w in payload.get("warnings", [])
        if isinstance(w, dict)
    }
    assert "requested_year_out_of_coverage" in codes


def test_pwt_adapter_ingest_request_honors_all_request_scopes(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """Phase B Increment B regression proof:
    ``PWTAdapter.ingest(request)`` honors ``request.raw_root``,
    ``request.processed_root``, AND ``request.database_url``
    end-to-end -- outputs and DB rows land ONLY at the
    requested locations.

    The convenience method must NOT delegate to
    ``ingest_pwt()`` with the request scope dropped; the
    registry path and the convenience path must produce
    identical artifacts at the requested locations.

    Setup:
      - Custom raw root stages a valid PWT bundle at
        ``<tmp>/custom-raw/pwt``.
      - Custom processed root redirects the parquet to
        ``<tmp>/custom-processed/pwt``.
      - Custom database URL points at
        ``<tmp>/custom-db/leaders_db.sqlite``.

    Assertion: the parquet lands at
    ``<tmp>/custom-processed/pwt/pwt_country_year.parquet``,
    the manifest at
    ``<tmp>/custom-processed/pwt/pwt_run_manifest.json``,
    and the DB rows land at the custom SQLite file -- and
    NOT at any default location.
    """
    from leaders_db.ingest.sources.pwt import PWTAdapter

    # ---- Stage the PWT bundle under a custom raw root ------------
    custom_raw_root = tmp_path / "custom-raw"
    custom_processed_root = tmp_path / "custom-processed"
    custom_db_root = tmp_path / "custom-db"
    custom_db_root.mkdir(parents=True, exist_ok=True)
    custom_db_path = custom_db_root / "leaders_db.sqlite"
    custom_db_url = f"sqlite:///{custom_db_path.as_posix()}"

    fixtures_dir = (
        Path(__file__).resolve().parents[3] / "fixtures" / "pwt"
    )
    _stage_pwt_bundle_for_regression(
        custom_raw_root, fixtures_dir,
    )

    # ---- Drive the convenience path with all request scopes ------
    request = IngestRequest(
        source_key="pwt",
        year=2019,
        raw_root=custom_raw_root,
        processed_root=custom_processed_root,
        database_url=custom_db_url,
    )
    result = PWTAdapter().ingest(request)

    # ---- Parquet at custom processed root only -------------------
    expected_parquet = (
        custom_processed_root / PWT_SOURCE_KEY / "pwt_country_year.parquet"
    )
    assert expected_parquet.is_file(), (
        f"parquet must land at {expected_parquet}; got "
        f"result.parquet_path={result.parquet_path!r}"
    )
    assert result.parquet_path == expected_parquet
    # No default processed-root artifact leaked.
    default_processed_root = isolated_data_lake / "data" / "processed"
    if (default_processed_root / PWT_SOURCE_KEY).exists():
        assert not (
            default_processed_root
            / PWT_SOURCE_KEY
            / "pwt_country_year.parquet"
        ).exists(), (
            "parquet must NOT land at the default data-lake "
            "processed root"
        )

    # ---- Manifest at custom processed root only ------------------
    expected_manifest = (
        custom_processed_root / PWT_SOURCE_KEY / "pwt_run_manifest.json"
    )
    assert expected_manifest.is_file(), (
        f"manifest must land at {expected_manifest}; got "
        f"result.manifest_path={result.manifest_path!r}"
    )
    assert result.manifest_path == expected_manifest

    # ---- DB rows at custom SQLite URL only -----------------------
    # The custom DB was initialized by the adapter's DB write block.
    assert custom_db_path.is_file(), (
        f"custom DB must exist at {custom_db_path}"
    )
    custom_engine = create_engine(
        custom_db_url, future=True,
        connect_args={"check_same_thread": False},
    )
    CustomSession = sessionmaker(
        bind=custom_engine, expire_on_commit=False, future=True,
    )
    with CustomSession() as session:
        pwt_sources = session.execute(
            select(Source).where(Source.source_name == "Penn World Table"),
        ).scalars().all()
    assert pwt_sources, (
        "DB rows must land at the custom SQLite URL; got no "
        "Penn World Table sources"
    )
    with CustomSession() as session:
        obs_count = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()
    assert obs_count == 15, (
        f"expected 15 source_observations rows from year=2019 "
        f"(USA 6 + MEX 6 + SWE 3) at the custom SQLite URL; got "
        f"{obs_count}"
    )

    # ---- No DB rows at the default SQLite file -------------------
    default_db = (
        isolated_data_lake / "data" / "catalog" / "leaders_db.sqlite"
    )
    if default_db.is_file():
        default_url = f"sqlite:///{default_db.as_posix()}"
        default_engine = create_engine(
            default_url, future=True,
            connect_args={"check_same_thread": False},
        )
        DefaultSession = sessionmaker(
            bind=default_engine, expire_on_commit=False, future=True,
        )
        with DefaultSession() as session:
            default_obs_count = session.execute(
                select(func.count(SourceObservation.id)),
            ).scalar_one()
        assert default_obs_count == 0, (
            f"DB rows must NOT leak to the default SQLite file; "
            f"got {default_obs_count} rows at the default URL"
        )


def test_ingest_pwt_convenience_honors_all_request_scopes(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """Phase B Increment B regression proof:
    ``ingest_pwt(xlsx_path=..., parquet_path=..., database_url=...)``
    faithfully converts all public overrides into request-scoped
    fields so the adapter reads / writes / persists ONLY at the
    requested locations.

    The convenience function must NOT silently fall back to the
    default data-lake locations when the caller passes overrides;
    every public argument must propagate into the request the
    adapter sees.

    Setup:
      - xlsx_path = <tmp>/custom-raw/pwt/pwt1001.xlsx
      - parquet_path = <tmp>/custom-processed/pwt_country_year.parquet
      - database_url = sqlite:///<tmp>/custom-db/leaders_db.sqlite

    Assertion: the parquet lands at the requested parquet_path,
    the manifest next to it, and the DB rows land at the custom
    SQLite file -- and NOT at any default location.
    """
    from leaders_db.ingest.sources.pwt import ingest_pwt

    # ---- Stage the PWT bundle under a custom raw root ------------
    custom_raw_root = tmp_path / "custom-raw"
    custom_processed_root = tmp_path / "custom-processed"
    custom_db_root = tmp_path / "custom-db"
    custom_db_root.mkdir(parents=True, exist_ok=True)
    custom_db_path = custom_db_root / "leaders_db.sqlite"
    custom_db_url = f"sqlite:///{custom_db_path.as_posix()}"

    fixtures_dir = (
        Path(__file__).resolve().parents[3] / "fixtures" / "pwt"
    )
    staged_xlsx = _stage_pwt_bundle_for_regression(
        custom_raw_root, fixtures_dir,
    )

    custom_parquet_path = (
        custom_processed_root / "pwt_country_year.parquet"
    )
    custom_processed_root.mkdir(parents=True, exist_ok=True)
    result = ingest_pwt(
        year=2019,
        xlsx_path=staged_xlsx,
        parquet_path=custom_parquet_path,
        database_url=custom_db_url,
    )

    # ---- Parquet at the requested parquet_path ------------------
    assert result.parquet_path == custom_parquet_path, (
        f"parquet must land at the requested parquet_path; got "
        f"{result.parquet_path!r}"
    )
    assert result.parquet_path.is_file()

    # ---- DB rows at the custom SQLite URL -----------------------
    custom_engine = create_engine(
        custom_db_url, future=True,
        connect_args={"check_same_thread": False},
    )
    CustomSession = sessionmaker(
        bind=custom_engine, expire_on_commit=False, future=True,
    )
    with CustomSession() as session:
        obs_count = session.execute(
            select(func.count(SourceObservation.id)),
        ).scalar_one()
    assert obs_count == 15, (
        f"expected 15 source_observations rows at the custom "
        f"SQLite URL; got {obs_count}"
    )

    # ---- No DB rows at the default SQLite file ------------------
    default_db = (
        isolated_data_lake / "data" / "catalog" / "leaders_db.sqlite"
    )
    if default_db.is_file():
        default_url = f"sqlite:///{default_db.as_posix()}"
        default_engine = create_engine(
            default_url, future=True,
            connect_args={"check_same_thread": False},
        )
        DefaultSession = sessionmaker(
            bind=default_engine, expire_on_commit=False, future=True,
        )
        with DefaultSession() as session:
            default_obs_count = session.execute(
                select(func.count(SourceObservation.id)),
            ).scalar_one()
        assert default_obs_count == 0, (
            f"DB rows must NOT leak to the default SQLite file; "
            f"got {default_obs_count} rows at the default URL"
        )


# ---------------------------------------------------------------------------
# 6. Phase B Increment B second-pass regression proofs
# ---------------------------------------------------------------------------
#
# Phase B Increment B second-pass reviewer feedback flagged two
# regressions in the convenience / DB paths after the first-pass fix:
#
# - ``PWTAdapter.transform`` only forwarded ``request.year`` to the
#   transform layer and silently dropped ``request.years`` (the
#   tuple form) and ``request.country_filter``. A registry runner
#   call with ``IngestRequest(years=(2018,))`` would still transform
#   every year in the wide frame, and a call with
#   ``IngestRequest(country_filter=('USA',))`` would still emit
#   MEX / SWE rows.
# - ``write_pwt_observations`` only filtered the per-year cleanup
#   pass by ``years_filter`` and never scoped to ``country_filter``;
#   a corrective ``country_filter=('USA',)`` re-run could
#   accidentally delete MEX / SWE rows that the request did not
#   scope (a silent cross-country overwrite).
#
# The tests below are the regression proofs the reviewer demanded.


def _count_obs_by_year_and_iso3(
    session: Session,
) -> dict[tuple[str, int], int]:
    """Group ``source_observations`` rows by ``(iso3, year)`` from
    the canonical locator ``pwt:Data:<iso3>:<year>:<raw_column>``.
    """
    refs = session.execute(
        select(SourceObservation.source_row_reference),
    ).scalars().all()
    counts: dict[tuple[str, int], int] = {}
    for ref in refs:
        parts = (ref or "").split(":")
        if len(parts) < 5:
            continue
        iso3 = parts[2]
        year = int(parts[3])
        counts[(iso3, year)] = counts.get((iso3, year), 0) + 1
    return counts


def test_registry_ingest_source_years_tuple_persists_only_requested_years(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """Phase B Increment B second-pass regression proof:
    ``registry.ingest_source(IngestRequest(years=(2018,)))``
    persists ONLY 2018 rows -- no 2019 leakage.

    Setup: stage the PWT bundle under a request-scoped raw root
    so the registry path can drive the production adapter
    without going through the default data-lake.

    Assertion: the persisted ``source_observations`` rows have
    ``year == 2018`` only. Any 2019 row is a regression -- the
    transform must apply the ``years`` filter (the previous
    Increment B pass only forwarded the single-year ``year``
    shortcut and silently dropped ``years=``).
    """
    from leaders_db.db.engine import init_database
    from leaders_db.ingest.registry import (
        ingest_source,
        register,
        unregister,
    )
    from leaders_db.ingest.sources.pwt import PWTAdapter

    custom_raw = tmp_path / "raw-years"
    custom_db_path = tmp_path / "db-years" / "leaders_db.sqlite"
    custom_db_path.parent.mkdir(parents=True, exist_ok=True)
    custom_db_url = f"sqlite:///{custom_db_path.as_posix()}"
    init_database(custom_db_url)

    _stage_pwt_bundle_for_regression(custom_raw, _PWT_FIXTURES_DIR)

    register("pwt", PWTAdapter())
    try:
        result = ingest_source(
            IngestRequest(
                source_key="pwt",
                years=(2018,),
                raw_root=custom_raw,
                database_url=custom_db_url,
            ),
        )
    finally:
        unregister("pwt")

    assert result.observation_rows == 2, (
        f"IngestRequest(years=(2018,)) must persist only the 2 USA "
        f"2018 cells; got {result.observation_rows} rows"
    )
    assert tuple(result.years) == (2018,), (
        f"IngestResult.years must reflect the request-scoped years "
        f"tuple; got {tuple(result.years)}"
    )

    custom_engine = create_engine(
        custom_db_url, future=True,
        connect_args={"check_same_thread": False},
    )
    CustomSession = sessionmaker(
        bind=custom_engine, expire_on_commit=False, future=True,
    )
    with CustomSession() as session:
        counts = _count_obs_by_year_and_iso3(session)
    assert set(counts.keys()) == {("USA", 2018)}, (
        f"IngestRequest(years=(2018,)) must persist ONLY USA 2018 "
        f"rows; got {sorted(counts.keys())}"
    )
    # Sanity: assert the DB also has zero 2019 rows (no leakage).
    with CustomSession() as session:
        year_2019_count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.year == 2019,
            ),
        ).scalar_one()
    assert year_2019_count == 0, (
        f"IngestRequest(years=(2018,)) must not write 2019 rows; "
        f"got {year_2019_count}"
    )


def test_pwt_adapter_ingest_country_filter_persists_only_filtered_iso3s(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """Phase B Increment B second-pass regression proof:
    ``PWTAdapter.ingest(IngestRequest(country_filter=('USA',)))``
    persists ONLY USA locator rows -- no MEX / SWE leakage.

    Setup: stage the PWT bundle under a request-scoped raw root
    so the convenience-path test is isolated from the default
    data-lake.

    Assertion: the persisted ``source_observations`` rows have
    iso3 == "USA" ONLY (per the canonical locator
    ``pwt:Data:<iso3>:<year>:<raw_column>``). Any MEX / SWE
    row is a regression -- the transform must apply the
    ``country_filter`` (the previous Increment B pass silently
    dropped ``country_filter=``).
    """
    from leaders_db.db.engine import init_database
    from leaders_db.ingest.sources.pwt import PWTAdapter

    custom_raw = tmp_path / "raw-country-filter"
    custom_db_path = tmp_path / "db-country-filter" / "leaders_db.sqlite"
    custom_db_path.parent.mkdir(parents=True, exist_ok=True)
    custom_db_url = f"sqlite:///{custom_db_path.as_posix()}"
    init_database(custom_db_url)

    _stage_pwt_bundle_for_regression(custom_raw, _PWT_FIXTURES_DIR)

    result = PWTAdapter().ingest(
        IngestRequest(
            source_key="pwt",
            country_filter=("USA",),
            raw_root=custom_raw,
            database_url=custom_db_url,
        ),
    )

    # All-years, USA-only: USA 2018 = 2 + USA 2019 = 6 = 8 rows.
    assert result.observation_rows == 8, (
        f"IngestRequest(country_filter=('USA',)) must persist only "
        f"USA cells (USA 2018 = 2 + USA 2019 = 6 = 8); got "
        f"{result.observation_rows}"
    )

    custom_engine = create_engine(
        custom_db_url, future=True,
        connect_args={"check_same_thread": False},
    )
    CustomSession = sessionmaker(
        bind=custom_engine, expire_on_commit=False, future=True,
    )
    with CustomSession() as session:
        counts = _count_obs_by_year_and_iso3(session)
    observed_iso3s = {iso3 for iso3, _ in counts.keys()}
    assert observed_iso3s == {"USA"}, (
        f"IngestRequest(country_filter=('USA',)) must persist only "
        f"USA iso3 rows; got {sorted(observed_iso3s)}"
    )
    assert counts.get(("USA", 2018), 0) == 2
    assert counts.get(("USA", 2019), 0) == 6
    # Sanity: no MEX / SWE rows at all.
    for forbidden_iso3 in ("MEX", "SWE"):
        for year in (2018, 2019):
            assert counts.get((forbidden_iso3, year), 0) == 0, (
                f"IngestRequest(country_filter=('USA',)) leaked a "
                f"{forbidden_iso3} {year} row; "
                f"counts[{forbidden_iso3}, {year}]="
                f"{counts.get((forbidden_iso3, year), 0)}"
            )


def test_registry_ingest_source_country_filter_does_not_delete_unscoped_iso3s(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """Phase B Increment B second-pass regression proof:
    the ``country_filter`` cleanup pass is scoped to the
    request-scoped iso3s only -- pre-existing MEX / SWE rows
    survive a corrective ``country_filter=('USA',)`` re-run.

    Setup:
      1. Run a full (no-country-filter) ingest so MEX 2019,
         SWE 2019, and USA 2018/2019 rows are persisted.
      2. Run a corrective ``country_filter=('USA',)`` ingest
         with ``years=(2019,)``.
      3. Assert MEX 2019 + SWE 2019 rows are PRESERVED (the
         corrective run scoped its cleanup to ``USA`` +
         ``year=2019`` only; the previous Increment B pass
         cleaned up by year alone and silently deleted every
         2019 row regardless of iso3).

    DOMAIN-RED until the cleanup-pass fix lands.
    """
    from leaders_db.db.engine import init_database
    from leaders_db.ingest.registry import (
        ingest_source,
        register,
        unregister,
    )
    from leaders_db.ingest.sources.pwt import PWTAdapter

    custom_raw = tmp_path / "raw-country-cleanup"
    custom_db_path = tmp_path / "db-country-cleanup" / "leaders_db.sqlite"
    custom_db_path.parent.mkdir(parents=True, exist_ok=True)
    custom_db_url = f"sqlite:///{custom_db_path.as_posix()}"
    init_database(custom_db_url)
    _stage_pwt_bundle_for_regression(custom_raw, _PWT_FIXTURES_DIR)

    # First run: full ingest (USA + MEX + SWE across 2018+2019).
    register("pwt", PWTAdapter())
    try:
        ingest_source(
            IngestRequest(
                source_key="pwt",
                raw_root=custom_raw,
                database_url=custom_db_url,
            ),
        )
    finally:
        unregister("pwt")

    custom_engine = create_engine(
        custom_db_url, future=True,
        connect_args={"check_same_thread": False},
    )
    CustomSession = sessionmaker(
        bind=custom_engine, expire_on_commit=False, future=True,
    )
    with CustomSession() as session:
        baseline = _count_obs_by_year_and_iso3(session)
    assert baseline.get(("MEX", 2019), 0) == 6, (
        f"baseline run must include MEX 2019 rows; got "
        f"{baseline.get(('MEX', 2019), 0)}"
    )
    assert baseline.get(("SWE", 2019), 0) == 3, (
        f"baseline run must include SWE 2019 rows; got "
        f"{baseline.get(('SWE', 2019), 0)}"
    )

    # Second run: corrective ``country_filter=('USA',)`` +
    # ``years=(2019,)``.
    register("pwt", PWTAdapter())
    try:
        ingest_source(
            IngestRequest(
                source_key="pwt",
                years=(2019,),
                country_filter=("USA",),
                raw_root=custom_raw,
                database_url=custom_db_url,
            ),
        )
    finally:
        unregister("pwt")

    with CustomSession() as session:
        after = _count_obs_by_year_and_iso3(session)

    # USA 2019 must still be 6 rows (the corrective run replaced
    # USA 2019 with the same content).
    assert after.get(("USA", 2019), 0) == 6, (
        f"corrective run must leave USA 2019 at 6 rows; got "
        f"{after.get(('USA', 2019), 0)}"
    )
    # MEX 2019 + SWE 2019 must SURVIVE the corrective run.
    assert after.get(("MEX", 2019), 0) == 6, (
        f"corrective country_filter=('USA',) run must NOT delete "
        f"MEX 2019 rows; got {after.get(('MEX', 2019), 0)} "
        f"(was {baseline.get(('MEX', 2019), 0)} before). This is "
        "the Phase B Increment B second-pass regression: the "
        "cleanup pass must scope to iso3_filter."
    )
    assert after.get(("SWE", 2019), 0) == 3, (
        f"corrective country_filter=('USA',) run must NOT delete "
        f"SWE 2019 rows; got {after.get(('SWE', 2019), 0)}"
    )
    # USA 2018 must SURVIVE (years filter was 2019 only).
    assert after.get(("USA", 2018), 0) == 2, (
        f"corrective years=(2019,) run must NOT delete USA 2018 "
        f"rows; got {after.get(('USA', 2018), 0)}"
    )


__all__ = []




__all__ = []
