"""Deterministic vertical slice for a constrained investigation question.

Takes a question key and produces a chart-ready CSV, a static
HTML+SVG graph, and (optionally) refreshes the read-only Superset
SQLite artifact. See :func:`run_investigation_slice` for the contract.

This package implements a small end-to-end proof slice that exercises
the updated source architecture:

1. Wire a small set of unified-source adapters (PWT, Maddison, WDI by
   default) into an :class:`InMemorySourceRegistry`.
2. Drive the adapters through the documented ``check_ready ->
   read_raw -> transform`` lifecycle on each registered adapter. The
   not-ready outcome is reported as a per-source coverage gap; the
   slice continues with the remaining sources. Runtime failures from
   ``read_raw`` or ``transform`` are bugs and propagate.
3. Flatten the resulting :class:`NormalizedObservation` tuples into a
   single stream.
4. Run the semantic concept catalog
   (:func:`leaders_db.sources.concepts.extract_concept_result`) against
   the stream so the slice surfaces ``gdp_per_capita`` rows from
   every available source while preserving indicator codes, source
   ids, source versions, units, scales, and locators.
5. Materialise a chart-ready long-form CSV under
   ``data/processed/viz/country-year-chronicle/`` named
   ``viz_investigation_<question_key>.csv``. Every row carries the
   canonical ``question_key`` so the slice column is never blank.
6. Emit a deterministic dependency-free static HTML+SVG line chart
   beside the CSV so a human can see the result without new packages.
7. Refresh the read-only Superset-facing SQLite artifact via
   :func:`leaders_db.viz.superset_db.build_superset_sqlite_db` so the
   new table is visible to local Superset dashboards.

The slice is intentionally constrained:

- One supported question key (``gdp_per_capita_major_powers``) maps to
  one concept (``gdp_per_capita``). The mapping is a stable dictionary
  (:data:`SUPPORTED_QUESTIONS`) so callers cannot invent a free-form
  question: the slice fails fast on unknown keys.
- Each source is dispatched through the registry seam. The slice never
  reads raw files directly and never imports the legacy
  ``leaders_db.ingest`` subsystem. Source readiness gaps are reported
  as informational coverage rows; runtime failures inside
  ``read_raw`` / ``transform`` propagate so they cannot be hidden by a
  too-broad readiness guard.
- Partial coverage is the norm, not an error. The slice continues with
  whatever sources reported observations and emits the CSV + graph
  using the rows that materialised. Only the empty-result path
  (zero concept rows for the requested scope) is a hard failure --
  otherwise the slice would silently lose data when a real
  source-bundle gap exists.

Module layout (each module stays under the 400-line convention):

- :mod:`._models` -- public dataclasses and the supported question
  catalog (:class:`InvestigationQuestion`, :class:`InvestigationSliceRequest`,
  :class:`SourceCoverageRow`, :class:`InvestigationSliceResult`,
  :class:`UnknownInvestigationQuestionError`,
  :data:`SUPPORTED_QUESTIONS`, :data:`SUPPORTED_QUESTION_KEYS`).
- :mod:`._api` -- the public :func:`run_investigation_slice` entry
  point plus its private helpers (:func:`_resolve_question`,
  :func:`_expand_years`, :func:`_build_default_registry`,
  :func:`_run_one_source`, :func:`_filter_concept_rows`).
- :mod:`._csv` -- the long-form CSV writer plus the stable
  :data:`INVESTIGATION_CSV_COLUMNS` schema.
- :mod:`._html` -- the dependency-free HTML+SVG line-chart writer
  and its layout helpers.
"""

from __future__ import annotations

from ._api import run_investigation_slice
from ._csv import INVESTIGATION_CSV_COLUMNS
from ._models import (
    SUPPORTED_QUESTION_KEYS,
    SUPPORTED_QUESTIONS,
    InvestigationQuestion,
    InvestigationSliceRequest,
    InvestigationSliceResult,
    SourceCoverageRow,
    UnknownInvestigationQuestionError,
)

__all__ = [
    "INVESTIGATION_CSV_COLUMNS",
    "SUPPORTED_QUESTIONS",
    "SUPPORTED_QUESTION_KEYS",
    "InvestigationQuestion",
    "InvestigationSliceRequest",
    "InvestigationSliceResult",
    "SourceCoverageRow",
    "UnknownInvestigationQuestionError",
    "run_investigation_slice",
]
