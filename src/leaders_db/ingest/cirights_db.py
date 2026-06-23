"""Stage 2 -- CIRI Human Rights Data Project (CIRIGHTS) DB writes.

The DB half of the CIRIGHTS adapter. Owns:

- :func:`register_cirights_source` -- upsert the ``sources`` row
  from the CIRIGHTS bundle's ``metadata.json``.
- :func:`write_cirights_observations` -- write one
  ``source_observations`` row per ``(country, year, variable)``
  triple. Idempotent (deletes existing rows for the requested years
  before inserting).
- :func:`_delete_existing_observations` -- helper for
  :func:`write_cirights_observations`, separated for testability.
- :func:`write_cirights_run_manifest` -- write the audit-trail JSON
  next to the narrow parquet. Carries the ``proxy_year_semantics``
  field (when the caller asked for ``year=2023``) and the
  ``requested_year`` so the audit trail records the 1-year-gap
  proxy mapping explicitly.

The pure helpers (value coercion, the observation-row builder,
bundle-metadata parsing) live in
:mod:`leaders_db.ingest.cirights_db_helpers`. The xlsx read + parquet
write functions live in :mod:`leaders_db.ingest.cirights_io` and
:mod:`leaders_db.ingest.cirights_xlsx`. The orchestrator lives in
:mod:`leaders_db.ingest.cirights`.

The split into ``cirights_db`` + ``cirights_db_helpers`` mirrors
the WGI / WDI / PTS / UNDP HDI pattern (architecture §5: "no separate
``_helpers.py`` unless the module grows past 350 lines").
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir
from .cirights_db_helpers import (
    _build_observation_rows,
    _parse_download_date,
    _parse_year_range,
    _read_cirights_bundle_metadata,
)
from .cirights_io import (
    _DEFAULT_CATALOG_PATH,
    CIRIGHTS_ATTRIBUTION,
    CIRIGHTS_PROXY_REQUESTED_YEAR,
    CIRIGHTS_PROXY_YEAR,
    CIRIGHTS_SOURCE_KEY,
    load_indicator_catalog,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_cirights_source(session: Session) -> int:
    """Upsert the CIRIGHTS source row into the ``sources`` table.

    Keyed by
    ``(source_name='CIRI Human Rights Data Project',
    version='v3.12.10.24')``. Idempotent: returns the same
    ``sources.id`` on every call. Reads the bundle's
    ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_*_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source`, WGI's
    :func:`wgi_db.register_wgi_source`, UCDP's
    :func:`ucdp_db.register_ucdp_source`, SIPRI milex's
    :func:`sipri_milex_db.register_sipri_milex_source`, SIPRI
    Yearbook Ch.7's
    :func:`sipri_yearbook_ch7_db.register_sipri_yearbook_ch7_source`,
    PTS's :func:`pts_db.register_pts_source`, and UNDP HDI's
    :func:`undp_hdi_db.register_undp_hdi_source`).
    """
    source_name = "CIRI Human Rights Data Project"
    version = "v3.12.10.24"

    bundle_meta = _read_cirights_bundle_metadata()
    download_date_value = _parse_download_date(bundle_meta.get("download_date"))
    coverage_start, coverage_end = _parse_year_range(bundle_meta.get("year_range"))

    # The bundle stores coverage as separate ``coverage_start_year`` /
    # ``coverage_end_year`` integers (not a range string); the helper
    # supports both shapes. Fall back to the integer fields if the
    # range parse returned ``(None, None)``.
    if coverage_start is None:
        cs = bundle_meta.get("coverage_start_year")
        if isinstance(cs, int):
            coverage_start = cs
    if coverage_end is None:
        ce = bundle_meta.get("coverage_end_year")
        if isinstance(ce, int):
            coverage_end = ce

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
                or "https://www.cirights.org/"
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or (
                    "Free academic use with attribution; cite "
                    "Cingranelli, Richards, and Crepaz (2024). See "
                    "docs/sources/attributions.md for the exact "
                    "citation text."
                )
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C. Indicator "
                "catalog at "
                "src/leaders_db/ingest/catalogs/cirights.csv. See "
                "docs/sources/attributions.md for the exact citation "
                "text. Coverage ends 2022; 2023 requests are "
                "proxied to 2022 (1-year-gap, same pattern as UNDP "
                "HDI and Leader Survival)."
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


def write_cirights_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per
    ``(country, year, variable)``.

    Same shape as V-Dem / WGI / WDI / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 / PTS / UNDP HDI:

    - ``country_id`` is ``NULL``; Stage 3 (country match) fills it.
    - ``leader_id`` is ``NULL``.
    - ``source_row_reference`` is
      ``cirights:<country_token>:<year>:<raw_column>`` (e.g.
      ``cirights:Mexico:2022:Physical Integrity Rights Index``). The
      country display name is URL-safe-substituted
      (e.g. ``Cote d'Ivoire`` -> ``Cote_d_Ivoire``).
    - ``raw_value`` preserves the original cell text. For empty
      cells, the row is SKIPPED (per the design contract: do not
      invent values for missing cells).
    - ``normalized_value`` is the int 0-2 / 0-6 / 0-8 / 0-17 for
      valid cells, or ``None`` if the cell is missing.
    - Idempotent: deletes existing rows for the requested years
      (from the frame) before inserting. Years outside the frame
      are untouched.

    Returns the number of ``source_observations`` rows inserted.
    """
    if df.empty:
        return 0

    specs = load_indicator_catalog(catalog_path=catalog_path)
    years = sorted(
        {
            int(y) for y in pd.Series(df["year"]).dropna().astype(int).tolist()
            if int(y) != 0
        },
    )

    _delete_existing_observations(session, source_id, years)
    rows = _build_observation_rows(source_id, df, specs)
    session.add_all(rows)
    session.flush()
    return len(rows)


def _delete_existing_observations(
    session: Session, source_id: int, years: list[int],
) -> None:
    """Delete existing ``source_observations`` rows for the given years.

    Years outside the list are not touched. Pulled out of
    :func:`write_cirights_observations` so the orchestrator stays
    short. Same pattern as V-Dem / WGI / WDI / UCDP / SIPRI milex /
    SIPRI Yearbook Ch.7 / PTS / UNDP HDI.
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


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_cirights_run_manifest(
    result,  # CirightsIngestResult, imported lazily to avoid circular import
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    proxy_year_semantics: str | None = None,
    requested_year: int | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest is the audit trail for ``processed/``: it records
    ``source_id``, the parquet path, the observation row count, the
    countries count, the years, the indicator count, the
    ``year_window`` ``(start, end)`` tuple, the ``source_key``, the
    ``proxy_year_semantics`` (when the caller asked for
    ``year=2023`` and the adapter proxied to ``2022``), the
    ``requested_year`` (the literal year the caller asked for), the
    catalog path, and the attribution. Written every run (not
    best-effort) so Stage 15 reports can find the attribution
    without re-reading the parquet metadata.

    Args:
        result: the :class:`CirightsIngestResult` returned by
            :func:`ingest_cirights`.
        manifest_dir: override the output dir. Default: data-lake
            path (``data/processed/cirights/``).
        catalog_path: override the catalog path. Default: checked-in.
        proxy_year_semantics: when the caller asked for
            ``year=2023``, this records the ``2023 -> 2022`` mapping.
            Surfaced as ``payload["proxy_year_semantics"]`` so the
            audit trail records the proxy mapping explicitly.
        requested_year: the literal year the caller asked for (e.g.
            ``2023`` for the proxy). Surfaced as
            ``payload["requested_year"]``.
    """
    out_dir = manifest_dir or processed_dir(CIRIGHTS_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "cirights_run_manifest.json"
    payload: dict[str, object] = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "year_window": list(result.year_window),
        "source_key": CIRIGHTS_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": CIRIGHTS_ATTRIBUTION,
    }
    if proxy_year_semantics:
        payload["proxy_year_semantics"] = proxy_year_semantics
    if requested_year is not None:
        payload["requested_year"] = int(requested_year)
    # Surface the proxy-target-year constant so the manifest
    # always documents the 1-year-gap mapping even if the caller
    # did not explicitly pass ``year=2023``.
    payload["proxy_requested_year"] = int(CIRIGHTS_PROXY_REQUESTED_YEAR)
    payload["proxy_data_year"] = int(CIRIGHTS_PROXY_YEAR)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_cirights_source",
    "write_cirights_observations",
    "write_cirights_run_manifest",
]
