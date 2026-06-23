"""Stage 2 -- Maddison Project Database 2023 DB writes: sources, source_observations, run manifest.

This module is the DB half of the Maddison Project adapter. It owns:

- :func:`register_maddison_project_source` -- upsert the ``sources``
  row from the Maddison Project bundle's ``metadata.json``.
- :func:`write_maddison_project_observations` -- write one
  ``source_observations`` row per catalog indicator per country-
  year. Idempotent (deletes existing rows for the requested years
  before inserting).
- :func:`_delete_existing_observations` -- helper for
  :func:`write_maddison_project_observations`, separated for
  testability.
- :func:`_build_observation_rows` -- in-memory builder for
  ``SourceObservation`` rows from the narrow-format pandas frame.
- :func:`write_maddison_project_run_manifest` -- write the audit-
  trail JSON next to the narrow parquet.

The pure helpers (value coercion, bundle metadata parsing) live in
:mod:`maddison_project_db_helpers`. The xlsx read function lives in
:mod:`maddison_project_xlsx`. The catalog + path helpers + parquet
write live in :mod:`maddison_project_io`. The orchestrator that
ties everything together lives in :mod:`maddison_project`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source, SourceObservation
from ..paths import processed_dir
from .maddison_project_db_helpers import (
    _coerce_float,
    _parse_download_date,
    _parse_year_range,
    _raw_value_to_string,
    _read_maddison_project_bundle_metadata,
)
from .maddison_project_io import (
    _DEFAULT_CATALOG_PATH,
    MADDISON_PROJECT_ATTRIBUTION,
    MADDISON_PROJECT_SOURCE_KEY,
    load_indicator_catalog,
)

# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_maddison_project_source(session: Session) -> int:
    """Upsert the Maddison Project source row into the ``sources``
    table.

    Keyed by
    ``(source_name='Maddison Project Database 2023', version='2023')``.
    Idempotent: returns the same ``sources.id`` on every call.
    Reads the bundle's ``metadata.json`` for ``source_url``,
    ``download_date``, ``license_note``,
    ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as the V-Dem / WDI / WGI /
    UCDP / SIPRI / BTI / CIRIGHTS / UNDP HDI / WHO GHO API / PTS
    adapters).
    """
    source_name = "Maddison Project Database 2023"
    version = "2023"

    bundle_meta = _read_maddison_project_bundle_metadata()
    download_date_value = _parse_download_date(
        bundle_meta.get("download_date"),
    )
    coverage_start, coverage_end = _parse_year_range(
        bundle_meta.get("year_range"),
    )
    # Bundle stores ``coverage_start_year`` / ``coverage_end_year``
    # as separate integers; the helper supports both shapes via the
    # bundle metadata. Fall back to the integer fields if the
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
        ),
    ).scalar_one_or_none()

    if existing is None:
        row = Source(
            source_name=source_name,
            source_type="official",
            source_url=str(
                bundle_meta.get("source_url")
                or (
                    "https://www.rug.nl/ggdc/historicaldevelopment/"
                    "maddison/releases/maddison-project-database-2023"
                ),
            ),
            version=version,
            license_note=str(
                bundle_meta.get("license_note")
                or bundle_meta.get("license")
                or (
                    "CC BY 4.0 International; cite Bolt and van "
                    "Zanden 2024 per docs/sources/attributions.md."
                ),
            ),
            download_date=download_date_value,
            coverage_start_year=coverage_start,
            coverage_end_year=coverage_end,
            notes=(
                "Stage 2 adapter implemented in Phase C.11. "
                "Indicator catalog at "
                "src/leaders_db/ingest/catalogs/maddison_project.csv. "
                "See docs/sources/attributions.md for the exact "
                "citation text. Year 2023 requests are proxied to "
                "2022 data (1-year-gap, per CIRIGHTS / UNDP HDI / "
                "Leader Survival pattern). The GDP total indicator "
                "is DERIVED (gdppc * pop * 1000) and is labelled "
                "'derived 2011 international dollars'."
            ),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    # In-place refresh. See the docstring's update policy.
    if bundle_meta.get("source_url"):
        existing.source_url = str(bundle_meta["source_url"])
    if bundle_meta.get("license_note") or bundle_meta.get("license"):
        existing.license_note = str(
            bundle_meta.get("license_note")
            or bundle_meta.get("license"),
        )
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


def write_maddison_project_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per
    ``(countrycode, year, variable_name)`` triple.

    The ``df`` is the narrow-format frame returned by
    :func:`maddison_project_xlsx.read_maddison_project` (one row
    per ``(countrycode, year, variable_name)`` triple with the
    ``raw_value`` preserved). The function iterates the frame row-
    by-row and writes one :class:`SourceObservation` row per
    narrow-frame row. ``country_id`` is left ``NULL`` -- Stage 3
    (country match) populates it after the Maddison ``countrycode``
    is mapped to our canonical country key. ``source_row_reference``
    carries the ISO3 + raw_column prefixed with ``"maddison_project:"``
    (e.g. ``"maddison_project:gdppc:MEX:2022"``) so Stage 3 can
    resolve it. ``confidence`` is left ``NULL`` (Stage 11 fills
    it).

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``year`` is present in ``df`` before inserting. Years outside
    the frame are untouched (so a single-year re-run does not
    erase older data).

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
    session: Session, source_id: int, years: list[int],
) -> None:
    """Delete existing ``source_observations`` rows for the given
    years.

    Years outside the list are not touched. Pulled out of
    :func:`write_maddison_project_observations` so the orchestrator
    stays short.
    """
    existing_rows = session.execute(
        select(SourceObservation).where(
            SourceObservation.source_id == source_id,
            SourceObservation.year.in_(years),
        ),
    ).scalars().all()
    for row in existing_rows:
        session.delete(row)
    session.flush()


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[object],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB
    session needed).

    The ``df`` is the narrow-format frame returned by
    :func:`maddison_project_xlsx.read_maddison_project` (one row per
    ``(countrycode, year, variable_name)`` triple). The function
    iterates the frame row-by-row and writes one
    :class:`SourceObservation` row per narrow-frame row. The
    ``raw_value`` column preserves the verbatim cell text (so the
    audit trail records ``"nan"`` for missing cells, the literal
    numeric string for present cells, and the derived total's
    ``f"{value:.6f}"`` rendering for derived indicators).

    Iteration order: the orchestrator pre-sorts the frame by
    ``(year ASC, countrycode ASC, variable_name ASC)`` so the
    insertion order is fully deterministic. Tests that filter on a
    single ``variable_name`` and build ``{countrycode: row}`` from
    the result rely on the last-seen semantics of the dict
    comprehension being deterministic; the sort + the test's
    ``order_by`` guarantee that.
    """
    # Build a (countrycode, year, variable_name) -> spec lookup so
    # we can resolve the per-row spec without an inner-list scan.
    specs_by_variable: dict[str, object] = {
        s.variable_name: s for s in specs  # type: ignore[attr-defined]
    }
    rows: list[SourceObservation] = []
    for _, narrow_row in df.iterrows():
        iso3 = str(narrow_row["countrycode"])
        year = int(narrow_row["year"])
        variable_name = str(narrow_row["variable_name"])
        spec = specs_by_variable.get(variable_name)
        if spec is None:
            # Defensive: narrow-row variable not in the catalog. The
            # xlsx read only emits rows for catalog variables, but
            # we guard against future drift.
            continue
        raw_cell = narrow_row["raw_value"]
        normalized_cell = narrow_row["normalized_value"]
        value = _coerce_float(normalized_cell)
        rows.append(
            SourceObservation(
                source_id=source_id,
                country_id=None,  # Stage 3 fills this in
                leader_id=None,
                year=year,
                variable_name=variable_name,
                raw_value=_raw_value_to_string(raw_cell),
                normalized_value=value,
                unit=spec.unit,
                source_row_reference=(
                    f"maddison_project:{spec.raw_column}:{iso3}:{year}"
                ),
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


def write_maddison_project_run_manifest(
    result,  # MaddisonProjectIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
    proxy_year_semantics: str | None = None,
    requested_year: int | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, country count, years, indicator count,
    ``year_window`` (the ``(start, end)`` tuple of years the run
    covered), the ``source_key``, the ``proxy_year_semantics`` (when
    the requested year was the 2023 proxy), the ``requested_year``
    (when a year filter was applied), the catalog path, and the
    attribution. Written every run (not best-effort) so Stage 15
    reports can find the attribution without re-reading the parquet
    metadata.

    Args:
        result: the :class:`MaddisonProjectIngestResult` returned by
            :func:`ingest_maddison_project`.
        manifest_dir: override the output dir. Default: data-lake
            path (``data/processed/maddison_project/``).
        catalog_path: override the catalog path. Default: checked-in.
        proxy_year_semantics: when the caller asked for ``year=2023``,
            this records the ``2023 -> 2022`` mapping. Surfaced as
            ``payload["proxy_year_semantics"]`` so the audit trail
            records the proxy mapping explicitly.
        requested_year: the literal year the caller asked for (e.g.
            ``2023`` for the proxy). Surfaced as
            ``payload["requested_year"]``.
    """
    out_dir = manifest_dir or processed_dir(MADDISON_PROJECT_SOURCE_KEY)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        out_dir / "maddison_project_run_manifest.json"
    )
    payload: dict[str, object] = {
        "source_id": result.source_id,
        "parquet_path": str(result.parquet_path),
        "observation_rows": result.observation_rows,
        "countries": result.countries,
        "years": list(result.years),
        "indicators": result.indicators,
        "year_window": list(result.year_window),
        "source_key": MADDISON_PROJECT_SOURCE_KEY,
        "catalog_path": str(catalog_path or _DEFAULT_CATALOG_PATH),
        "attribution": MADDISON_PROJECT_ATTRIBUTION,
    }
    if proxy_year_semantics:
        payload["proxy_year_semantics"] = proxy_year_semantics
    if requested_year is not None:
        payload["requested_year"] = int(requested_year)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "register_maddison_project_source",
    "write_maddison_project_observations",
    "write_maddison_project_run_manifest",
]
