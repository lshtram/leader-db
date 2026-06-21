"""Political-regime and system-type column population for the row builder.

Split out of :mod:`row_builder` during the Increment 3 reviewer-gate
follow-up so :mod:`row_builder` stays under the documented 400-line
convention. See
``docs/country-year-chronicle-increment-3.md`` §9 and
``docs/workplan.md`` for the module-layout rationale.

Public helpers:

- :func:`populate_regime` — populate the ``political_regime_*``
  columns from a :class:`RegimeBucketResult`.
- :func:`populate_system_type` — populate the ``system_type_*``
  columns from a :class:`SystemTypeResult`.
"""

from __future__ import annotations

from ._formatters import coerce_int
from .regime import RegimeBucketResult
from .system_type import SystemTypeResult


def populate_regime(row: dict[str, str], bucket: RegimeBucketResult) -> None:
    """Populate the political-regime columns from a :class:`RegimeBucketResult`."""
    row["political_regime_bucket"] = bucket.bucket
    row["political_regime_raw_score"] = bucket.raw_score
    row["political_regime_source"] = bucket.source
    row["political_regime_source_year_used"] = coerce_int(
        bucket.source_year_used
    )
    row["political_regime_confidence"] = coerce_int(bucket.confidence)


def populate_system_type(row: dict[str, str], st: SystemTypeResult) -> None:
    """Populate the system-type columns from a :class:`SystemTypeResult`."""
    row["system_type_primary"] = st.primary
    row["system_type_secondary"] = st.secondary
    row["system_type_source"] = st.source
    row["system_type_confidence"] = coerce_int(st.confidence)
    row["system_type_notes"] = st.notes


__all__ = [
    "populate_regime",
    "populate_system_type",
]
