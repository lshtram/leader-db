"""Unified-source Transparency International CPI
raw-read orchestration.

Owns the body of
:meth:`TransparencyCPIAdapter.read_raw` extracted into a
free function :func:`read_transparency_cpi_csv` so the
adapter class module stays focused on lifecycle wiring +
registration. The function lazy-imports the legacy
reader (:func:`leaders_db.ingest.transparency_cpi_csv.read_transparency_cpi_csv`)
so the unified package boundary is preserved; the
local-file-only read path emits a :class:`RawReadResult`
carrying the wide-format country-year DataFrame under
``payload["wide_df"]`` for the transform layer plus the
staged metadata bundle.

The Transparency International CPI unified path is
local-file only (no network). The ``read_raw`` call
loads the per-year CSV through the legacy reader, which
returns a wide-format DataFrame (one row per ``(iso3,
year)`` with columns ``country``, ``region``,
``cpi_score``, ``cpi_score_raw_value``, ``rank``,
``sources``, ``standard_error``, ``lower_ci``,
``upper_ci``). The transform layer consumes this frame
and emits one :class:`NormalizedObservation` per
``(iso3, year)`` triple (the canonical CPI catalog has 1
indicator row).

The per-year CSV filename is derived from the request
scope: ``years=None`` defaults to the canonical 2023 CSV
(``transparency_cpi_2023.csv``), matching the staged
bundle; explicit ``years=(Y,)`` selects the per-year
CSV ``transparency_cpi_<Y>.csv`` when staged.

The CPI unified path is local-file only (no network). The
CSV is NEVER hashed by the unified adapter beyond the
optional metadata-checksum verification at the readiness
gate -- the readiness gate optionally verifies the
staged CSV's SHA-256 against the metadata
``checksum_sha256`` (the canonical CPI bundle ships
``null`` and the gate accepts this shape). The raw
asset's ``checksum_sha256`` field is intentionally left
as ``None`` so the raw asset does not lie about a
checksum that is not actually recorded.

The readiness gate (:func:`check_metadata_well_formed`)
returns ``ready=False`` with a structured ``MISSING_RAW``
error when the per-year CSV is not staged on disk. The
``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
``read_raw`` is invoked so the legacy reader never sees
a missing-CSV scenario in production -- this
``read_raw`` function is only reached when the bundle is
runner-ready.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._descriptor import (
    TRANSPARENCY_CPI_CSV_NAME_TEMPLATE,
    TRANSPARENCY_CPI_DEFAULT_CSV_NAME,
    TRANSPARENCY_CPI_DEFAULT_VERSION,
    _csv_asset_id_for_year,
)


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/transparency_cpi/``
    bundle directory."""
    return Path(request.raw_root) / "transparency_cpi"


def _csv_name_for_request(
    request: SourceIngestRequest,
) -> tuple[str, int]:
    """Return the ``(csv_name, year)`` tuple for the
    request scope.

    The CPI canonical bundle ships one CSV at
    ``data/raw/transparency_cpi/transparency_cpi_2023.csv``
    (the canonical per-year HDX-mirrored verbatim TI
    release). The unified adapter always reads the
    canonical CSV -- the request's ``years=`` filter is
    applied on the wide frame after the legacy read so
    out-of-coverage year requests still pass readiness
    and the transform emits zero observations plus a
    structured ``YEAR_ABSENT`` warning per offending
    year. This matches the V-Dem / WGI / WDI pattern
    (single canonical CSV per bundle; request year /
    country filters applied on the wide frame).
    """
    # Always read the canonical 2023 CSV (the staged
    # bundle's only CSV; see
    # ``data/raw/transparency_cpi/metadata.json``'s
    # ``local_files`` annotation).
    year_int = 2023
    return (
        TRANSPARENCY_CPI_CSV_NAME_TEMPLATE.format(year=year_int),
        year_int,
    )


def _csv_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped per-year CSV path.

    The CPI unified adapter always reads the canonical
    2023 CSV (the staged bundle's only CSV). The
    request's ``years=`` filter is honored by the
    transform layer (which narrows the wide frame after
    the legacy read).
    """
    csv_name, _ = _csv_name_for_request(request)
    return _bundle_dir(request) / csv_name


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / "metadata.json"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or
    ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(
            metadata_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_records(csv_path: Path) -> list[dict[str, str]]:
    """Read the per-year CPI CSV into a list of dicts.

    The unified adapter reads the per-year CSV with the
    Python standard library ``csv.DictReader`` rather
    than through ``pandas.read_csv`` so the helper
    preserves the exact HDX CSV column shape (string
    values, including the verbatim missing sentinels like
    empty cells) without coercing empty strings to NaN.
    The legacy reader
    (:func:`leaders_db.ingest.transparency_cpi_csv.read_transparency_cpi_csv`)
    accepts the records list and applies the canonical
    wide-format coercion.
    """
    records: list[dict[str, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as src:
        reader = csv.DictReader(src)
        for row in reader:
            records.append(dict(row))
    return records


def read_transparency_cpi_csv(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Open the staged per-year
    ``transparency_cpi_<year>.csv`` and return the raw
    bundle.

    Lazy-imports the legacy reader so the unified package
    boundary is preserved. The wide-format DataFrame (one
    row per ``(iso3, year)`` with one column per catalog
    ``variable_name``, plus the audit-trail columns
    ``country``, ``region``, ``rank``, ``sources``,
    ``standard_error``, ``lower_ci``, ``upper_ci``) is
    carried in :attr:`RawReadResult.payload` under
    ``"wide_df"`` for the transform layer. The
    ``read_raw`` call loads the full per-year CSV so the
    transform layer applies the request year + country
    filters on the wide frame.

    The CPI unified path is local-file only (no network).
    The CSV is NEVER hashed by the unified adapter beyond
    the readiness gate's optional metadata-checksum
    verification. The raw asset's ``checksum_sha256``
    field is intentionally left as ``None`` so the raw
    asset does not lie about a checksum that is not
    actually recorded.

    The legacy ``read_transparency_cpi_csv`` reader also
    accepts a ``catalog_path`` kwarg. The unified adapter
    passes the catalog path resolved from the canonical
    checked-in location (``DEFAULT_CATALOG_PATH`` in
    :mod:`._catalog`) via the transform layer's catalog
    loader, so the ``read_raw`` call here does not need
    to thread the catalog path through.

    When the staged per-year CSV is absent, the readiness
    gate (:func:`check_metadata_well_formed`) fires the
    structured ``MISSING_RAW`` error BEFORE ``read_raw``
    is invoked, and the ``SourceIngestRunner`` raises
    ``RuntimeError`` -- so this function is only reached
    when the bundle is runner-ready (the staged CSV is
    present on disk).
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest``
    # (docs/architecture/sources.md §10.1 +
    # docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.transparency_cpi_csv import (
        read_transparency_cpi_csv as _legacy_read_cpi_csv,
    )

    csv_name, year = _csv_name_for_request(request)
    csv_path = _csv_path(request)
    records = _read_csv_records(csv_path)
    wide_df = _legacy_read_cpi_csv(
        records,
        year=year,
        cache_path=csv_path,
    )
    metadata = _read_metadata_payload(_metadata_path(request))

    # Carry the canonical Transparency International CPI
    # source URL metadata onto the RawAsset. The staged
    # bundle's ``source_url`` field is the canonical TI
    # publisher URL; ``hdx_mirror_url`` carries the HDX
    # mirror URL (the durable CSV provenance path).
    # Prefer the staged TI publisher URL when present
    # because the staged bundle carries the canonical
    # citation landing page.
    asset_url = None
    staged_url = metadata.get("source_url")
    if isinstance(staged_url, str) and staged_url.strip():
        asset_url = staged_url.strip()

    asset = RawAsset(
        asset_id=_csv_asset_id_for_year(year),
        source_id=request.source_id,
        version=TRANSPARENCY_CPI_DEFAULT_VERSION,
        media_type="text/csv",
        path=csv_path,
        url=asset_url,
        # The unified adapter does NOT hash the staged
        # CSV -- the readiness gate optionally verifies
        # the CSV SHA-256 against the metadata
        # ``checksum_sha256`` (the canonical CPI bundle
        # ships ``null`` and the gate accepts this shape).
        # The raw asset's checksum field stays ``None``
        # so downstream code does not assume a checksum
        # that is not actually recorded.
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )
    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={
            "wide_df": wide_df,
            "metadata": metadata,
            "csv_path": csv_path,
            "year": year,
            "csv_name": csv_name,
        },
        warnings=(),
    )


__all__ = [
    "TRANSPARENCY_CPI_DEFAULT_CSV_NAME",
    "_bundle_dir",
    "_csv_name_for_request",
    "_csv_path",
    "_metadata_path",
    "_read_csv_records",
    "_read_metadata_payload",
    "read_transparency_cpi_csv",
]
