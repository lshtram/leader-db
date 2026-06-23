"""Stage 2 — World Bank WDI DB writes: sources, source_observations, run manifest.

This module is the DB half of the WDI adapter. It owns:

- :func:`register_wdi_source` — upsert the ``sources`` row from the
  WDI bundle's ``metadata.json``.
- :func:`write_wdi_observations` — write one ``source_observations``
  row per ``(country, year, variable)`` triple. Idempotent (deletes
  existing rows for the requested years before inserting).
- :func:`write_wdi_run_manifest` — write the audit-trail JSON next to
  the narrow parquet.
- :func:`_coerce_float` — turn a JSON cell into ``float | None`` for
  the ``source_observations.normalized_value`` column. Handles
  ``None`` (WDI's null), pandas NaN, and numeric strings.

The cache read + parquet write functions live in
:mod:`leaders_db.ingest.wdi_io`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.wdi`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir, raw_dir
from .wdi_io import (
    _DEFAULT_CATALOG_PATH,
    WDI_ATTRIBUTION,
    WDI_SOURCE_KEY,
    IndicatorSpec,
    load_indicator_catalog,
)

#: String sentinels pandas / JSON may emit on re-reads. Treated as
#: missing. WDI uses ``null`` for missing cells (not a sentinel value
#: like V-Dem's ``-999``).
_WDI_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "null", "None", ""}
)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_wdi_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/world_bank_wdi/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(WDI_SOURCE_KEY) / "metadata.json"
    if not bundle_meta_path.is_file():
        return {}
    try:
        result: dict[str, object] = json.loads(
            bundle_meta_path.read_text(encoding="utf-8")
        )
        return result
    except json.JSONDecodeError:
        return {}


def _parse_download_date(raw: object) -> date | None:
    """Parse an ISO date from the bundle metadata; return ``None`` on failure."""
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_year_range(raw: object) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; return ``(None, None)`` on failure."""
    if not isinstance(raw, str) or "-" not in raw:
        return (None, None)
    start_str, end_str = raw.split("-", 1)
    try:
        return (int(start_str.strip()), int(end_str.strip()))
    except ValueError:
        return (None, None)


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_wdi_source(session: Session) -> int:
    """Upsert the WDI source row into the ``sources`` table.

    Keyed by ``(source_name='World Bank WDI', version='2024')``.
    Idempotent: returns the same ``sources.id`` on every call. Reads
    the bundle's ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source`). This means a future bundle
    with a new ``year_range`` will overwrite the existing row's
    coverage, but a missing ``download_date`` will not blank the field.
    """
    source_name = "World Bank WDI"
    version = "2024"

    bundle_meta = _read_wdi_bundle_metadata()
    download_date_value = _parse_download_date(bundle_meta.get("download_date"))
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("year_range")
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
            source_type="official",
            source_url=str(
                bundle_meta.get("source_url") or "https://data.worldbank.org/"
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or "CC BY 4.0 International per World Bank Terms of Use for Datasets"
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator catalog at "
                "src/leaders_db/ingest/catalogs/wdi.csv. See "
                "docs/sources/attributions.md for the exact citation text."
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
# Missing-value coercion
# ---------------------------------------------------------------------------


def _coerce_float(value: object) -> float | None:
    """Coerce a JSON / pandas cell to ``float`` or return ``None``.

    WDI's missing-data convention is ``null`` (the JSON literal).
    After JSON parsing, ``null`` becomes Python ``None``; after pandas
    reads the wide frame, missing cells become NaN. This helper
    handles both, plus the common string sentinels (``""``, ``"NA"``,
    ``"NaN"``, ``"nan"``, ``"null"``, ``"None"``).
    """
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    # Unknown type (list, dict, etc.) — be safe and return None.
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`."""
    stripped = raw.strip()
    if stripped in _WDI_MISSING_STRINGS:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit trail of what
      pandas saw).
    - All other values -> ``str(cell)`` (preserves the original
      numeric value as a string so the audit trail shows what the
      source file actually said).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


# ---------------------------------------------------------------------------
# Observations write
# ---------------------------------------------------------------------------


def write_wdi_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    ``country_id`` is intentionally left ``NULL`` — Stage 3 (country
    match) populates it after the WDI ``iso3`` is mapped to our
    canonical country key. ``source_row_reference`` carries the ISO3
    prefixed with ``"wdi:"`` (e.g. ``"wdi:MEX"``) so Stage 3 can
    resolve it.

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose ``year`` is
    present in ``df`` before inserting. Years outside the frame are
    untouched (so a single-year re-run does not erase older data).

    Returns the number of ``source_observations`` rows inserted.
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
    session: Session, source_id: int, years: list[int]
) -> None:
    """Delete existing ``source_observations`` rows for the given years.

    Years outside the list are not touched. Pulled out of
    :func:`write_wdi_observations` so the orchestrator stays short.
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
    source_id: int, df: pd.DataFrame, specs: list[IndicatorSpec]
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed)."""
    rows: list[SourceObservation] = []
    for _, raw_row in df.iterrows():
        iso3 = str(raw_row["iso3"])
        year = int(raw_row["year"])
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                # No data for this indicator for this row (e.g. the
                # wide frame is missing the column for an indicator
                # that had no values anywhere). Skip — no observation
                # to record.
                continue
            cell = raw_row[spec.variable_name]
            value = _coerce_float(cell)
            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year,
                    variable_name=spec.variable_name,
                    raw_value=_raw_value_to_string(cell),
                    normalized_value=value,
                    unit=spec.unit,
                    source_row_reference=f"wdi:{iso3}",
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better={1 if spec.higher_is_better else 0}"
                    ),
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_wdi_run_manifest(
    result,  # WDIIngestResult, imported lazily to avoid circular import
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, countries count, years, indicator count,
    indicators_cached / indicators_fetched, the catalog path used, and
    the attribution. Written every run (not best-effort) so Stage 15
    reports can find the attribution without re-reading the parquet
    metadata.

    Args:
        result: the :class:`WDIIngestResult` returned by :func:`ingest_wdi`.
        manifest_dir: override the output dir. Default: data-lake path.
        catalog_path: override the catalog path. Default: checked-in.
    """
    out_dir = manifest_dir or processed_dir(WDI_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "wdi_run_manifest.json"
    payload = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "indicators_cached": result.indicators_cached,
        "indicators_fetched": result.indicators_fetched,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": WDI_ATTRIBUTION,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_wdi_source",
    "write_wdi_observations",
    "write_wdi_run_manifest",
]
