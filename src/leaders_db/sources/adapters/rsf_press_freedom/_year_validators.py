"""Per-year RSF CSV presence + per-file SHA-256
validators.

Split out of :mod:`._readiness` so the readiness
orchestrator stays focused on lifecycle ordering.
The helpers handle:

- :func:`_check_year_csv_presence` -- validate
  per-year CSV presence on disk for one year.
- :func:`_check_year_2011` -- block year=2011 with
  the documented ``rsf_year_2011_absent`` warning.
- :func:`_resolve_years_for_validation` -- resolve
  the canonical per-year set for the request scope
  (broad / no-year defaults to the 24-year staged
  set; year-scoped requests validate only the
  requested year(s); year=2011 is always reported as
  ``rsf_year_2011_absent``).
- :func:`_check_year_csvs` -- top-level orchestrator
  that loops over the per-year set, returns the
  first readiness blocker tuple (or ``(True, None,
  None)`` when all per-year CSVs are present and
  per-file SHA-256 matches). For each per-year CSV
  on disk, the gate ALSO requires a matching
  ``files`` metadata entry (enforced by
  :func:`._files_validators._check_year_files_entry`)
  before the optional per-file SHA-256 match.

The mandatory readiness requirement is on per-year
raw-file presence: a metadata-only bundle (no
staged per-year CSVs) is intentionally NOT
runner-ready; the gate returns ``ready=False`` with a
structured ``missing_raw`` error before the runner
dispatches ``read_raw`` / ``transform``. Year=2011
is always reported as ``rsf_year_2011_absent`` (NOT
``missing_raw``) so the operator can distinguish the
documented 2011 caveat from a generic
out-of-coverage year.
"""

from __future__ import annotations

from typing import Any

from leaders_db.sources.warnings import MISSING_RAW

from ._constants import (
    RSF_PRESS_FREEDOM_AVAILABLE_YEARS,
    RSF_PRESS_FREEDOM_COVERAGE_END_YEAR,
    RSF_PRESS_FREEDOM_COVERAGE_START_YEAR,
    RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR,
    RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE,
)
from ._files_validators import _check_year_files_entry
from ._metadata_validators import (
    _checksum_match_blocker,
)
from ._raw_read import _csv_name_for_year, _csv_path_for_year


def _resolve_years_for_validation(
    years_scope: tuple[int, ...] | None,
) -> tuple[int, ...]:
    """Resolve the canonical per-year set for the
    request scope.

    ``years_scope=None`` (broad / no-year request)
    defaults to :data:`RSF_PRESS_FREEDOM_AVAILABLE_YEARS`
    (the 24 staged per-year CSVs covering 2002-2010
    + 2012-2026). Explicit ``years_scope=(Y,)``
    validates only the requested year(s). Year=2011
    is silently filtered out -- the direct
    ``2011.csv`` is absent and the 2012 file
    represents the combined 2011/2012 edition (the
    readiness gate surfaces a structured
    ``rsf_year_2011_absent`` warning so the operator
    sees the gap).

    Out-of-coverage years (outside
    2002-2026) are also filtered out -- the
    per-year CSV-presence check does not fire for
    out-of-coverage years; the
    :func:`leaders_db.sources.adapters.rsf_press_freedom._readiness.collect_request_scoping_warnings`
    helper surfaces a structured ``YEAR_ABSENT``
    warning on the readiness envelope instead (per
    SRC-COV-002 / SRC-COV-003).
    """
    if years_scope is None:
        return RSF_PRESS_FREEDOM_AVAILABLE_YEARS
    return tuple(
        y for y in years_scope
        if y != RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR
        and RSF_PRESS_FREEDOM_COVERAGE_START_YEAR <= y
        <= RSF_PRESS_FREEDOM_COVERAGE_END_YEAR
    )


def _check_year_csv_presence(
    bundle_dir: Any,
    year: int,
) -> tuple[str, str] | None:
    """Return a blocker tuple if the per-year CSV for
    ``year`` is missing on disk.

    The mandatory readiness requirement is on per-year
    raw-file presence: the gate returns ``ready=False``
    with a structured ``missing_raw`` error whenever
    the per-year CSV is NOT staged on disk, regardless
    of the metadata's ``local_files`` / ``files``
    shape.
    """
    csv_name, year_int = _csv_name_for_year(year)
    csv_path = _csv_path_for_year(bundle_dir, year_int)
    if not csv_path.is_file():
        return (
            f"RSF readiness gate: {csv_name} missing "
            f"at {csv_path}; place the canonical "
            f"data/raw/rsf_press_freedom/{csv_name} "
            "before running Stage 2. The readiness "
            "gate requires the staged per-year CSV -- "
            "a metadata-only bundle is NOT "
            "runner-ready.",
            MISSING_RAW,
        )
    return None


def _check_year_2011(
    year: int,
) -> tuple[str, str] | None:
    """Return a blocker tuple for year=2011 (the
    documented missing year).

    The direct ``2011.csv`` is absent; RSF's combined
    2011/2012 edition is represented by the 2012 CSV
    (its ``Year (N)`` column reads ``"2011-12"``).
    Year=2011 requests fail readiness with a
    structured ``rsf_year_2011_absent`` warning so
    the operator can distinguish the documented 2011
    caveat from a generic out-of-coverage year.
    """
    if year != RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR:
        return None
    return (
        "RSF readiness gate: year=2011 is the "
        "documented missing year in the direct-CSV "
        "pattern. RSF publishes a combined "
        "2011/2012 edition represented by the "
        "2012 CSV (its `Year (N)` column reads "
        "`2011-12`); the direct `2011.csv` is "
        "intentionally absent. To ingest "
        "2011-related data, request the 2012 "
        "file (years=(2012,)); do NOT silently "
        "proxy 2011 -> 2012 (no stale-proxy fill "
        "per SRC-COV-002 / SRC-COV-003).",
        RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE,
    )


def _check_year_csvs(
    *,
    bundle_dir: Any,
    payload: dict[str, Any],
    years_scope: tuple[int, ...] | None,
) -> tuple[bool, str | None, str | None]:
    """Validate per-year CSV presence + per-file
    checksum for the request scope.

    For broad (``years_scope=None``) requests, the
    gate validates every year in the canonical
    :data:`RSF_PRESS_FREEDOM_AVAILABLE_YEARS` set.
    For year-scoped requests, the gate validates only
    the requested years. Year=2011 is always reported
    as ``rsf_year_2011_absent`` (NOT ``missing_raw``)
    so the operator can distinguish the documented
    2011 caveat from a generic out-of-coverage year.

    The 2011 check is applied BEFORE the per-year
    filter (year=2011 is checked in the raw
    ``years_scope`` argument, NOT in the
    per-year-filtered set) so the documented 2011
    caveat blocks the runner with a structured
    ``rsf_year_2011_absent`` error.
    """
    # First check 2011 against the raw ``years_scope``
    # (NOT the per-year-filtered set) so the documented
    # 2011 caveat blocks the runner for an explicit
    # year=2011 request.
    if years_scope is not None:
        for year in years_scope:
            year_2011_blocker = _check_year_2011(year)
            if year_2011_blocker is not None:
                return (
                    False,
                    year_2011_blocker[0],
                    year_2011_blocker[1],
                )

    years_to_check = _resolve_years_for_validation(years_scope)

    for year in years_to_check:
        presence_blocker = _check_year_csv_presence(bundle_dir, year)
        if presence_blocker is not None:
            return False, presence_blocker[0], presence_blocker[1]
        # Require a matching ``files`` metadata entry
        # whenever a per-year CSV is on disk. The
        # canonical RSF bundle uses ``files`` as the
        # per-file checksum + audit source of truth;
        # a staged per-year CSV without a matching
        # entry is malformed metadata and the gate
        # returns ``ready=False`` with a structured
        # ``missing_metadata`` blocker BEFORE the
        # runner dispatches ``read_raw`` /
        # ``transform``. The check fires AFTER the
        # per-year CSV presence check so a
        # metadata-only bundle is still reported as
        # ``missing_raw`` (NOT ``missing_metadata``).
        files_entry_blocker = _check_year_files_entry(
            payload, year,
        )
        if files_entry_blocker is not None:
            return (
                False,
                files_entry_blocker[0],
                files_entry_blocker[1],
            )
        csv_name, year_int = _csv_name_for_year(year)
        csv_path = _csv_path_for_year(bundle_dir, year_int)
        # Optional per-file SHA-256 match. A null /
        # absent per-file sha256 is treated as "no
        # checksum declared" and passes the gate (the
        # audit chain is preserved via the legacy
        # parquet metadata + the canonical attribution
        # text, Rule #15).
        checksum_blocker = _checksum_match_blocker(
            payload, csv_path, csv_name, year,
        )
        if checksum_blocker is not None:
            return False, checksum_blocker[0], checksum_blocker[1]

    return True, None, None


__all__ = [
    "_check_year_2011",
    "_check_year_csv_presence",
    "_check_year_csvs",
    "_resolve_years_for_validation",
]
