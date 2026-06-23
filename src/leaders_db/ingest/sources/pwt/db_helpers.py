"""Stage 2 -- PWT DB helpers: parquet write + source/observation persistence + run manifest.

This module owns the I/O + DB-write contract for the PWT adapter:

- :func:`write_pwt_parquet` -- persist the long-format frame as
  parquet with the PWT attribution attached to the schema
  metadata (Always-On Rule #15).
- :func:`register_pwt_source` -- upsert the ``sources`` row from
  the PWT bundle's ``metadata.json``.
- :func:`write_pwt_observations` -- write one ``source_observations``
  row per long-frame row. Idempotent: deletes existing rows for
  the request-scoped year(s) before inserting.
- :func:`_build_observation_rows` -- in-memory builder for the
  ``SourceObservation`` rows from the long-format DataFrame.
- :func:`write_pwt_run_manifest` -- write the audit-trail JSON
  next to the parquet, including the ``requested_year_out_of_coverage``
  warnings produced by :class:`PWTAdapter.write`.

The orchestrator that ties everything together lives in
:mod:`leaders_db.ingest.sources.pwt.adapter` (the ``PWTAdapter``
class itself). The reader + transform live in
:mod:`.reader` + :mod:`.transform`. The package-level
:func:`ingest_pwt` orchestrator lives in ``__init__.py`` and is the
single public entry point for both the registry runner and the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....db.models import Source, SourceObservation
from ....paths import processed_dir, raw_dir
from ...interfaces import IngestRequest
from .adapter import PWT_METADATA_NAME, PWT_SOURCE_KEY, PWT_XLSX_NAME

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

#: Narrow parquet name Stage 2 writes under
#: ``data/processed/pwt/``. Mirrors the Maddison / WGI / BTI naming
#: convention.
_PWT_PROCESSED_PARQUET_NAME: str = "pwt_country_year.parquet"

#: Run-manifest JSON name Stage 2 writes next to the parquet.
_PWT_RUN_MANIFEST_NAME: str = "pwt_run_manifest.json"

#: Parquet schema metadata key for the PWT attribution text
#: (Always-On Rule #15). pyarrow schema metadata keys are UTF-8
#: bytes.
_PWT_PARQUET_META_ATTRIBUTION: bytes = b"pwt_attribution"
_PWT_PARQUET_META_SOURCE_KEY: bytes = b"pwt_source_key"


def default_processed_parquet_path(
    processed_root: Path | None = None,
) -> Path:
    """Return the conventional PWT narrow parquet path.

    Creates the ``<root>/pwt/`` directory if missing.
    Honors ``processed_root`` overrides for the registry runner's
    request-scoped contract: when ``processed_root`` is set, the
    file lands at ``<processed_root>/pwt/pwt_country_year.parquet``
    (the same per-source layout as the data-lake default --
    ``<processed_root>`` is the parent of the ``<source>``
    subdirectory, NOT the parent of the file).
    """
    base = (
        Path(processed_root) if processed_root is not None
        else processed_dir()  # parent of the per-source folder
    )
    per_source = base / PWT_SOURCE_KEY
    per_source.mkdir(parents=True, exist_ok=True)
    return per_source / _PWT_PROCESSED_PARQUET_NAME


def _read_pwt_bundle_metadata(
    request: IngestRequest | None = None,
) -> dict[str, Any]:
    """Read the request-scoped bundle's ``metadata.json`` if present.

    Honors ``IngestRequest.raw_root`` so a custom raw-root run reads
    the metadata from the SAME bundle the readiness gate / reader
    validated. Falls back to ``data/raw/pwt/metadata.json`` only
    when ``request`` is ``None`` or ``request.raw_root`` is not
    set (per the Phase B Increment B reviewer feedback: the
    DB write block must use the request-scoped bundle metadata,
    NOT the default data-lake / fallback literals).
    """
    if request is not None and request.raw_root is not None:
        bundle_meta_path = (
            Path(request.raw_root) / PWT_SOURCE_KEY / PWT_METADATA_NAME
        )
    else:
        bundle_meta_path = raw_dir(PWT_SOURCE_KEY) / PWT_METADATA_NAME
    if not bundle_meta_path.is_file():
        return {}
    try:
        result: dict[str, Any] = json.loads(
            bundle_meta_path.read_text(encoding="utf-8"),
        )
        return result if isinstance(result, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_pwt_parquet(
    df: pd.DataFrame,
    *,
    processed_root: Path | None = None,
    parquet_path: Path | None = None,
) -> Path:
    """Persist the long-format frame as parquet with attribution
    metadata.

    Mirrors :func:`maddison_project_io.write_maddison_project_parquet`:
    writes the parquet via ``df.to_parquet``, then rewrites the
    file with the PWT attribution + source key attached as
    file-level schema metadata. The metadata rewrite is best-
    effort (logged + ignored on failure; the data parquet is
    still valid).
    """
    out = parquet_path or default_processed_parquet_path(processed_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_pwt_parquet_metadata(out)
    return out


def _attach_pwt_parquet_metadata(parquet_path: Path) -> None:
    """Attach the PWT attribution + source key to the parquet's
    schema metadata.

    Best-effort (logged on failure). The data parquet is still
    valid if the rewrite fails; the run manifest is the audit
    fallback.
    """
    import logging

    from . import PWT_ATTRIBUTION

    _logger = logging.getLogger(__name__)
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PWT_PARQUET_META_ATTRIBUTION] = PWT_ATTRIBUTION.encode("utf-8")
        meta[_PWT_PARQUET_META_SOURCE_KEY] = PWT_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        _logger.warning(
            "Failed to attach PWT attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the "
            "audit fallback.",
            parquet_path,
            exc,
        )


# ---------------------------------------------------------------------------
# Source registration
# ---------------------------------------------------------------------------


def register_pwt_source(
    session: Session,
    *,
    request: IngestRequest | None = None,
) -> int:
    """Upsert the PWT source row into the ``sources`` table.

    Keyed by ``(source_name='Penn World Table', version='10.01')``.
    Idempotent: returns the same ``sources.id`` on every call.
    Reads the bundle's ``metadata.json`` for ``source_url``,
    ``license_note``, and ``coverage`` when present.

    Honors ``request.raw_root`` when supplied (per Phase B
    Increment B reviewer feedback): the bundle metadata
    ``source_url`` / ``license_note`` are read from the SAME
    request-scoped bundle the readiness gate / reader use, NOT
    from the default data-lake path. Without ``request=`` the
    helper falls back to the default raw_dir path (kept for
    backward-compat with callers that do not have an
    ``IngestRequest`` in scope -- e.g. seeding fixtures).

    The non-destructive update policy mirrors the V-Dem / WDI /
    WGI / Maddison adapters: missing bundle fields keep the
    existing row's old value.
    """
    source_name = "Penn World Table"
    version = "10.01"

    bundle_meta = _read_pwt_bundle_metadata(request=request)
    bundle_source_url = bundle_meta.get("source_url")
    bundle_license = bundle_meta.get("license_note")

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
                bundle_source_url
                or (
                    "https://www.rug.nl/ggdc/productivity/pwt/"
                    "pwt-releases/pwt1001"
                ),
            ),
            version=version,
            license_note=str(
                bundle_license
                or (
                    "Creative Commons Attribution 4.0 International "
                    "(CC BY 4.0); cite Feenstra, Inklaar, Timmer "
                    "2015 per docs/source-attributions.md."
                ),
            ),
            coverage_start_year=1950,
            coverage_end_year=2019,
            notes=(
                "Stage 2 adapter implemented in Phase C.12 "
                "(Penn World Table 10.01). Indicator catalog at "
                "src/leaders_db/ingest/sources/pwt/catalog.csv. "
                "See docs/source-attributions.md for the exact "
                "citation text. PWT 10.01 covers 1950-2019; "
                "year=2023 requests produce zero observations + "
                "a requested_year_out_of_coverage manifest "
                "warning (no 2019 -> 2023 stale-proxy fill)."
            ),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    # In-place refresh.
    if bundle_source_url:
        existing.source_url = str(bundle_source_url)
    if bundle_license:
        existing.license_note = str(bundle_license)
    # PWT 10.01 coverage is fixed at 1950-2019; always keep it.
    existing.coverage_start_year = 1950
    existing.coverage_end_year = 2019
    return int(existing.id)


# ---------------------------------------------------------------------------
# Observations write
# ---------------------------------------------------------------------------


def write_pwt_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    years_filter: tuple[int, ...] | None = None,
    iso3_filter: tuple[str, ...] = (),
) -> int:
    """Write one ``source_observations`` row per long-frame row.

    The ``df`` is the long-format frame returned by
    :func:`leaders_db.ingest.sources.pwt.transform.transform_pwt_long_frame`
    (one row per ``(iso3, year, variable_name)`` triple with the
    ``raw_value`` + ``numeric_value`` preserved). The function
    iterates the frame row-by-row and writes one
    :class:`SourceObservation` row per long-frame row. ``country_id``
    is left ``NULL`` -- Stage 3 (country match) fills it in after
    the PWT ``countrycode`` is mapped to our canonical country key.
    ``source_row_reference`` carries the canonical locator
    ``pwt:Data:<iso3>:<year>:<raw_column>``.

    Idempotency: the function deletes every existing
    ``source_observations`` row for this ``source_id`` whose
    ``year`` is present in ``years_filter`` (or in the frame, if
    no ``years_filter`` was passed) BEFORE inserting. Years
    outside the filter are untouched. When ``iso3_filter`` is
    non-empty, the cleanup is ALSO scoped to those ISO3 codes
    (extracted from the canonical locator
    ``pwt:Data:<iso3>:<year>:<raw_column>``); rows whose iso3 is
    NOT in ``iso3_filter`` are left untouched, so a corrective
    ``country_filter=('USA',)`` re-run cannot accidentally
    delete MEX / SWE rows that the request did not scope.

    The cleanup runs even when ``df`` is empty -- an out-of-
    coverage request (e.g. ``year=2023`` against a 1950-2019
    PWT bundle) still cleans up any pre-existing stale
    observations for the requested year(s) so a previous bad
    proxy / stale-fill cannot survive a corrective re-run
    (per Phase B Increment B reviewer feedback).

    Returns the number of ``source_observations`` rows inserted.
    """
    # Compute the years-to-clean set BEFORE any branching so an
    # empty frame with an explicit ``years_filter`` still
    # triggers the per-year DELETE pass.
    if years_filter is not None:
        years = sorted({int(y) for y in years_filter})
    elif not df.empty and "year" in df.columns:
        years = sorted({int(y) for y in df["year"].tolist()})
    else:
        years = []

    # Normalize the iso3 filter so case-insensitive matching
    # works regardless of how the caller spelled the codes.
    iso3s_normalized: list[str] = sorted(
        {str(c).strip().upper() for c in iso3_filter if str(c).strip()},
    )

    # Always run the per-year (and optionally per-iso3) DELETE
    # pass (idempotency contract).
    _delete_existing_observations(session, source_id, years, iso3s_normalized)

    if df.empty:
        return 0

    rows = _build_observation_rows(source_id, df)
    session.add_all(rows)
    session.flush()
    return len(rows)


def _delete_existing_observations(
    session: Session,
    source_id: int,
    years: list[int],
    iso3s: list[str] | None = None,
) -> None:
    """Delete existing ``source_observations`` rows for the given
    years (and, optionally, the given ISO3 codes).

    When ``iso3s`` is non-empty, only rows whose canonical
    locator ``pwt:Data:<iso3>:<year>:<raw_column>`` carries an
    iso3 in the set are deleted. This scopes the cleanup to a
    request-scoped ``country_filter`` so the deletion does not
    silently remove rows for countries the caller did not
    include (per Phase B Increment B reviewer feedback).
    """
    if not years:
        return
    existing_rows = session.execute(
        select(SourceObservation).where(
            SourceObservation.source_id == source_id,
            SourceObservation.year.in_(years),
        ),
    ).scalars().all()
    iso3_set: set[str] | None = set(iso3s) if iso3s else None
    for row in existing_rows:
        if iso3_set is None:
            session.delete(row)
            continue
        ref = row.source_row_reference or ""
        parts = ref.split(":")
        # Canonical locator shape: ``pwt:Data:<iso3>:<year>:<raw_column>``.
        # The transform layer guarantees the 5-token shape; the
        # defensive guard skips rows with an unexpected shape so
        # they survive any out-of-band writes.
        if len(parts) >= 5 and parts[2] in iso3_set:
            session.delete(row)
    session.flush()


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB
    session needed).
    """
    rows: list[SourceObservation] = []
    for _, narrow_row in df.iterrows():
        year = int(narrow_row["year"])
        variable_name = str(narrow_row["variable_name"])
        raw_value_cell = narrow_row.get("raw_value")
        numeric_cell = narrow_row.get("numeric_value")
        raw_column = str(narrow_row["raw_column"])
        rows.append(
            SourceObservation(
                source_id=source_id,
                country_id=None,  # Stage 3 fills this in
                leader_id=None,
                year=year,
                variable_name=variable_name,
                raw_value=_raw_value_to_string(raw_value_cell),
                normalized_value=(
                    float(numeric_cell)
                    if numeric_cell is not None
                    and not (
                        isinstance(numeric_cell, float)
                        and pd.isna(numeric_cell)
                    )
                    else None
                ),
                unit=None,
                source_row_reference=str(
                    narrow_row["source_row_reference"],
                ),
                confidence=None,  # Stage 11 fills in
                notes=(
                    f"raw_column={raw_column}; "
                    f"temporal_kind={narrow_row['temporal_kind']}"
                ),
            ),
        )
    return rows


def _raw_value_to_string(cell: Any) -> str:
    """Render a raw cell for the ``source_observations.raw_value``
    audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` -> ``"nan"`` (preserves the audit trail of
      what pandas saw).
    - All other values -> ``str(cell)`` (preserves the numeric
      string the xlsx actually held).
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def write_pwt_run_manifest(
    *,
    source_id: int,
    parquet_path: Path,
    observation_rows: int,
    countries: int,
    years: tuple[int, ...],
    indicators: int,
    warnings: tuple[dict[str, Any], ...],
    requested_year: int | None = None,
    processed_root: Path | None = None,
    manifest_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the PWT parquet.

    The manifest records the run's ``source_id``, parquet path,
    observation row count, country count, years, indicator count,
    the PWT attribution (Rule #15), and the
    ``requested_year_out_of_coverage`` warnings when the request
    year is outside PWT 10.01's 1950-2019 coverage. Written every
    run (not best-effort) so Stage 15 reports can find the
    attribution + warnings without re-reading the parquet
    metadata.
    """
    from . import PWT_ATTRIBUTION

    base = (
        Path(processed_root) if processed_root is not None
        else processed_dir()  # parent of the per-source folder
    )
    per_source = base / PWT_SOURCE_KEY
    per_source.mkdir(parents=True, exist_ok=True)
    out_path = manifest_path or per_source / _PWT_RUN_MANIFEST_NAME
    payload: dict[str, Any] = {
        "source_id": int(source_id),
        "parquet_path": str(parquet_path),
        "observation_rows": int(observation_rows),
        "countries": int(countries),
        "years": list(years),
        "indicators": int(indicators),
        "source_key": PWT_SOURCE_KEY,
        "xlsx_name": PWT_XLSX_NAME,
        "warnings": [
            {k: v for k, v in w.items()}
            for w in warnings
        ],
        "attribution": PWT_ATTRIBUTION,
    }
    if requested_year is not None:
        payload["requested_year"] = int(requested_year)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


__all__ = [
    "default_processed_parquet_path",
    "register_pwt_source",
    "write_pwt_observations",
    "write_pwt_parquet",
    "write_pwt_run_manifest",
]
