"""Unified-source World Bank WGI transform-pipeline orchestration.

Owns the body of :meth:`WGIAdapter.transform` extracted into
a free function :func:`transform_world_bank_wgi_observations`
so the adapter class module stays focused on lifecycle wiring
+ registration. The function applies the request year /
country filters on the wide-format DataFrame returned by
:mod:`._raw_read` and delegates the per-row
:class:`NormalizedObservation` emission to
:func:`emit_world_bank_wgi_observations` in :mod:`._transform`.

Split out of :mod:`.adapter` to keep the adapter class focused
on the lifecycle class + the protocol conformance guard + the
registration helpers while preserving the documented
end-to-end behaviour the reviewer gate requires (every blocker
surfaces a structured :class:`SourceWarning`).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawReadResult,
    SourceIngestRequest,
)

from ._raw_read import _xlsx_path
from ._transform import emit_world_bank_wgi_observations


def transform_world_bank_wgi_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    """Convert the wide raw frame into
    :class:`NormalizedObservation` records.

    Honors ``request.years`` and ``request.countries`` by
    filtering the wide-format DataFrame after the legacy read
    (the legacy reader returns the full frame when called with
    ``year=None``; the new adapter owns the request-scoping
    logic). ``request.leaders`` is unsupported for a
    country-year governance source and surfaces a structured
    ``UNSUPPORTED_FILTER`` warning per SRC-REQ-005 (the warning
    is surfaced on the readiness envelope; the transform does
    not re-emit per-row to avoid double-counting in the
    warnings audit trail). Out-of-coverage years (anything
    outside 1996-2022) emit zero rows plus a structured
    ``YEAR_ABSENT`` warning per offending year (no stale-proxy
    fill per SRC-COV-002 / SRC-COV-003 -- the warning is
    surfaced on the readiness envelope; the transform
    narrows the wide frame to the requested years and produces
    zero rows for the out-of-coverage case).
    """
    if not isinstance(raw.payload, dict):
        raise ValueError(
            "WGIAdapter.transform: raw.payload must be a dict "
            "carrying the wide DataFrame under 'wide_df'."
        )
    wide_df = raw.payload.get("wide_df")
    if wide_df is None:
        raise ValueError(
            "WGIAdapter.transform: raw.payload has no 'wide_df' "
            "key; read_raw must populate it."
        )
    metadata = raw.payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    # Apply the request year + country filters on the wide
    # frame. The legacy wide-format DataFrame has integer
    # ``year`` and string ``iso3`` columns.
    filtered_df = wide_df
    years_arg: tuple[int, ...] | None = (
        tuple(int(y) for y in request.years)
        if request.years else None
    )
    countries_arg: tuple[str, ...] | None = (
        tuple(str(c) for c in request.countries)
        if request.countries else None
    )

    if years_arg is not None:
        years_set = set(years_arg)
        # ``DataFrame.isin`` on the ``year`` column accepts a
        # set of ints; the resulting boolean mask filters to
        # the requested years. Out-of-coverage years are still
        # passed here (the readiness gate fires the
        # YEAR_ABSENT warning per offending year; the filter
        # then produces zero rows for them, matching the
        # readiness envelope's contract).
        filtered_df = filtered_df.loc[
            filtered_df["year"].astype(int).isin(years_set),
        ]
    if countries_arg:
        countries_set = set(countries_arg)
        filtered_df = filtered_df.loc[
            filtered_df["iso3"].astype(str).isin(countries_set),
        ]

    xlsx_path = raw.payload.get("xlsx_path")
    xlsx_path_value = (
        xlsx_path if isinstance(xlsx_path, Path) else None
    )
    # The xlsx path is also derivable from the request
    # payload via the ``_xlsx_path`` helper -- prefer the
    # staged one if it carries through, fall back to the
    # helper-derived path when the raw payload does not.
    if xlsx_path_value is None:
        xlsx_path_value = _xlsx_path(request)
    return emit_world_bank_wgi_observations(
        filtered_df, request, xlsx_path_value, metadata,
    )


__all__ = ["transform_world_bank_wgi_observations"]
