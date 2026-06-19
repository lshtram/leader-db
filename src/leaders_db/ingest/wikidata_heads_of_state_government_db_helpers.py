"""Stage 2 -- Wikidata heads-of-state-and-government DB helpers.

This module holds the pure helper functions used by
:mod:`wikidata_heads_of_state_government_db`. It is split out of
:mod:`wikidata_heads_of_state_government_db` so the DB module stays
focused on the DB-write contract (sources, source_observations, run
manifest) and the helper module stays focused on the
value-coercion and bundle-metadata parsing rules.

Owns:

- :func:`_read_wikidata_bundle_metadata` -- read
  ``data/raw/wikidata_heads_of_state_government/metadata.json`` if
  present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_build_observation_rows` -- in-memory builder for
  :class:`SourceObservation` rows from the long-format frame produced
  by the parser. Wikidata has no numeric ``normalized_value`` --
  every row has ``normalized_value=NULL`` because a Wikidata leader
  reference is a QID (string), not a number. The verbatim binding
  JSON is preserved in ``raw_value``.
- :func:`_make_source_row_reference` -- build the canonical
  ``source_row_reference`` string
  ``wikidata:<country_qid>:<office_qid>:<person_qid>:<statement_uri_hash>``
  so Stage 3 / Stage 4 can resolve the observation.

The DB-write functions
(:func:`wikidata_heads_of_state_government_db.register_wikidata_heads_of_state_government_source`,
:func:`wikidata_heads_of_state_government_db.write_wikidata_heads_of_state_government_observations`,
:func:`wikidata_heads_of_state_government_db.write_wikidata_heads_of_state_government_run_manifest`)
live in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_db`. The
catalog + paths + parquet write live in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_io`. The
HTTP + cache I/O lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_http`. The
parser lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government_parse`.
The orchestrator lives in
:mod:`leaders_db.ingest.wikidata_heads_of_state_government`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .wikidata_heads_of_state_government_io import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    IndicatorSpec,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_wikidata_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/wikidata_heads_of_state_government/metadata.json``
    if present, else empty dict.
    """
    bundle_meta_path = (
        raw_dir(WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY)
        / "metadata.json"
    )
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


# ---------------------------------------------------------------------------
# Source-row-reference builder
# ---------------------------------------------------------------------------


def _make_source_row_reference(
    *,
    country_qid: str,
    office_qid: str,
    person_qid: str,
    statement_uri: str,
) -> str:
    """Build the canonical ``source_row_reference`` string for one observation.

    Format:
    ``wikidata:<country_qid>:<office_qid>:<person_qid>:<statement_hash>``

    where ``<statement_hash>`` is a 10-character SHA-256 prefix of the
    statement URI so two observations that differ only in the
    auto-generated statement UUID do not collide. The full URI is
    still preserved in ``raw_value`` (the verbatim binding JSON).

    Empty ``country_qid`` / ``office_qid`` / ``person_qid`` values are
    replaced with ``"-"`` so the ``:`` separator count is stable for
    the audit-trail parsers downstream (Stage 3 / Stage 4 can split
    on ``:`` and read 5 parts).
    """
    parts = [
        "wikidata",
        country_qid or "-",
        office_qid or "-",
        person_qid or "-",
    ]
    if statement_uri:
        parts.append(
            hashlib.sha256(statement_uri.encode("utf-8")).hexdigest()[:10]
        )
    else:
        parts.append("-")
    return ":".join(parts)


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    df: pd.DataFrame,
    *,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed).

    Iterates the long-format frame (one row per SPARQL binding) and
    emits one ``SourceObservation`` per (binding, matching catalog
    spec) pair. The catalog's ``raw_column`` is the Wikidata office
    QID; a binding matches a spec when ``binding.office_qid ==
    spec.raw_column``.

    For each row:

    - ``source_id`` is left for the DB layer to set (the orchestrator
      passes it in after registering the source).
    - ``country_id`` and ``leader_id`` are intentionally ``NULL``.
      Stage 3 maps ``country_qid`` (a QID like ``Q30``) to our
      ``countries`` table; Stage 4 maps ``person_qid`` (a QID like
      ``Q6279``) to a canonical ``leaders`` row.
    - ``year`` is the calendar year of ``start_date`` (the year the
      holder took office). When ``start_date`` is absent the year is
      ``NULL`` (the binding did not have a start qualifier -- a data
      quality issue that Stage 11 should flag).
    - ``variable_name`` is the catalog spec's ``variable_name`` (the
      canonical Stage 2 / Stage 9 name, e.g.
      ``wikidata_head_of_state_held``).
    - ``raw_value`` is the verbatim binding JSON (preserved exactly
      as the API returned it).
    - ``normalized_value`` is always ``NULL``. Wikidata is a
      leader-reference source; the "value" is a QID, not a number.
      Numeric coercion would silently lose information, so the
      orchestrator emits ``NULL`` per the prototype convention
      (requirement §7: "preserve raw values, normalized values, and
      source provenance separately").
    - ``unit`` is the catalog spec's ``unit`` (``"qid"``).
    - ``source_row_reference`` carries the QID + statement hash so
      Stage 3 / Stage 4 can resolve the observation.
    - ``confidence`` is ``NULL`` (set by Stage 11).
    - ``notes`` carries the request audit trail: catalog rating
      category, request office_qid, requested year.
    """
    if df.empty:
        return []

    # Index specs by raw_column (office QID) for O(1) lookup.
    specs_by_office: dict[str, IndicatorSpec] = {
        spec.raw_column: spec for spec in specs
    }

    rows: list[SourceObservation] = []
    for _, raw_row in df.iterrows():
        office_qid = str(raw_row.get("office_qid") or "").strip()
        spec = specs_by_office.get(office_qid)
        if spec is None:
            # Binding for an office QID not in the catalog. The
            # SPARQL query is built from the catalog's office_qids,
            # so this branch is defensive only -- if the catalog
            # changes between query-construction and row-build, the
            # unknown binding is silently skipped (logged at
            # DEBUG).
            _logger.debug(
                "Skipping Wikidata binding for office_qid=%s "
                "absent from catalog",
                office_qid,
            )
            continue
        country_qid = str(raw_row.get("country_qid") or "").strip()
        person_qid = str(raw_row.get("person_qid") or "").strip()
        statement_uri = str(raw_row.get("statement_uri") or "").strip()
        start_date = raw_row.get("start_date")
        end_date = raw_row.get("end_date")
        year_value = raw_row.get("year")
        raw_value_text = str(raw_row.get("raw_value") or "")
        try:
            year_int = int(year_value) if year_value is not None else None
            if year_int is not None and (
                pd.isna(year_int) or year_int < 0
            ):
                year_int = None
        except (TypeError, ValueError):
            year_int = None

        rows.append(
            SourceObservation(
                source_id=0,  # set by the DB layer
                country_id=None,  # Stage 3 fills this in
                leader_id=None,  # Stage 4 fills this in
                year=year_int,
                variable_name=spec.variable_name,
                raw_value=raw_value_text,
                normalized_value=None,  # Wikidata has no numeric value
                unit=spec.unit,
                source_row_reference=_make_source_row_reference(
                    country_qid=country_qid,
                    office_qid=office_qid,
                    person_qid=person_qid,
                    statement_uri=statement_uri,
                ),
                confidence=None,  # set by Stage 11
                notes=(
                    f"raw_scale={spec.raw_scale}; "
                    f"higher_is_better="
                    f"{1 if spec.higher_is_better else 0}; "
                    f"country_label={raw_row.get('country_label')}; "
                    f"person_label={raw_row.get('person_label')}; "
                    f"office_label={raw_row.get('office_label')}; "
                    f"start_date={start_date}; "
                    f"end_date={end_date}; "
                    f"requested_year={raw_row.get('requested_year')}"
                ),
            )
        )
    return rows


__all__ = [
    "_build_observation_rows",
    "_make_source_row_reference",
    "_parse_download_date",
    "_read_wikidata_bundle_metadata",
]
