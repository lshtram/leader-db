"""Stage 2 -- Wikipedia search-extract DB helpers.

This module holds the pure helper functions used by
:mod:`wikipedia_search_extract_db`. It is split out of
:mod:`wikipedia_search_extract_db` so the DB module stays focused on
the DB-write contract (sources, source_observations, run manifest)
and the helper module stays focused on the
observation-row construction and source-row-reference rules.

Owns:

- :func:`_read_wikipedia_bundle_metadata` -- read
  ``data/raw/wikipedia_search_extract/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_make_source_row_reference` -- build the canonical
  ``source_row_reference`` string for one observation. The
  orchestrator's hint ``source_row_reference_hint`` is augmented
  with the catalog spec's ``variable_name`` so Stage 3 / Stage 4 can
  resolve the observation unambiguously.
- :func:`_build_observation_rows` -- in-memory builder for
  :class:`SourceObservation` rows from the long-format frame
  produced by the parser. Wikipedia has no numeric
  ``normalized_value`` -- every row has ``normalized_value=NULL``
  because a Wikipedia extract / snippet is text, not a number. The
  verbatim per-row payload is preserved in ``raw_value``.

The DB-write functions
(:func:`wikipedia_search_extract_db.register_wikipedia_search_extract_source`,
:func:`wikipedia_search_extract_db.write_wikipedia_search_extract_observations`,
:func:`wikipedia_search_extract_db.write_wikipedia_search_extract_run_manifest`)
live in
:mod:`leaders_db.ingest.wikipedia_search_extract_db`. The HTTP +
cache I/O lives in
:mod:`leaders_db.ingest.wikipedia_search_extract_http`. The catalog +
paths + parquet write live in
:mod:`leaders_db.ingest.wikipedia_search_extract_io`. The parser lives
in :mod:`leaders_db.ingest.wikipedia_search_extract_parse`. The
orchestrator lives in
:mod:`leaders_db.ingest.wikipedia_search_extract`.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .wikipedia_search_extract_io import (
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    IndicatorSpec,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_wikipedia_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/wikipedia_search_extract/metadata.json`` if
    present, else empty dict.
    """
    bundle_meta_path = (
        raw_dir(WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY) / "metadata.json"
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
    hint: str,
    variable_name: str,
) -> str:
    """Build the canonical ``source_row_reference`` string for one observation.

    Format:
    ``wikipedia:<variable_name>:<hint>``

    where ``<hint>`` is the parser-emitted per-row hint
    (``wikipedia:<pageid>:<title>`` for ``extracts`` or
    ``wikipedia:search:<pageid>:<title>`` for ``search``). The
    ``variable_name`` prefix lets Stage 3 / Stage 4 distinguish
    extracts observations from search observations without parsing
    the hint further.
    """
    return f"wikipedia:{variable_name}:{hint}"


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    df: pd.DataFrame,
    *,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed).

    Iterates the long-format frame (one row per Action API response
    page / search hit) and emits one ``SourceObservation`` per
    (row, matching catalog spec) pair. The catalog's ``raw_column``
    is the API action name (``"extracts"`` or ``"search"``); a row
    matches a spec when ``row.action == spec.raw_column``.

    For each row:

    - ``source_id`` is left for the DB layer to set (the orchestrator
      passes it in after registering the source).
    - ``country_id`` and ``leader_id`` are intentionally ``NULL``.
      Wikipedia is a narrative-context helper; the pageid + title are
      preserved in ``source_row_reference`` and ``raw_value`` for
      downstream resolution.
    - ``year`` is ``NULL`` -- the Action API does not return a
      ``year`` for ``extracts`` or ``search`` responses. Stage 4
      may resolve the year from the page metadata if needed.
    - ``variable_name`` is the catalog spec's ``variable_name`` (the
      canonical Stage 2 / Stage 9 name, e.g.
      ``wikipedia_extract_lead``).
    - ``raw_value`` is the verbatim per-row payload JSON (preserved
      exactly as the API returned it).
    - ``normalized_value`` is always ``NULL``. Wikipedia is a
      narrative-context source; the "value" is text (extract or
      snippet), not a number. Numeric coercion would silently lose
      information, so the orchestrator emits ``NULL`` per the
      prototype convention (requirement §7).
    - ``unit`` is the catalog spec's ``unit`` (``"text"``).
    - ``source_row_reference`` is
      ``wikipedia:<variable_name>:<hint>`` (see
      :func:`_make_source_row_reference`).
    - ``confidence`` is ``NULL`` (set by Stage 11).
    - ``notes`` carries the request audit trail: action, query, the
      page title (when present), and the parser-emitted hint.
    """
    if df.empty:
        return []

    # Index specs by raw_column (action) for O(1) lookup.
    specs_by_action: dict[str, IndicatorSpec] = {
        spec.raw_column: spec for spec in specs
    }

    rows: list[SourceObservation] = []
    for _, raw_row in df.iterrows():
        action = str(raw_row.get("action") or "").strip()
        spec = specs_by_action.get(action)
        if spec is None:
            # Row for an action not in the catalog. The orchestrator
            # filters by the catalog's actions at the read step, so
            # this branch is defensive only -- if a future caller
            # bypasses the orchestrator and constructs a DataFrame
            # directly, the unknown action is silently skipped
            # (logged at DEBUG).
            _logger.debug(
                "Skipping Wikipedia row for action=%s absent from "
                "catalog",
                action,
            )
            continue
        hint = str(raw_row.get("source_row_reference_hint") or "").strip()
        query = raw_row.get("query")
        title = raw_row.get("title")
        pageid = raw_row.get("pageid")
        try:
            pageid_int = int(pageid) if pageid is not None else None
            if pageid_int is not None and pageid_int < 0:
                pageid_int = None
        except (TypeError, ValueError):
            pageid_int = None
        raw_value_text = str(raw_row.get("raw_value") or "")
        rows.append(
            SourceObservation(
                source_id=0,  # set by the DB layer
                country_id=None,  # Stage 3 fills this in
                leader_id=None,  # Stage 4 fills this in
                year=None,  # Wikipedia Action API does not return a year
                variable_name=spec.variable_name,
                raw_value=raw_value_text,
                normalized_value=None,  # Wikipedia has no numeric value
                unit=spec.unit,
                source_row_reference=_make_source_row_reference(
                    hint=hint, variable_name=spec.variable_name,
                ),
                confidence=None,  # set by Stage 11
                notes=(
                    f"raw_scale={spec.raw_scale}; "
                    f"higher_is_better="
                    f"{1 if spec.higher_is_better else 0}; "
                    f"action={action}; "
                    f"query={query}; "
                    f"title={title}; "
                    f"pageid={pageid_int}; "
                    f"hint={hint}"
                ),
            )
        )
    return rows


__all__ = [
    "_build_observation_rows",
    "_make_source_row_reference",
    "_parse_download_date",
    "_read_wikipedia_bundle_metadata",
]
