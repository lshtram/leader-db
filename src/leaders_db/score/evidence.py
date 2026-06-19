"""Stage 5 evidence bundle contract (requirement §8, REQ-STAGE-006/007).

The production scorer does **not** receive a single raw number per category.
It receives an explicit per-country/year/category evidence bundle that
carries:

- the **expected** source set (``CategorySourcePlan``),
- the **available** observations (``tuple[EvidenceObservation, ...]``),
- the **missing** observations and the reason each one is missing
  (``tuple[MissingObservation, ...]``),
- raw locators, normalized values, direction, temporal fit, and
  per-observation authority/specificity scores,
- a small read-only ``category_metadata`` slot for category-specific
  audit-trail context.

This module is the typed contract for that bundle. It deliberately has no
database or filesystem dependencies — bundles can be built, stored, and
materialized as JSON/CSV without coupling to SQLAlchemy or to any
specific adapter. Wiring to ``source_observations`` rows lives in
:mod:`leaders_db.resolve.indicators` (Stage 5 orchestrator) and the
materialization layer under ``data/outputs/``.

Module layout
-------------

The contract is split across focused modules so each file stays small
and acyclic:

- :mod:`leaders_db.score.evidence_types` — enums + ``IndicatorSpec``
  (the vocabulary).
- :mod:`leaders_db.score.evidence_observation` — ``EvidenceObservation``
  + ``MissingObservation`` (the per-row payload types).
- :mod:`leaders_db.score.evidence_plan` — ``CategorySourcePlan`` (the
  expected source set for one rating category).
- :mod:`leaders_db.score.evidence_bundle` — ``CategoryEvidenceBundle``
  (the full per-country/year/category bundle).

This file is the **re-export facade** so the public import path
``from leaders_db.score.evidence import CategoryEvidenceBundle`` (and
the other ten public names) keeps working unchanged across the split.
``leaders_db.score.__init__`` re-exports the same names.

Why frozen dataclasses (not Pydantic):

- The architecture document (``docs/architecture.md`` §"Evidence Bundle
  Contract") says "Pydantic or typed dataclasses". The ``score/`` package
  already uses ``@dataclass(frozen=True)`` for internal typed payloads
  (see ``confidence.py``); the strict Pydantic boundary in this codebase
  is reserved for the LLM JSON contract (``llm/schemas.py``) and config
  (``config.py``).
- Evidence bundles are internal data carriers, not JSON payloads that
  cross a file/CLI/provider boundary, so dataclasses are the right fit.

Immutability contract (REQ-NFR-AUDIT-001, REQ-SCORE-004):

- The dataclasses are ``frozen=True``, so scalar fields are immutable.
- For sequence fields (``expected_sources``, ``expected_indicators``,
  ``allowed_proxy_years``, ``default_source_weights``, ``observations``,
  ``missing``) the constructor accepts any sequence, defensively copies
  it to a ``tuple`` in ``__post_init__`` via ``object.__setattr__``, and
  stores only the tuple. Callers can therefore pass a list and mutate
  it after construction without leaking into the bundle.
- For the ``category_metadata`` mapping, the constructor accepts any
  ``Mapping`` (or ``None``), copies its contents into a **fresh** dict,
  and stores a :class:`types.MappingProxyType` view of that copy. The
  copy is unconditional — even when the caller passes a
  ``MappingProxyType`` wrapping a mutable backing dict — so later
  mutation of the caller's container cannot leak into the bundle. Item
  assignment on the bundle's metadata raises ``TypeError``.

Style invariants (per ``docs/coding-guidelines.md``):

- Type hints on every public field and method.
- ``from __future__ import annotations`` for forward-reference safety.
- Light ``__post_init__`` validation on numeric fields, matching
  ``confidence.py``.
- No mutable defaults; ``default_factory=tuple`` for sequences and a
  module-level ``_EMPTY_*`` sentinel for the bundle observation /
  missing defaults.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from .evidence_bundle import CategoryEvidenceBundle
from .evidence_observation import EvidenceObservation, MissingObservation
from .evidence_plan import CategorySourcePlan
from .evidence_types import (
    Direction,
    IndicatorRole,
    IndicatorSpec,
    MissingReason,
    MissingSeverity,
    SparseDataPolicy,
    TemporalKind,
)

__all__ = [
    "CategoryEvidenceBundle",
    "CategorySourcePlan",
    "Direction",
    "EvidenceObservation",
    "IndicatorRole",
    "IndicatorSpec",
    "MissingObservation",
    "MissingReason",
    "MissingSeverity",
    "SparseDataPolicy",
    "TemporalKind",
]
