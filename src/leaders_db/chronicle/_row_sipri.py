"""SIPRI military-spend column population for the row builder.

Split out of :mod:`row_builder` during the Increment 3 reviewer-gate
follow-up so :mod:`row_builder` stays under the documented 400-line
convention. See
``docs/country-year-chronicle-increment-3.md`` §9 and
``docs/workplan.md`` for the module-layout rationale.

Public helpers:

- :func:`populate_sipri_fields` — populate the ``military_spend_*``
  columns from a SIPRI lookup result and return ``has_milex``
  (whether the canonical ``milex_constant_usd`` field was found).
"""

from __future__ import annotations

from ._formatters import coerce_float, coerce_int
from .constants import SOURCE_NA, SOURCE_TAG_SIPRI


def populate_sipri_fields(
    row: dict[str, str],
    sipri_values: dict[str, float | None],
    *,
    year: int,
) -> bool:
    """Populate the SIPRI military-spend columns. Returns ``has_milex``.

    The ``missing_military_spend`` flag is driven **only** by the
    canonical CSV target field ``milex_constant_usd``. Ancillary
    SIPRI fields (per-capita, share-of-GDP) may be present in the
    lookup result but must not clear the flag on their own — the row
    builder treats them as supporting context, not as evidence that
    a usable military-spend value was found.
    """
    milex = sipri_values.get("milex_constant_usd")
    has_milex = milex is not None
    if has_milex:
        row["military_spend"] = coerce_float(milex, decimals=0)
        row["military_spend_unit"] = "constant_usd"
        row["military_spend_source"] = SOURCE_TAG_SIPRI
        row["military_spend_source_year_used"] = coerce_int(year)
    else:
        row["military_spend"] = ""
        row["military_spend_unit"] = ""
        row["military_spend_source"] = SOURCE_NA
        row["military_spend_source_year_used"] = ""
    return has_milex


__all__ = [
    "populate_sipri_fields",
]
