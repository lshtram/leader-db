"""Ruler-column population for the Country-Year Chronicle row builder.

Split out of :mod:`row_builder` during the Increment 3 reviewer-gate
follow-up so :mod:`row_builder` stays under the documented 400-line
convention. See
``docs/country-year-chronicle-increment-3.md`` §9 and
``docs/workplan.md`` for the module-layout rationale.

Public helpers:

- :func:`populate_ruler_placeholder` — emit the canonical
  ``missing_ruler`` placeholder row (kept for back-compat with older
  fixtures that pre-date the Increment 2 ruler resolver).
- :func:`populate_ruler_fields` — lift a :class:`RulerResult` into the
  row's ruler columns (``ruler_name`` / ``ruler_title`` /
  ``ruler_type`` / ``ruler_source`` / ``ruler_source_year_used`` /
  ``ruler_confidence``).
"""

from __future__ import annotations

from ._formatters import coerce_int
from .constants import SOURCE_NA
from .ruler_resolver import RulerResult


def populate_ruler_placeholder(row: dict[str, str]) -> None:
    """Populate the ruler fields with placeholder values + ``missing_ruler`` flag.

    Used when the row builder has no :class:`RulerResolver` (e.g.
    older test fixtures that still emit the Increment 1
    placeholder). The columns are emitted empty with a
    0-confidence placeholder so the CSV row is well-formed and
    downstream consumers can filter on the ``ruler_confidence``
    field.
    """
    row["ruler_name"] = ""
    row["ruler_title"] = ""
    row["ruler_type"] = ""
    row["ruler_source"] = SOURCE_NA
    row["ruler_source_year_used"] = ""
    row["ruler_confidence"] = coerce_int(0)
    row["shared_rule_flag"] = ""
    row["disputed_rule_flag"] = ""


def populate_ruler_fields(
    row: dict[str, str], ruler: RulerResult
) -> None:
    """Populate the ruler columns from a :class:`RulerResult`.

    When the resolver returned ``has_ruler=False`` (the
    missing-ruler path), the row carries the canonical placeholder
    fields. The ``missing_ruler`` flag is added by
    :func:`assemble_flags` based on the ``ruler.has_ruler`` bit.
    """
    if ruler.has_ruler:
        row["ruler_name"] = ruler.ruler_name
        row["ruler_title"] = ruler.ruler_title
        row["ruler_type"] = ruler.ruler_type
        row["ruler_source"] = ruler.ruler_source
        row["ruler_source_year_used"] = coerce_int(
            ruler.ruler_source_year_used,
        )
        row["ruler_confidence"] = coerce_int(ruler.ruler_confidence)
    else:
        row["ruler_name"] = ""
        row["ruler_title"] = ""
        row["ruler_type"] = ""
        row["ruler_source"] = SOURCE_NA
        row["ruler_source_year_used"] = ""
        row["ruler_confidence"] = coerce_int(0)
    # These two are intentionally left empty in Increment 2;
    # they require a dedicated source-level investigation that the
    # conservative resolver does not pretend to do.
    row["shared_rule_flag"] = ""
    row["disputed_rule_flag"] = ""


__all__ = [
    "populate_ruler_fields",
    "populate_ruler_placeholder",
]
