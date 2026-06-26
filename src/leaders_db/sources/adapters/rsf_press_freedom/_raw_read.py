"""Unified-source RSF raw-read orchestration.

Owns the body of :meth:`RSFPressFreedomAdapter.read_raw`
extracted into a free function
:func:`read_rsf_press_freedom_csv` so the adapter class
module stays focused on lifecycle wiring + registration.
The function lazy-imports the legacy reader
(:func:`leaders_db.ingest.rsf_press_freedom_csv.read_rsf_press_freedom_csv`)
so the unified package boundary is preserved; the
local-file-only read path emits a :class:`RawReadResult`
carrying the narrow observation frame under
``payload["narrow_df"]`` for the transform layer plus
the staged metadata bundle.

The RSF unified path is local-file only (no network).
The ``read_raw`` call loads the per-year CSV(s) through
the legacy reader, which returns a narrow-format
DataFrame (one row per
``(iso3, year, variable_name)`` triple with columns
``iso3``, ``year``, ``variable_name``, ``raw_value``,
``normalized_value``, ``source_row_reference``). The
transform layer consumes this frame and emits one
:class:`NormalizedObservation` per
``(iso3, year, variable_name)`` triple (the canonical
RSF catalog has 7 indicator rows: 2 base + 5
component-context, the latter 2022+ only).

The per-year CSV filename is derived from the request
scope: ``years=None`` defaults to a broad read of the
canonical 24-year CSV set (the staged bundle's
``local_files`` annotation); explicit ``years=(Y,)``
selects the per-year CSV
``rsf_press_freedom_<Y>.csv`` when staged. For
multi-year requests (``years=(Y1, Y2, ...)``), the
``read_raw`` call reads each year file in turn and
concatenates the per-year narrow frames into one
combined frame. The readiness gate
(:func:`check_metadata_well_formed` in
:mod:`._readiness`) ensures the per-year CSV(s) are
staged on disk before the runner dispatches
``read_raw``.

The RSF unified path is local-file only (no network).
The per-year CSV is NEVER hashed by the unified
adapter beyond the optional per-file SHA-256
verification at the readiness gate (the readiness
gate optionally verifies the staged CSV's SHA-256
against the metadata ``files`` array's
``sha256`` field). The raw asset's
``checksum_sha256`` field is intentionally left as
``None`` so the raw asset does not lie about a
checksum that is not actually recorded.

The readiness gate (:func:`check_metadata_well_formed`)
returns ``ready=False`` with a structured
``missing_raw`` error when the per-year CSV is not
staged on disk. The ``SourceIngestRunner`` raises
``RuntimeError`` BEFORE ``read_raw`` is invoked so
the legacy reader never sees a missing-CSV scenario
in production -- this ``read_raw`` function is only
reached when the bundle is runner-ready.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._constants import (
    RSF_PRESS_FREEDOM_AVAILABLE_YEARS,
    RSF_PRESS_FREEDOM_COVERAGE_END_YEAR,
    RSF_PRESS_FREEDOM_COVERAGE_START_YEAR,
    RSF_PRESS_FREEDOM_CSV_NAME_PATTERN,
    RSF_PRESS_FREEDOM_DEFAULT_VERSION,
    RSF_PRESS_FREEDOM_METADATA_NAME,
    RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR,
    RSF_PRESS_FREEDOM_SOURCE_KEY,
    _csv_asset_id_for_year,
)


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/rsf_press_freedom/``
    bundle directory.

    The canonical RSF bundle folder is
    ``rsf_press_freedom/`` (the slug is the folder
    name; no source-key / folder-alias reconciliation
    is needed, unlike ``pts`` /
    ``political_terror_scale``).
    """
    return Path(request.raw_root) / RSF_PRESS_FREEDOM_SOURCE_KEY


def _csv_name_for_year(year: int) -> tuple[str, int]:
    """Return the ``(csv_name, year)`` tuple for one
    per-year RSF CSV.

    The canonical per-year CSV filename is
    ``rsf_press_freedom_<year>.csv`` per the staged
    bundle's ``local_files`` annotation and the live
    RSF download URL pattern
    (``https://rsf.org/sites/default/files/import_classement/{year}.csv``).
    """
    year_int = int(year)
    return (
        RSF_PRESS_FREEDOM_CSV_NAME_PATTERN.format(year=year_int),
        year_int,
    )


def _csv_path_for_year(
    bundle_dir: Path, year: int,
) -> Path:
    """Return the resolved per-year CSV path."""
    csv_name, _ = _csv_name_for_year(year)
    return bundle_dir / csv_name


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json``
    path."""
    return _bundle_dir(request) / RSF_PRESS_FREEDOM_METADATA_NAME


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or
    ``{}`` on any error.

    The unified ``read_raw`` call uses this helper to
    load the staged bundle's ``source_url`` /
    ``canonical_page`` / ``license_note`` metadata
    fields so the raw asset can carry the canonical
    citation URL forward to the observation layer.
    """
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(
            metadata_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_years_for_request(
    request: SourceIngestRequest,
) -> tuple[int, ...]:
    """Return the resolved per-year scope for the
    request.

    ``years=None`` (broad / no-year request) defaults
    to the canonical staged set documented in
    ``RSF_PRESS_FREEDOM_AVAILABLE_YEARS`` (2002-2010
    + 2012-2026, the 24 staged per-year CSVs). Explicit
    ``years=(Y,)`` selects the per-year CSVs for the
    requested year(s). Year=2011 is silently filtered
    out -- the direct ``2011.csv`` is absent and the
    2012 file represents the combined 2011/2012
    edition (the readiness gate surfaces a structured
    ``rsf_year_2011_absent`` warning so the operator
    sees the gap). Out-of-coverage years (outside
    2002-2026) are also filtered out -- the per-year
    CSV-presence check does not fire for
    out-of-coverage years; the
    :func:`leaders_db.sources.adapters.rsf_press_freedom._readiness.collect_request_scoping_warnings`
    helper surfaces a structured ``YEAR_ABSENT``
    warning on the readiness envelope instead (per
    SRC-COV-002 / SRC-COV-003).
    """
    if request.years:
        years = tuple(int(y) for y in request.years)
    else:
        years = RSF_PRESS_FREEDOM_AVAILABLE_YEARS
    return tuple(
        y for y in years
        if y != RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR
        and RSF_PRESS_FREEDOM_COVERAGE_START_YEAR <= y
        <= RSF_PRESS_FREEDOM_COVERAGE_END_YEAR
    )


def read_rsf_press_freedom_csv(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Open the staged per-year RSF CSV(s) and return
    the raw bundle.

    Lazy-imports the legacy reader so the unified
    package boundary is preserved. The
    narrow-format DataFrame (one row per
    ``(iso3, year, variable_name)`` triple with the
    audit-trail columns ``raw_value`` /
    ``normalized_value`` / ``source_row_reference``)
    is carried in :attr:`RawReadResult.payload` under
    ``"narrow_df"`` for the transform layer. The
    ``read_raw`` call loads the per-year CSV(s) so
    the transform layer applies the request year /
    country filters on the narrow frame.

    The RSF unified path is local-file only (no
    network). The per-year CSV is NEVER hashed by the
    unified adapter beyond the readiness gate's
    optional per-file SHA-256 verification. The raw
    asset's ``checksum_sha256`` field is intentionally
    left as ``None`` so the raw asset does not lie
    about a checksum that the unified adapter does not
    actually record.

    The legacy
    :func:`leaders_db.ingest.rsf_press_freedom_csv.read_rsf_press_freedom_csv`
    reader applies the BOM-first / cp1252-fallback
    encoding detection, the semicolon-delimiter /
    comma-decimal-separator parsing, the pre/post-2022
    column-name variant resolution, the 2022 blank-
    row filter, and the long-to-narrow per-iso3 /
    per-indicator pivot. The narrow frame preserves
    the verbatim ``raw_value`` cell text (e.g.
    ``"72,67"``) alongside the period-decimal
    ``normalized_value`` float (``72.67``).

    When the staged per-year CSV is absent, the
    readiness gate (:func:`check_metadata_well_formed`)
    fires the structured ``missing_raw`` error BEFORE
    ``read_raw`` is invoked, and the
    ``SourceIngestRunner`` raises ``RuntimeError`` --
    so this function is only reached when the bundle
    is runner-ready (the per-year CSV(s) are present
    on disk).
    """
    # Lazy import: keeps ``leaders_db.sources``
    # importable without ``leaders_db.ingest``
    # (docs/architecture/sources.md §10.1 +
    # docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.rsf_press_freedom_csv import (
        read_rsf_press_freedom_csv as _legacy_read_rsf_csv,
    )

    bundle_dir = _bundle_dir(request)
    years_scope = _resolve_years_for_request(request)
    metadata = _read_metadata_payload(_metadata_path(request))

    # Carry the canonical RSF source URL metadata onto
    # the RawAsset. The staged bundle's ``source_url``
    # field is the canonical RSF CSV download URL
    # pattern; ``canonical_page`` is the canonical
    # user-facing citation landing page. Prefer the
    # staged ``canonical_page`` when present because
    # the staged bundle carries the canonical citation
    # landing page.
    asset_url: str | None = None
    staged_canonical_page = metadata.get("canonical_page")
    if (
        isinstance(staged_canonical_page, str)
        and staged_canonical_page.strip()
    ):
        asset_url = staged_canonical_page.strip()

    # Per-year narrow frames + per-year raw assets.
    # The unified transform consumes the combined
    # narrow frame; the per-year assets carry one
    # RawAsset each (the asset id embeds the year, so
    # audit code can group observations by per-year
    # asset). The combined frame is the
    # ``payload["narrow_df"]`` the transform layer
    # consumes.
    narrow_frames: list[pd.DataFrame] = []
    assets: list[RawAsset] = []
    csv_paths: list[Path] = []
    csv_names: list[str] = []
    for year in years_scope:
        csv_name, year_int = _csv_name_for_year(year)
        csv_path = _csv_path_for_year(bundle_dir, year_int)
        # The readiness gate has already validated
        # per-year CSV presence; the legacy reader
        # will raise FileNotFoundError if the per-year
        # file is missing at this point (defensive
        # guard for an out-of-band bundle mutation).
        narrow_frame = _legacy_read_rsf_csv(
            year=year_int,
            csv_path=csv_path,
        )
        narrow_frames.append(narrow_frame)
        csv_paths.append(csv_path)
        csv_names.append(csv_name)
        assets.append(
            RawAsset(
                asset_id=_csv_asset_id_for_year(year_int),
                source_id=request.source_id,
                version=RSF_PRESS_FREEDOM_DEFAULT_VERSION,
                media_type="text/csv",
                path=csv_path,
                url=asset_url,
                # The unified adapter does NOT hash the
                # staged per-year CSVs -- the readiness
                # gate optionally verifies the per-file
                # SHA-256 against the metadata ``files``
                # array's ``sha256`` field (the canonical
                # RSF bundle ships per-file SHA-256
                # values for all 24 CSVs). The raw
                # asset's checksum field stays ``None``
                # so downstream code does not assume a
                # checksum that the unified adapter does
                # not actually record.
                checksum_sha256=None,
                retrieved_at=None,
                immutable=True,
            ),
        )

    if narrow_frames:
        combined = pd.concat(
            narrow_frames, ignore_index=True, sort=False,
        )
        # Re-sort for deterministic output. The
        # per-year frames are already sorted; concat
        # preserves the order; the final sort makes the
        # cross-year row order stable.
        combined = combined.sort_values(
            by=["year", "iso3", "variable_name"],
            ascending=[True, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
    else:
        # Empty narrow frame; preserve the canonical
        # column shape so the transform layer can
        # detect "this run produced no data" without
        # re-reading the CSVs.
        combined = pd.DataFrame(
            columns=(
                "iso3",
                "year",
                "variable_name",
                "raw_value",
                "normalized_value",
                "source_row_reference",
            ),
        )

    return RawReadResult(
        source_id=request.source_id,
        assets=tuple(assets),
        payload={
            "narrow_df": combined,
            "metadata": metadata,
            "csv_paths": csv_paths,
            "csv_names": csv_names,
            "years_scope": years_scope,
        },
        warnings=(),
    )


__all__ = [
    "_bundle_dir",
    "_csv_name_for_year",
    "_csv_path_for_year",
    "_metadata_path",
    "_read_metadata_payload",
    "_resolve_years_for_request",
    "read_rsf_press_freedom_csv",
]
