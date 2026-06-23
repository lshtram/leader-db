"""Selection + numeric-coercion helpers for the Stage 5 evidence-bundle builder.

This module groups the pure (or near-pure) helpers used by
:mod:`leaders_db.resolve.indicators_collection` to convert the
raw ``SourceObservation`` rows into :class:`EvidenceObservation` /
:class:`MissingObservation` records:

- :func:`select_best_row` picks the best-fit year from a list of
  candidate rows under a fully-documented deterministic tie-breaker.
- :func:`temporal_kind_for` classifies a year delta as ``DIRECT``,
  ``PROXY``, ``STALE``, or ``NOT_AVAILABLE``.
- :func:`severity_for_indicator` maps an indicator's
  :class:`~leaders_db.score.evidence.IndicatorRole` to the
  :class:`~leaders_db.score.evidence.MissingSeverity` carried on
  every ``MissingObservation``.
- :func:`coerce_float` / :func:`coerce_numeric` convert the adapter's
  raw / normalized strings into the float values recorded on
  ``EvidenceObservation``.

Deterministic selection
-----------------------

:func:`select_best_row` picks the best-fit year from a list of
candidate rows. The tie-breaker is fully documented and stable:

1. ``DIRECT`` (year delta == 0) beats ``PROXY`` (year delta in
   ``plan.allowed_proxy_years``). Stale rows are skipped.
2. Within a tier, smaller ``abs(observation_year - target_year)``
   wins (closest year).
3. Within (tier, delta), the **later** ``observation_year`` wins
   (most recent published data point).
4. Within (tier, delta, year), the **lower** ``source_id`` wins
   (stable DB insertion order; the source registry is unique).
5. Within (tier, delta, year, source_id), the **lower**
   ``SourceObservation.id`` wins (stable DB insertion order).

The (4)/(5) tie-breakers matter when multiple rows share the same
canonical source key (e.g. two registry rows that both substring-
match ``"V-Dem"``): the builder consistently picks the row that
was inserted first. Tests in
``tests/test_resolve_indicators_builder_selection.py`` exercise the
deterministic contract by inserting tied candidates in different
orders and asserting the same selected row.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Type hints on every public function parameter and return.
- No mutable defaults.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..db.models import Source, SourceObservation
from ..score.evidence import (
    IndicatorRole,
    MissingSeverity,
    TemporalKind,
)
from ..score.source_plans import (
    CategorySourcePlan,
    IndicatorSpec,
)

__all__ = [
    "coerce_float",
    "coerce_numeric",
    "select_best_row",
    "severity_for_indicator",
    "temporal_kind_for",
]


# ---------------------------------------------------------------------------
# Pure selection helpers
# ---------------------------------------------------------------------------


def select_best_row(
    rows: Sequence[tuple[SourceObservation, Source]],
    target_year: int,
    plan: CategorySourcePlan,
) -> tuple[SourceObservation, Source] | None:
    """Pick the best-fit (observation, source) row for the target year.

    Tie-breaker (stable, fully documented in this module's docstring):

    1. ``DIRECT`` (year delta == 0) beats ``PROXY`` (year delta in
       ``plan.allowed_proxy_years``). Rows outside the proxy budget
       (``STALE`` rows) are skipped.
    2. Within a tier, smaller ``abs(observation_year - target_year)``
       wins (closest year).
    3. Within (tier, delta), the **later** ``observation_year``
       wins (most recent published data point).
    4. Within (tier, delta, year), the **lower** ``source.id`` wins
       (stable DB insertion order).
    5. Within (tier, delta, year, source_id), the **lower**
       ``SourceObservation.id`` wins (stable DB insertion order).

    The query that feeds this function is required to order by
    ``SourceObservation.id`` so the (4)/(5) tie-breakers are
    deterministic. Rows whose ``year`` is ``None`` are skipped.
    """
    if not rows:
        return None
    proxy_budget = {abs(d) for d in plan.allowed_proxy_years}

    def sort_key(
        pair: tuple[SourceObservation, Source],
    ) -> tuple[int, int, int, int, int]:
        obs, source = pair
        if obs.year is None:
            # Sort sentinel: any (year=None) row lands at the end of
            # the candidate list so a deterministic row wins before
            # any yearless row. The caller filters out year=None
            # rows before they reach this function in practice, but
            # the key is total so the sort never raises.
            return (2, 0, 0, int(source.id), int(obs.id))
        delta = abs(obs.year - target_year)
        if delta == 0:
            tier = 0  # DIRECT
        elif delta in proxy_budget:
            tier = 1  # PROXY
        else:
            tier = 2  # STALE — will be filtered after sort
        # Negate observation_year so a later year sorts before an
        # earlier year (T3: prefer the most recent published data
        # point on tied delta).
        return (
            tier,
            delta,
            -int(obs.year),
            int(source.id),
            int(obs.id),
        )

    sorted_rows = sorted(rows, key=sort_key)
    # Drop STALE rows (tier == 2) and yearless rows (tier == 2 too).
    for obs, source in sorted_rows:
        if obs.year is None:
            continue
        delta = abs(obs.year - target_year)
        if delta == 0 or delta in proxy_budget:
            return (obs, source)
    return None


def temporal_kind_for(
    observation_year: int | None,
    target_year: int,
    plan: CategorySourcePlan,
) -> TemporalKind:
    """Classify an observation's year relative to the target year."""
    if observation_year is None:
        return TemporalKind.NOT_AVAILABLE
    if observation_year == target_year:
        return TemporalKind.DIRECT
    delta = abs(observation_year - target_year)
    if delta in {abs(d) for d in plan.allowed_proxy_years}:
        return TemporalKind.PROXY
    return TemporalKind.STALE


def severity_for_indicator(
    spec: IndicatorSpec, plan: CategorySourcePlan
) -> MissingSeverity:
    """Map an indicator's :class:`IndicatorRole` to a missing severity."""
    role = plan.role_of(spec.variable_name)
    if role is IndicatorRole.REQUIRED:
        return MissingSeverity.PRIMARY
    if role is IndicatorRole.PREFERRED:
        return MissingSeverity.IMPORTANT
    return MissingSeverity.OPTIONAL


# ---------------------------------------------------------------------------
# Numeric coercion (used to populate EvidenceObservation numeric_value /
# normalized_value from the adapter's raw / normalized strings)
# ---------------------------------------------------------------------------


def coerce_float(value: object) -> float | None:
    """Best-effort float coercion; returns ``None`` for unparseable values.

    NaN (``float('nan')`` and ``pandas.NA`` cast to float) is
    normalised to ``None`` via :func:`math.isnan`. Bool and ``int``
    are accepted as numeric. Strings are stripped and parsed with
    :func:`float`; empty / whitespace-only / unparseable strings
    return ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, int):
        return float(value)
    if not isinstance(value, str):
        return None
    return _coerce_float_from_string(value)


def _coerce_float_from_string(value: str) -> float | None:
    """Parse a string to float; return ``None`` for empty / unparseable text."""
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def coerce_numeric(
    normalized_value: object, raw_value: object
) -> float | None:
    """Return the bundle's :attr:`numeric_value` for an observation row.

    Prefers the adapter's pre-computed ``normalized_value`` when it
    is parseable; otherwise falls back to a light coercion of the
    ``raw_value`` string. Returns ``None`` when neither is usable.
    """
    parsed = coerce_float(normalized_value)
    if parsed is not None:
        return parsed
    return coerce_float(raw_value)
