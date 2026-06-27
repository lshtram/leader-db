"""Request-scoping warning builders for the clean Wikipedia adapter.

The readiness envelope in :mod:`._readiness` surfaces a structured
:class:`SourceWarning` per request-scoping anomaly. This module
owns the warning builders so the readiness module stays focused on
the cache / metadata / version / queries gates.

Surfaces:

- ``UNSUPPORTED_FILTER`` when ``years=`` is set (Wikipedia Action
  API responses are not year-scoped; the filter is ignored).
- ``UNSUPPORTED_FILTER`` when ``countries=`` is set (Wikipedia
  Action API responses do not return country-coded rows; the
  filter is ignored; the unified adapter never invents ISO3).

The leader-filter warning is intentionally NOT raised for the
clean slice: ``request.leaders`` IS the query-string list for this
source (the documented clean-slice contract).
"""

from __future__ import annotations

from leaders_db.sources.contracts import SourceIngestRequest, SourceWarning
from leaders_db.sources.warnings import UNSUPPORTED_FILTER


def request_warnings(
    request: SourceIngestRequest,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    See module docstring for the per-warning rationale.
    """
    warnings: list[SourceWarning] = []
    if request.years:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "Wikipedia Action API responses are not "
                    "year-scoped; the years= filter is ignored. The "
                    "unified adapter never invents proxy years; "
                    "Stage 11 may resolve the year from the page "
                    "metadata if needed."
                ),
                severity="warning",
                source_id=request.source_id,
                context={
                    "requested_years": list(request.years),
                },
            )
        )
    if request.countries:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "Wikipedia Action API responses do not return "
                    "country-coded rows; the countries= filter is "
                    "ignored. The unified adapter never invents ISO3 "
                    "country codes; Stage 3 country match resolves "
                    "the source-native title to a country when "
                    "applicable."
                ),
                severity="warning",
                source_id=request.source_id,
                context={
                    "requested_countries": list(request.countries),
                },
            )
        )
    return tuple(warnings)


__all__ = ["request_warnings"]
