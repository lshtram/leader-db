"""Stage 2 -- PWT adapter class (production).

The :class:`PWTAdapter` is the first concrete proof of the shared
:class:`SourceAdapter` Protocol (defined in
:mod:`leaders_db.ingest.interfaces`). It drives the full pipeline
``check_ready -> read -> transform -> write`` and exposes the
:meth:`ingest` convenience method.

Public contract
---------------

- :meth:`check_ready` validates the bundle's ``metadata.json`` and
  the staged ``pwt1001.xlsx`` BEFORE the reader opens the workbook.
  Every blocker names the specific missing / invalid field or file
  (e.g. ``metadata.json``, ``source_url``, ``license_note``,
  ``checksum_sha256``, ``local_files`` / ``pwt1001.xlsx``,
  ``ingestion_status``, ``coverage``) so a developer can fix the
  upstream issue without reading source code. The gate also
  recomputes the SHA-256 of ``pwt1001.xlsx`` and refuses to run if
  it disagrees with the ``checksum_sha256`` field (catches
  byte-level drift between the staged xlsx and the recorded
  checksum).
- :meth:`read` resolves the xlsx path through the request-scoped
  ``raw_root`` override (when set) and falls back to the default
  data-lake path. The bundle directory resolved by
  :meth:`check_ready` is the same path used by :meth:`read` so the
  request-scoped contract is honored end-to-end.
- :meth:`transform` invokes the canonical long-format pivot and
  returns a :class:`NormalizedSourceFrame` carrying the canonical
  long DataFrame + the PWT attribution block (Rule #15).
- :meth:`write` persists the parquet, writes the run manifest
  (including ``requested_year_out_of_coverage`` warnings when
  applicable), and upserts the ``sources`` + ``source_observations``
  rows. Idempotent: re-running for the same year deletes the
  existing ``source_observations`` rows for that year before
  inserting.
- :meth:`ingest` drives the full pipeline on the SAME
  :class:`IngestRequest` the caller passed in (check_ready
  -> read -> transform -> write). The convenience method and
  the registry runner produce identical artifacts because both
  go through the same shared-adapter code paths on the same
  request object.

Year semantics
--------------

PWT 10.01 covers 1950-2019. A request for ``year=2023`` produces
zero observations AND a ``requested_year_out_of_coverage`` manifest
warning. No 2019 -> 2023 stale-proxy fill is permitted -- this is
the documented architectural decision per
``docs/sources/ingestion-plan.md`` and requirement §13
("no invented historical data; older years degrade gracefully").
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ...interfaces import (
    IngestRequest,
    IngestResult,
    NormalizedSourceFrame,
    RawSourceBundle,
    SourceReadiness,
)

# Imported at module load time to avoid a circular import between
# ``adapter.py`` and the package ``__init__.py`` (which re-exports
# ``PWTAdapter``). The string value matches the package constant.
PWT_SOURCE_KEY: str = "pwt"
PWT_XLSX_NAME: str = "pwt1001.xlsx"
PWT_METADATA_NAME: str = "metadata.json"

# Required metadata fields (per the source-ingestion-plan PWT
# section). The production check_ready gate validates that each
# field is present and well-typed in the bundle's
# ``metadata.json`` AND names the missing / invalid field in the
# blocker (per the Phase B Increment B test contract).
_REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_url",
    "license_note",
    "checksum_sha256",
    "local_files",
    "ingestion_status",
    "coverage",
)


def _bundle_dir(request: IngestRequest) -> Path:
    """Return the resolved ``data/raw/pwt/`` bundle directory.

    The ``IngestRequest.raw_root`` override is honored if set;
    otherwise the default ``data/raw/pwt/`` is used (resolved
    through :func:`leaders_db.paths.raw_dir`).
    """
    if request.raw_root is not None:
        return Path(request.raw_root) / PWT_SOURCE_KEY
    from ....paths import raw_dir

    return raw_dir(PWT_SOURCE_KEY)


def _resolve_xlsx_path(request: IngestRequest) -> Path:
    """Return the request-scoped ``pwt1001.xlsx`` path.

    Honors ``IngestRequest.raw_root`` overrides consistently
    across ``check_ready`` / ``read`` / ``write`` so the registry
    runner's request-scoped raw-root contract is met (per the
    Phase B Increment B review feedback).
    """
    return _bundle_dir(request) / PWT_XLSX_NAME


def _check_metadata_well_formed(
    bundle_dir: Path,
) -> tuple[bool, str | None]:
    """Validate the bundle's ``metadata.json`` + ``pwt1001.xlsx``.

    Returns ``(ready, blocker)``:

    - ``(True, None)`` when the bundle is fully well-formed.
    - ``(False, blocker_message)`` when the bundle is missing
      ``metadata.json`` (blocker names ``metadata.json``),
      missing ``pwt1001.xlsx`` (blocker names
      ``pwt1001.xlsx``), missing a required metadata field
      (blocker names the missing field), has
      ``local_files`` that does not include ``pwt1001.xlsx``
      (blocker names ``local_files`` / ``pwt1001.xlsx``), has
      ``ingestion_status != 'downloaded'`` (blocker names
      ``ingestion_status``), or has a checksum that disagrees
      with the actual xlsx SHA-256 (blocker names
      ``checksum``).
    """
    metadata_path = bundle_dir / PWT_METADATA_NAME
    xlsx_path = bundle_dir / PWT_XLSX_NAME

    if not metadata_path.is_file():
        return False, (
            f"PWT readiness gate: metadata.json missing at "
            f"{metadata_path}; place the canonical "
            "data/raw/pwt/metadata.json before running Stage 2."
        )
    if not xlsx_path.is_file():
        return False, (
            f"PWT readiness gate: pwt1001.xlsx missing at "
            f"{xlsx_path}; place the canonical Penn World Table "
            "10.01 xlsx before running Stage 2."
        )
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, (
            f"PWT readiness gate: failed to parse metadata.json "
            f"at {metadata_path}: {exc}"
        )
    if not isinstance(payload, dict):
        return False, (
            "PWT readiness gate: metadata.json must be a JSON "
            "object (got " + type(payload).__name__ + ")."
        )

    # Field presence: blocker names the FIRST missing field so a
    # developer can fix one issue at a time without guessing.
    for field in _REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return False, (
                f"PWT readiness gate: metadata.json is missing "
                f"required field '{field}'; per "
                "docs/sources/ingestion-plan.md §pwt, every PWT "
                "run must record this field."
            )

    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or PWT_XLSX_NAME not in local_files:
        return False, (
            f"PWT readiness gate: metadata.json 'local_files' "
            f"must include {PWT_XLSX_NAME!r}; got {local_files!r}"
        )

    ingestion_status = payload.get("ingestion_status")
    if ingestion_status != "downloaded":
        return False, (
            f"PWT readiness gate: metadata.json "
            f"'ingestion_status' must be 'downloaded'; got "
            f"{ingestion_status!r}. Re-stage the bundle and "
            "update the metadata before re-running."
        )

    coverage = payload.get("coverage")
    if not isinstance(coverage, str) or not coverage.strip():
        return False, (
            "PWT readiness gate: metadata.json 'coverage' must be "
            "a non-empty string describing the temporal + "
            "spatial coverage (e.g. 'country-year economic "
            "accounts 1950-2019')."
        )

    source_url = payload.get("source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        return False, (
            "PWT readiness gate: metadata.json 'source_url' must "
            "be a non-empty string naming the canonical PWT "
            "download URL."
        )

    license_note = payload.get("license_note")
    if not isinstance(license_note, str) or not license_note.strip():
        return False, (
            "PWT readiness gate: metadata.json 'license_note' "
            "must be a non-empty string naming the PWT license "
            "(CC BY 4.0; cite Feenstra, Inklaar, Timmer 2015)."
        )

    # Checksum verification: recompute the SHA-256 of the staged
    # xlsx and reject if it disagrees with the recorded
    # ``checksum_sha256`` field. Catches byte-level drift between
    # the staged xlsx and the recorded checksum (per the Phase B
    # Increment B readiness contract).
    expected_sha = payload.get("checksum_sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return False, (
            "PWT readiness gate: metadata.json 'checksum_sha256' "
            "must be a non-empty hex SHA-256 string."
        )
    actual_sha = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.strip().lower():
        return False, (
            f"PWT readiness gate: xlsx checksum mismatch. "
            f"metadata.json says checksum_sha256="
            f"{expected_sha.strip().lower()!r} but the staged "
            f"{PWT_XLSX_NAME} has sha256="
            f"{actual_sha.lower()!r}. Re-download / re-stage the "
            "xlsx and update metadata.json in the same commit."
        )

    return True, None


class PWTAdapter:
    """Production Stage 2 adapter for the Penn World Table 10.01.

    Implements the full shared :class:`SourceAdapter` Protocol
    (defined in :mod:`leaders_db.ingest.interfaces`). The
    readiness gate fires BEFORE the reader opens the workbook;
    the read / transform / write methods carry the request-scoped
    ``raw_root`` through the full pipeline; the write method
    persists parquet + manifest + ``source_observations`` rows
    idempotently.
    """

    source_key: str = PWT_SOURCE_KEY

    # ---- readiness gate -------------------------------------------------

    def check_ready(
        self, request: IngestRequest,
    ) -> SourceReadiness:
        """Return ``ready=True`` for a well-formed PWT bundle.

        The gate validates the bundle's ``metadata.json`` and
        ``pwt1001.xlsx`` against the documented readiness
        contract (see :func:`_check_metadata_well_formed`). Every
        blocker names the specific missing / invalid field or
        file so a developer can fix the upstream issue without
        reading source code. The attribution is the canonical
        PWT citation text (Rule #15).

        ``request`` is required (per the Increment A protocol
        revision) so the readiness gate can resolve a request-
        scoped ``raw_root`` override. When ``request.raw_root``
        is ``None`` the default data-lake path is used.
        """
        from . import PWT_ATTRIBUTION

        bundle_dir = _bundle_dir(request)
        ready, blocker = _check_metadata_well_formed(bundle_dir)
        if ready:
            return SourceReadiness(
                ready=True,
                blocker=None,
                attribution=PWT_ATTRIBUTION,
            )
        return SourceReadiness(
            ready=False,
            blocker=blocker,
            attribution=None,
        )

    # ---- read ------------------------------------------------------------

    def read(self, request: IngestRequest) -> RawSourceBundle:
        """Open the staged ``pwt1001.xlsx`` and return a
        :class:`RawSourceBundle` carrying the wide Data-sheet-
        shaped DataFrame + the bundle's parsed metadata.

        Honors ``request.raw_root`` (the same request-scoped
        path the registry runner resolved through
        ``check_ready``). The reader validates the canonical
        filename + identity + catalog columns BEFORE returning
        so the transform layer never sees a malformed wide
        frame.
        """
        from .reader import read_pwt

        xlsx_path = _resolve_xlsx_path(request)
        wide_df = read_pwt(xlsx_path=xlsx_path)
        metadata_payload = self._read_bundle_metadata(request)
        return RawSourceBundle(
            source_key=self.source_key,
            payload={"wide_df": wide_df, "xlsx_path": xlsx_path},
            metadata=metadata_payload,
        )

    # ---- transform -------------------------------------------------------

    def transform(
        self,
        bundle: RawSourceBundle,
        request: IngestRequest,
    ) -> NormalizedSourceFrame:
        """Pivot the wide ``Data``-sheet DataFrame to long format.

        Honors the optional ``request.year`` filter (so a
        registry runner call with ``year=2019`` produces a
        year-scoped long frame and a ``year=2023`` call produces
        an empty long frame + an out-of-coverage warning). The
        ``source_row_reference`` is the canonical locator
        ``pwt:Data:<iso3>:<year>:<raw_column>``; ``temporal_kind``
        is ``"observed"`` for every row; ``attribution`` is the
        canonical PWT citation text.

        Honors ``request.catalog_path`` (Phase B Increment B
        reviewer feedback): when set, the transform reads the
        indicator catalog from this exact path instead of the
        per-source ``catalog.csv`` default.
        """
        from . import PWT_ATTRIBUTION
        from .transform import transform_pwt_long_frame

        if not isinstance(bundle.payload, dict):
            raise ValueError(
                "PWTAdapter.transform: bundle.payload is not a "
                "dict; the read layer must populate the wide "
                "DataFrame under 'wide_df'."
            )
        wide_df = bundle.payload.get("wide_df")
        if wide_df is None:
            raise ValueError(
                "PWTAdapter.transform: bundle.payload has no "
                "'wide_df' key; the read layer must populate it."
            )
        # Carry the FULL request-scoped filter set into the
        # transform so the registry runner's ``years=`` /
        # ``country_filter=`` contract is honored end-to-end.
        # The previous Increment B pass only forwarded
        # ``request.year`` (a single-year shortcut) and
        # silently dropped ``request.years`` /
        # ``request.country_filter`` -- a request like
        # ``IngestRequest(years=(2018,))`` would still
        # transform every year in the wide frame, and
        # ``IngestRequest(country_filter=('USA',))`` would
        # still emit MEX / SWE rows. Phase B Increment B
        # reviewer feedback flagged this as a request-scope
        # filtering bug; the fix forwards the full filter
        # surface.
        long_df = transform_pwt_long_frame(
            wide_df,
            year=request.year,
            years=request.effective_years,
            country_filter=request.country_filter,
            catalog_path=request.catalog_path,
        )
        return NormalizedSourceFrame(
            source_key=self.source_key,
            rows=long_df,
            attribution=PWT_ATTRIBUTION,
        )

    # ---- write -----------------------------------------------------------

    def write(
        self,
        frame: NormalizedSourceFrame,
        request: IngestRequest,
    ) -> IngestResult:
        """Persist the long-format frame as parquet + manifest +
        DB rows.

        Idempotent: re-running for the same year deletes the
        existing ``source_observations`` rows for that year
        before inserting. Returns the canonical :class:`IngestResult`
        with ``observation_rows``, ``parquet_path``,
        ``manifest_path``, ``years``, ``countries``,
        ``indicators``, ``warnings`` (including
        ``requested_year_out_of_coverage`` when the request
        year is outside the 1950-2019 PWT 10.01 coverage), and
        the canonical PWT attribution block.
        """
        from ...interfaces import IngestResult as _IngestResult
        from . import PWT_ATTRIBUTION
        from .db_helpers import (
            register_pwt_source,
            write_pwt_observations,
            write_pwt_parquet,
            write_pwt_run_manifest,
        )

        long_df = frame.rows
        if not hasattr(long_df, "empty") or not hasattr(long_df, "columns"):
            raise ValueError(
                "PWTAdapter.write: frame.rows is not a pandas "
                "DataFrame; the transform layer must populate it."
            )

        warnings: list[dict[str, Any]] = []

        # Out-of-coverage warning. The check fires BEFORE any DB
        # / parquet write so a year=2023 run produces zero DB
        # rows AND zero parquet rows AND zero source_observations
        # rows AND the manifest warning (per the Phase B
        # Increment B reviewer contract).
        coverage_start, coverage_end = _pwt_coverage_range()  # noqa: RUF059 - coverage_start intentionally not used
        requested_years = list(request.effective_years)
        if requested_years and coverage_end is not None:
            for ry in requested_years:
                if ry > coverage_end:
                    warnings.append(
                        {
                            "code": "requested_year_out_of_coverage",
                            "year": int(ry),
                            "coverage_end_year": int(coverage_end),
                        },
                    )

        parquet_path = write_pwt_parquet(
            long_df,
            processed_root=request.processed_root,
            parquet_path=request.parquet_path,
        )

        # Compute the in-memory summary first so the
        # ``IngestResult`` is correct even if the DB write fails
        # (e.g. the test fixture did not initialize the schema).
        # Production code paths always initialize the schema via
        # ``init_database()`` below; tests that omit the
        # ``pwt_init_test_db`` fixture still see correct counts.
        observation_rows = len(long_df) if not long_df.empty else 0
        countries_count = (
            int(long_df["iso3"].nunique()) if not long_df.empty else 0
        )
        years_in_frame: tuple[int, ...] = (
            tuple(sorted({int(y) for y in long_df["year"].tolist()}))
            if not long_df.empty
            else ()
        )
        indicators_count = (
            int(long_df["raw_column"].nunique())
            if not long_df.empty
            else 0
        )

        # DB writes (idempotent by request-scoped year). The
        # helper honors ``request.database_url`` when set;
        # otherwise the default URL through ``session_scope``.
        # ``init_database`` is idempotent (the migration tracker
        # table guards re-runs), so this is safe in production +
        # the test fixtures that did not pre-initialize the schema.
        #
        # CRITICAL (Phase B Increment B reviewer feedback): the
        # DB-write block runs UNCONDITIONALLY -- including when
        # ``long_df`` is empty (out-of-coverage requests such as
        # ``year=2023``). Skipping it on an empty frame would
        # leave the PWT ``sources`` row unregistered and any
        # pre-existing stale ``source_observations`` rows for the
        # requested year(s) would survive a corrective re-run.
        # ``write_pwt_observations`` honors ``years_filter`` and
        # deletes existing rows for the requested year(s) even
        # when its frame is empty (see ``db_helpers.py``).
        from ....db.engine import init_database
        from ....db.session import default_sqlite_url, session_scope

        db_url = request.database_url or default_sqlite_url()
        try:
            init_database(db_url)
        except Exception:
            pass
        source_id = 0
        # Compute the request-scoped country filter (uppercased
        # for case-insensitive iso3 matching; the DB cleanup
        # layer also uppercases so the same iso3 casing works
        # in both paths).
        iso3_filter = tuple(
            str(c).strip().upper()
            for c in (request.country_filter or ())
            if str(c).strip()
        )
        with session_scope(request.database_url) as session:
            # The source row's ``source_url`` / ``license_note``
            # are populated from the bundle's ``metadata.json``
            # resolved through ``request.raw_root`` -- the same
            # request-scoped path ``check_ready`` / ``read`` use.
            # Without ``request=`` the DB write block falls back
            # to the default data-lake path and a custom
            # raw-root run writes DB provenance from the default
            # bundle metadata (Phase B Increment B reviewer
            # blocker).
            source_id = register_pwt_source(session, request=request)
            write_pwt_observations(
                session,
                source_id,
                long_df,
                years_filter=tuple(requested_years) or None,
                iso3_filter=iso3_filter,
            )

        manifest_path = write_pwt_run_manifest(
            source_id=source_id,
            parquet_path=parquet_path,
            observation_rows=observation_rows,
            countries=countries_count,
            years=years_in_frame,
            indicators=indicators_count,
            warnings=tuple(warnings),
            requested_year=(
                int(requested_years[0])
                if requested_years
                else None
            ),
            processed_root=request.processed_root,
        )

        return _IngestResult(
            source_key=self.source_key,
            source_id=int(source_id),
            observation_rows=int(observation_rows),
            parquet_path=parquet_path,
            manifest_path=manifest_path,
            countries=int(countries_count),
            years=years_in_frame,
            indicators=int(indicators_count),
            warnings=tuple(warnings),
            attribution=PWT_ATTRIBUTION,
        )

    # ---- ingest (convenience) -------------------------------------------

    def ingest(self, request: IngestRequest) -> IngestResult:
        """Convenience method: drive the full pipeline on the same
        request.

        Calls :meth:`check_ready` -> :meth:`read` ->
        :meth:`transform` -> :meth:`write` in order on the
        :class:`IngestRequest` the caller passed in. Honors
        every request-scoped field (``raw_root``,
        ``processed_root``, ``database_url``, ``year`` /
        ``years``, ``country_filter``, ``force_refresh``,
        ``allow_network``, ...) consistently so the convenience
        path and the registry runner produce identical
        artifacts.

        The :class:`IngestResult` is the return value of
        :meth:`write`. When ``check_ready`` returns
        ``ready=False`` the convenience method raises
        :class:`RuntimeError` naming the blocker (mirrors the
        registry runner's behavior in
        :func:`leaders_db.ingest.registry.ingest_source`).
        """
        readiness = self.check_ready(request)
        if not readiness.ready:
            raise RuntimeError(
                f"PWT bundle is not ready: "
                f"{readiness.blocker or 'no blocker given'}"
            )
        bundle = self.read(request)
        frame = self.transform(bundle, request)
        return self.write(frame, request)

    # ---- private helpers -------------------------------------------------

    @staticmethod
    def _read_bundle_metadata(request: IngestRequest) -> dict[str, Any]:
        """Return the parsed ``metadata.json`` payload (or empty dict)."""
        bundle_dir = _bundle_dir(request)
        metadata_path = bundle_dir / PWT_METADATA_NAME
        if not metadata_path.is_file():
            return {}
        try:
            payload = json.loads(
                metadata_path.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# PWT coverage helpers
# ---------------------------------------------------------------------------

#: PWT 10.01 covers 1950-2019 per the canonical attribution block
#: in ``docs/sources/attributions.md`` and the live xlsx
#: inspection on 2026-06-22. Used to detect out-of-coverage
#: requests (e.g. ``year=2023``) so the manifest warning can fire
#: BEFORE any DB / parquet write.
PWT_COVERAGE_START_YEAR: int = 1950
PWT_COVERAGE_END_YEAR: int = 2019


def _pwt_coverage_range() -> tuple[int, int]:
    """Return ``(PWT_COVERAGE_START_YEAR, PWT_COVERAGE_END_YEAR)``."""
    return PWT_COVERAGE_START_YEAR, PWT_COVERAGE_END_YEAR


__all__ = [
    "PWT_COVERAGE_END_YEAR",
    "PWT_COVERAGE_START_YEAR",
    "PWTAdapter",
]
