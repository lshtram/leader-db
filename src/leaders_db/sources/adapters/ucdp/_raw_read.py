"""Unified-source UCDP raw-read orchestration.

Owns the body of :meth:`UCDPAdapter.read_raw` extracted into a
free function :func:`read_ucdp_zip` so the adapter class
module stays focused on lifecycle wiring + registration. The
function lazy-imports the legacy reader
(:func:`leaders_db.ingest.ucdp_io.read_ucdp`) so the unified
package boundary is preserved; the local-file-only read path
emits a :class:`RawReadResult` carrying the wide-format
country-year DataFrame under ``payload["wide_df"]`` for the
transform layer plus the staged metadata bundle.

The UCDP unified path is local-file only (no network). The
``read_raw`` call passes ``year=None`` so the legacy reader
returns the full country-year wide frame; the transform layer
applies the request year / country filters on the wide frame
so the request-scoping semantics stay in one place.

The legacy reader returns the aggregated wide-format
DataFrame (one row per ``(country_id, year)`` with one column
per catalog ``variable_name``); the ``df.attrs`` carries
``events_total`` and ``events_filtered`` counts from the
pre-aggregation event-level frame. The transform layer
surfaces these on the per-observation extension
(``extension["ucdp_events_total"]`` /
``extension["ucdp_events_filtered"]``) so downstream audit
code can recover the input event-count metadata without
re-running the legacy read.

The UCDP zip carries the canonical CSV member
``GEDEvent_v23_1.csv`` (the real UCDP GED 23.1 release name).
The legacy reader also accepts a fixture path
(``tests/fixtures/ucdp/sample.zip``) with a different member
name (``GEDEvent_sample.csv``); the legacy read function
prefers the canonical name when present and falls back to the
first ``.csv`` member of the zip.

The UCDP unified path is local-file only (no network). The
zip is NEVER hashed by the unified adapter -- the readiness
gate optionally verifies the staged zip's SHA-256 against the
metadata ``checksum_sha256`` (canonical bundle metadata
carries ``null`` + ``pending`` status; the gate accepts
this shape when the staged zip is present). The raw asset's
``checksum_sha256`` field is intentionally left as ``None``
because the unified adapter does not know the canonical zip
SHA-256 from the metadata alone when the metadata is null.

The readiness gate (:func:`check_metadata_well_formed`)
returns ``ready=False`` with a structured ``MISSING_RAW``
error when ``ged231-csv.zip`` is not staged on disk. The
``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
``read_raw`` is invoked so the legacy reader never sees a
missing-zip scenario in production -- this ``read_raw``
function is only reached when the bundle is runner-ready.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._descriptor import (
    UCDP_DEFAULT_VERSION,
    UCDP_ZIP_ASSET_ID,
    UCDP_ZIP_NAME,
)


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/ucdp/`` bundle directory."""
    return Path(request.raw_root) / "ucdp"


def _zip_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``ged231-csv.zip`` path."""
    return _bundle_dir(request) / UCDP_ZIP_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / "metadata.json"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_ucdp_zip(request: SourceIngestRequest) -> RawReadResult:
    """Open the staged ``ged231-csv.zip`` and return the raw bundle.

    Lazy-imports the legacy reader so the unified package
    boundary is preserved. The wide-format DataFrame (one row
    per ``(country_id, year)`` with one column per catalog
    ``variable_name``, plus the two identity columns
    ``country_id`` and ``year``) is carried in
    :attr:`RawReadResult.payload` under ``"wide_df"`` for the
    transform layer. The ``read_raw`` call passes ``year=None``
    so the legacy reader returns the full frame; the transform
    layer applies the request year + country filters on the
    wide frame so the request-scoping semantics stay in one
    place.

    The UCDP unified path is local-file only (no network).
    The zip is NEVER hashed by the unified adapter -- the
    readiness gate optionally verifies the staged zip's
    SHA-256 against the metadata ``checksum_sha256`` (the
    canonical bundle ships ``null`` and the gate accepts
    this shape). The raw asset's ``checksum_sha256`` field
    is intentionally left as ``None`` so the raw asset does
    not lie about a checksum that is not actually recorded.

    The legacy ``read_ucdp`` reader also accepts a
    ``catalog_path`` kwarg and a ``year`` filter. The unified
    adapter passes ``year=None`` here so the legacy reader
    returns the full wide frame; the transform layer applies
    the request year + country filters. The ``catalog_path``
    kwarg is resolved through the transform layer (via
    :data:`DEFAULT_CATALOG_PATH` in :mod:`._catalog`) so the
    ``read_raw`` call here does not need to thread the
    catalog path through.

    When the staged zip is absent, the readiness gate
    (:func:`check_metadata_well_formed`) fires the
    structured ``MISSING_RAW`` error BEFORE ``read_raw``
    is invoked, and the ``SourceIngestRunner`` raises
    ``RuntimeError`` -- so this function is only reached
    when the bundle is runner-ready (the staged zip is
    present on disk). The fixture surface
    (``tests/fixtures/ucdp/sample.zip``) is staged via
    the test harness so the test runner always reaches
    ``read_raw`` with a staged zip.
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest`` (docs/architecture/sources.md
    # §10.1 + docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.ucdp_io import read_ucdp as _legacy_read_ucdp

    zip_path = _zip_path(request)
    # Pass ``year=None`` so the legacy reader returns the
    # full wide-format frame; the transform layer applies
    # the request year filter + the request country filter.
    # This keeps the legacy reader's behaviour intact while
    # giving the new transform full control over the
    # request-scoping decisions.
    wide_df = _legacy_read_ucdp(zip_path=zip_path)
    metadata = _read_metadata_payload(_metadata_path(request))

    # Carry the source URL metadata onto the RawAsset. The
    # staged bundle's ``source_url`` field is the canonical
    # UCDP data download URL; the descriptor's homepage_url
    # field is the UCDP downloads landing page. Prefer the
    # staged URL when present because the staged bundle
    # carries the canonical download URL.
    asset_url = None
    staged_url = metadata.get("source_url")
    if isinstance(staged_url, str) and staged_url.strip():
        asset_url = staged_url.strip()

    asset = RawAsset(
        asset_id=UCDP_ZIP_ASSET_ID,
        source_id=request.source_id,
        version=UCDP_DEFAULT_VERSION,
        media_type="application/zip",
        path=zip_path,
        url=asset_url,
        # The unified adapter does NOT hash the staged zip --
        # see the function docstring for the rationale.
        # The readiness gate optionally verifies the zip
        # SHA-256 against the metadata ``checksum_sha256``;
        # the raw asset's checksum field stays ``None`` so
        # downstream code does not assume a checksum that is
        # not actually recorded.
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
            "zip_path": zip_path,
        },
        warnings=(),
    )


__all__ = [
    "_bundle_dir",
    "_metadata_path",
    "_zip_path",
    "read_ucdp_zip",
]
