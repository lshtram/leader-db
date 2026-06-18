"""Stage 2 -- SIPRI Yearbook Ch.7 DB writes: sources, observations, manifest.

The DB half of the SIPRI Yearbook Ch.7 adapter. Owns:

- :func:`register_sipri_yearbook_ch7_source` -- upsert the
  ``sources`` row.
- :func:`write_sipri_yearbook_ch7_observations` -- write one
  ``source_observations`` row per ``(country, year, variable)``.
  Idempotent.
- :func:`write_sipri_yearbook_ch7_run_manifest` -- audit-trail
  JSON next to the narrow parquet.

The pure coercion helpers live in
:mod:`leaders_db.ingest.sipri_yearbook_ch7_db_helpers`. The PDF
read + parquet write live in
:mod:`leaders_db.ingest.sipri_yearbook_ch7_io` and
:mod:`leaders_db.ingest.sipri_yearbook_ch7_pdf`. The
orchestrator lives in :mod:`leaders_db.ingest.sipri_yearbook_ch7`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir
from .sipri_yearbook_ch7_db_helpers import (
    _coerce_int,
    _parse_download_date,
    _parse_year_range,
    _read_sipri_yearbook_ch7_bundle_metadata,
)
from .sipri_yearbook_ch7_io import (
    _DEFAULT_CATALOG_PATH,
    SIPRI_YEARBOOK_CH7_ATTRIBUTION,
    SIPRI_YEARBOOK_CH7_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
)
from .sipri_yearbook_ch7_pdf import DOTS_SENTINEL, EN_DASH_SENTINEL

# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_sipri_yearbook_ch7_source(session: Session) -> int:
    """Upsert the SIPRI Yearbook Ch.7 source row into ``sources``.

    Keyed by
    ``(source_name='SIPRI Yearbook Chapter 7 (World Nuclear Forces)',
    version='YB2024 (data: January 2024)')``. Idempotent. Reads
    the bundle's ``metadata.json`` for ``source_url``,
    ``download_date``, ``license_note``, ``coverage_*_year``.
    Non-destructive update policy: missing bundle fields keep
    the existing row's old value (V-Dem / WGI / UCDP / SIPRI
    milex pattern).
    """
    source_name = "SIPRI Yearbook Chapter 7 (World Nuclear Forces)"
    version = "YB2024 (data: January 2024)"

    bundle_meta = _read_sipri_yearbook_ch7_bundle_metadata()
    download_date_value = _parse_download_date(
        bundle_meta.get("download_date"),
    )
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("year_range"),
    )

    existing = session.execute(
        select(Source).where(
            Source.source_name == source_name,
            Source.version == version,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = Source(
            source_name=source_name,
            source_type="academic",
            source_url=str(
                bundle_meta.get("source_url")
                or "https://www.sipri.org/yearbook/2024"
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Free academic with attribution; cite the SIPRI "
                    "Yearbook edition. See "
                    "https://www.sipri.org/yearbook/2024"
                )
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. See "
                "src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv "
                "and docs/source-attributions.md. First PDF-based "
                "source; the PDF parser uses pdfplumber and reads "
                "Table 7.1 on the first content page of the "
                "YB24 07 WNF.pdf."
            ),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    # In-place refresh. See the docstring's update policy.
    if bundle_meta.get("source_url"):
        existing.source_url = str(bundle_meta["source_url"])
    if bundle_meta.get("license_note"):
        existing.license_note = str(bundle_meta["license_note"])
    if download_date_value is not None:
        existing.download_date = download_date_value
    if coverage_start is not None:
        existing.coverage_start_year = coverage_start
    if coverage_end is not None:
        existing.coverage_end_year = coverage_end
    return int(existing.id)


# ---------------------------------------------------------------------------
# Observations write
# ---------------------------------------------------------------------------


def write_sipri_yearbook_ch7_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per
    ``(country, year, variable)``.

    Same shape as V-Dem / WGI / UCDP / SIPRI milex:
    ``country_id`` is ``NULL`` (Stage 3 fills it);
    ``source_row_reference`` is ``sipri_yearbook_ch7:<country>``;
    ``raw_value`` preserves the literal original PDF cell
    (``"-"``, ``".."``, ``"c. 24 j"``, or stringified int);
    ``normalized_value`` is ``0`` / ``None`` / parsed int.
    Idempotent: deletes existing rows for the requested years
    before inserting. Returns the number of rows inserted.
    """
    if df.empty:
        return 0

    specs = load_indicator_catalog(catalog_path=catalog_path)
    years = sorted({int(y) for y in df["year"].tolist()})

    _delete_existing_observations(session, source_id, years)
    rows = _build_observation_rows(source_id, df, specs)
    session.add_all(rows)
    session.flush()
    return len(rows)


def _delete_existing_observations(
    session: Session,
    source_id: int,
    years: list[int],
) -> None:
    """Delete existing ``source_observations`` rows for the given
    years. Years outside the list are not touched. Same
    pattern as V-Dem / WGI / UCDP / SIPRI milex.
    """
    existing_rows = session.execute(
        select(SourceObservation).where(
            SourceObservation.source_id == source_id,
            SourceObservation.year.in_(years),
        )
    ).scalars().all()
    for row in existing_rows:
        session.delete(row)
    session.flush()


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB
    session needed).

    Iterates the wide frame row-by-row; for each spec, writes one
    :class:`SourceObservation` row. ``raw_value`` is recovered
    from ``df.attrs["_sipri_yearbook_ch7_raw_lookup"]`` (the
    long-format raw-cell map built by the read orchestrator);
    this is the source of truth for the original PDF cell
    text (the literal ``"-"`` / ``".."`` / ``"c. 24 j"`` for
    missing/annotated cells; the stringified int for numeric
    cells). Iteration order: ``(year ASC, country ASC)`` via
    stable mergesort.
    """
    rows: list[SourceObservation] = []
    # Sort: stable mergesort breaks ties by country so insertion
    # order is fully deterministic.
    sorted_df = df.sort_values(
        by=["year", "country"],
        ascending=[True, True],
        kind="mergesort",
    )
    # (country, year, variable_name) -> raw cell text lookup
    # from the read orchestrator's raw_lookup. The lookup is
    # the source of truth for the original PDF cell text; the
    # wide-frame cells have been coerced to int (or pd.NA for
    # the two-dot sentinel), so we cannot recover the literal
    # ``"c. 24 j"`` from the wide frame.
    raw_lookup: dict[tuple[str, int, str], str] = (
        df.attrs.get("_sipri_yearbook_ch7_raw_lookup", {}) or {}
    )

    for _, raw_row in sorted_df.iterrows():
        country = str(raw_row["country"])
        year = int(raw_row["year"])
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                # No data for this indicator; skip.
                continue
            cell = raw_row[spec.variable_name]
            value = _coerce_int(cell)
            # The raw cell is recovered from the lookup. If the
            # lookup misses, fall back to the stringified cell
            # value (defense in depth).
            raw_cell = raw_lookup.get(
                (country, year, spec.variable_name),
            )
            raw_value_str = _build_raw_value_for_db(
                raw_cell, cell, value,
            )
            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year,
                    variable_name=spec.variable_name,
                    raw_value=raw_value_str,
                    normalized_value=value,
                    unit=spec.unit,
                    source_row_reference=(
                        f"sipri_yearbook_ch7:{country}"
                    ),
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better="
                        f"{1 if spec.higher_is_better else 0}"
                    ),
                )
            )
    return rows


def _build_raw_value_for_db(
    raw_cell: str | None,
    wide_cell: object,
    normalized_value: int | None,
) -> str:
    """Choose the ``raw_value`` string for the
    ``source_observations.raw_value`` audit column.

    The Stage 2 -> Stage 11 contract distinguishes three kinds
    of cells:

    1. **Missing-value / annotation sentinels** (``"-"`` /
       ``".."`` / ``"c. <num> [letter]"``): preserve the
       literal original PDF cell in ``raw_value`` (per
       :mod:`sipri_yearbook_ch7_pdf`).
    2. **Plain numeric cells** (e.g., ``"1 770 d"`` -> int
       ``1770``): the ``raw_value`` is the stringified
       ``normalized_value`` (e.g., ``"1770"``). The PDF
       thousands-separator and footnote-letter suffixes are
       normalized away.
    3. **Missing cells** (``pd.NA`` / ``None`` ->
       ``normalized_value = None``): the ``raw_value`` is
       ``""``.

    This is the design contract from
    ``docs/architecture/sipri_yearbook_ch7.md`` §3.3, which says
    the audit trail "preserves the literal original cell for
    sentinels and the stringified int for numeric cells".

    Args:
        raw_cell: the literal original PDF cell text from
            ``df.attrs["_sipri_yearbook_ch7_raw_lookup"]``, or
            ``None`` if the lookup missed.
        wide_cell: the wide-frame cell (post-pivot). Used as
            the fallback when the lookup misses.
        normalized_value: the int | None coerced from
            ``wide_cell``.

    Returns:
        The ``raw_value`` string for the
        ``source_observations.raw_value`` column.
    """
    if normalized_value is None:
        # Two-dot sentinel or otherwise missing: the audit
        # trail preserves the literal original cell (if it
        # is "..") or empty string (if the lookup missed).
        if raw_cell == DOTS_SENTINEL:
            return DOTS_SENTINEL
        return ""
    # The cell has a normalized value. Decide between the
    # en-dash sentinel and a plain numeric cell.
    if raw_cell == EN_DASH_SENTINEL:
        # The en-dash sentinel: normalized_value=0, raw_value="-".
        return EN_DASH_SENTINEL
    # c.-prefix annotation: preserve the literal (e.g.,
    # "c. 24 j" -> normalized_value=24, raw_value="c. 24 j").
    if raw_cell is not None and (
        raw_cell.lstrip().lower().startswith("c.")
    ):
        return raw_cell
    # Plain numeric cell (e.g., "1 770 d" -> 1770): the
    # raw_value is the stringified int without thousands
    # separators or footnote-letter suffixes.
    return str(normalized_value)


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_sipri_yearbook_ch7_run_manifest(
    result,  # SipriYearbookCh7IngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest is the audit trail for ``processed/``: it
    records ``source_id``, the parquet path, the observation row
    count, the countries count, the years, the indicator count,
    the ``pdf_pages_total``, the ``snapshot_year``, the catalog
    path, and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution
    without re-reading the parquet metadata.
    """
    out_dir = manifest_dir or processed_dir(SIPRI_YEARBOOK_CH7_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        out_dir / "sipri_yearbook_ch7_run_manifest.json"
    )
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "pdf_pages_total": result.pdf_pages_total,
        "snapshot_year": result.snapshot_year,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": SIPRI_YEARBOOK_CH7_ATTRIBUTION,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_sipri_yearbook_ch7_source",
    "write_sipri_yearbook_ch7_observations",
    "write_sipri_yearbook_ch7_run_manifest",
]
