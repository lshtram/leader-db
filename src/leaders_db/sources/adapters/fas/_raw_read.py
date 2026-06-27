"""Raw HTML reader for the clean FAS Nuclear Notebook adapter.

Reads the staged local HTML cache
(``<raw_root>/fas/fas_status.html``) through the legacy parser via
lazy imports so the canonical Stage 2 parsing logic is reused
without duplication. The HTTP layer
(``leaders_db.ingest.fas_http.fetch_fas_status_html``) is
intentionally NEVER imported or invoked by the unified read path --
the readiness gate above enforces the supported cache policies and
the legacy bundle metadata already provides the cached HTML.

The wide-format DataFrame returned by
:func:`leaders_db.ingest.fas_html.read_fas_status_html` carries the
5 catalog indicator columns (``fas_operational_strategic``,
``fas_operational_nonstrategic``, ``fas_reserve_nondeployed``,
``fas_military_stockpile``, ``fas_total_inventory``) plus the
``_raw_value`` sibling columns that preserve the legacy parser's
post-``<sup>``-stripped FAS cell text (e.g. ``"1,600"`` for
Russia's operational strategic after the footnote marker is removed,
``"&lt;10"`` for North Korea's total inventory, etc.).
The sibling columns live in ``frame.attrs["_fas_raw_lookup"]`` so the
transform layer can attach the audit-trail ``raw_value`` per
``(country, year, indicator)`` triple without re-parsing the HTML.

The HTML parser also records the parsed snapshot year
(``frame.attrs["snapshot_year"]``) so the transform layer can stamp
every observation's ``year`` field with the parsed value rather than
relying on the staged ``metadata.json`` ``download_date``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import (
    FAS_DEFAULT_VERSION,
    FAS_HTML_ASSET_ID,
    FAS_HTML_NAME,
    FAS_SNAPSHOT_YEAR,
    FAS_SOURCE_KEY,
    FAS_STATUS_PAGE_URL,
)
from ._readiness import html_path, metadata_path, read_metadata


def read_fas_html(request: SourceIngestRequest) -> RawReadResult:
    """Read the staged FAS HTML cache through the legacy parser.

    Steps:

    1. Read the staged ``<raw_root>/fas/fas_status.html`` HTML.
    2. Parse the snapshot year + per-(country, indicator) wide
       DataFrame via the canonical legacy
       :func:`leaders_db.ingest.fas_html.read_fas_status_html`
       reader (lazy-imported so the unified adapter's package
       import does NOT pull in legacy ingest).
    3. Read the bundle metadata (the staged ``metadata.json``) to
       record the source URL + checksum on the :class:`RawAsset`.
    4. Carry the wide DataFrame + specs + raw-value lookup +
       snapshot year on the :class:`RawReadResult.payload` dict so
       the transform layer can pivot the wide frame to per-row
       :class:`NormalizedObservation` records.

    The imports from ``leaders_db.ingest`` are intentionally local
    so importing ``leaders_db.sources.adapters.fas`` does not pull
    in legacy ingest at module-import time (verified by the
    ``test_importing_fas_adapter_does_not_import_legacy_ingest``
    test in the unified test suite).
    """
    from leaders_db.ingest.fas_html import read_fas_status_html
    from leaders_db.ingest.fas_io import load_indicator_catalog

    path = html_path(request)
    html = path.read_text(encoding="utf-8", errors="replace")
    frame, parsed_snapshot_year = read_fas_status_html(html)
    specs = load_indicator_catalog()
    metadata = read_metadata(metadata_path(request))

    # Promote the wide frame's ``_raw_value`` sibling columns + the
    # parsed snapshot year onto a top-level attrs dict so the
    # transform layer can read the raw value per
    # ``(country, year, variable_name)`` triple. The legacy reader
    # uses ``_raw_value`` suffix columns per catalog variable
    # (``fas_operational_strategic_raw_value`` etc.).
    raw_lookup = _build_raw_value_lookup(frame, specs)

    checksum = _html_checksum(path, metadata)

    asset = RawAsset(
        asset_id=FAS_HTML_ASSET_ID,
        source_id=request.source_id,
        version=FAS_DEFAULT_VERSION,
        media_type="text/html",
        path=path,
        url=metadata.get("source_url") or FAS_STATUS_PAGE_URL,
        checksum_sha256=checksum,
        retrieved_at=None,
        immutable=True,
    )
    payload = {
        "frame": frame,
        "specs": specs,
        "metadata": metadata,
        "raw_value_lookup": raw_lookup,
        "snapshot_year": int(parsed_snapshot_year)
        if parsed_snapshot_year is not None
        else int(FAS_SNAPSHOT_YEAR),
        "status_page_url": FAS_STATUS_PAGE_URL,
    }
    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload=payload,
    )


def _build_raw_value_lookup(frame: object, specs: list[object]) -> dict[
    tuple[str, int, str], str
]:
    """Build a ``(country, snapshot_year, variable_name) -> raw_value`` lookup.

    Mirrors the SIPRI Yearbook Ch.7 / CIRIGHTS ``_raw_value_lookup``
    convention: the transform layer consults the lookup to attach
    the FAS legacy parser's audit cell text (e.g. ``"1,600"`` after
    stripping a ``<sup>`` footnote marker, ``"&lt;10"``, ``"n.a."``,
    ``"?"``) to each emitted :class:`NormalizedObservation`'s
    ``extension.raw_value`` audit field. The ``frame`` is the
    wide-format pandas DataFrame produced by the legacy reader; the
    ``_raw_value`` sibling columns live next to the indicator columns
    (e.g. ``fas_operational_strategic_raw_value``).
    """
    import pandas as pd

    lookup: dict[tuple[str, int, str], str] = {}
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return lookup
    snapshot_year = _frame_snapshot_year(frame)
    for spec in specs:
        raw_column_name = f"{spec.variable_name}_raw_value"
        if raw_column_name not in frame.columns:
            continue
        for row in frame.itertuples(index=False):
            country = getattr(row, "country", None)
            raw_value = getattr(row, raw_column_name, None)
            if country is None or raw_value is None:
                continue
            country_str = str(country).strip()
            raw_str = str(raw_value).strip() if not pd.isna(raw_value) else ""
            lookup[(country_str, snapshot_year, spec.variable_name)] = raw_str
    return lookup


def _frame_snapshot_year(frame: object) -> int:
    """Return the snapshot year parsed from the wide frame.

    Prefers ``frame.attrs["snapshot_year"]`` (the canonical
    placement the legacy reader uses); falls back to the
    ``year`` column's first value (the wide frame has one
    snapshot year across all rows); falls back to the documented
    default ``FAS_SNAPSHOT_YEAR`` constant.
    """
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        pd = None
    if frame is None:
        return int(FAS_SNAPSHOT_YEAR)
    attrs = getattr(frame, "attrs", None) or {}
    snapshot_year = attrs.get("snapshot_year")
    if isinstance(snapshot_year, int):
        return snapshot_year
    if isinstance(snapshot_year, str) and snapshot_year.strip().isdigit():
        return int(snapshot_year.strip())
    if pd is not None and isinstance(frame, pd.DataFrame) and "year" in frame.columns:
        years = frame["year"].dropna().unique().tolist()
        if years:
            return int(years[0])
    return int(FAS_SNAPSHOT_YEAR)


def _html_checksum(
    path: Path, metadata: dict[str, object]
) -> str | None:
    """Return the SHA-256 hex digest for the staged HTML cache.

    Prefers the bundle metadata's recorded ``checksum_sha256``
    (the staged ``data/raw/fas/metadata.json`` carries the
    canonical flat-string SHA-256). Falls back to the live
    re-hash of the file when the metadata field is absent (the
    audit trail is preserved either way). Returns ``None`` only
    when the file is unreadable.
    """
    metadata_checksum = metadata.get("checksum_sha256")
    if isinstance(metadata_checksum, str):
        cleaned = metadata_checksum.strip().lower()
        if len(cleaned) == 64 and all(
            c in "0123456789abcdef" for c in cleaned
        ):
            return cleaned
    if isinstance(metadata_checksum, dict):
        value = metadata_checksum.get(FAS_HTML_NAME)
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if len(cleaned) == 64 and all(
                c in "0123456789abcdef" for c in cleaned
            ):
                return cleaned
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest().lower()
    except OSError:
        return None


__all__ = ["read_fas_html"]


# Defensive: keep the canonical names referenced so static analyzers
# do not flag them as unused. The asset id constant is built from
# ``FAS_HTML_NAME`` + ``FAS_SOURCE_KEY`` so a future audit-trail
# expansion can use either component.
_ = (FAS_HTML_NAME, FAS_SOURCE_KEY)
