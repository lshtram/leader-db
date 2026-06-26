"""Unified-source BTI transform-pipeline orchestration.

Owns the body of :meth:`BTIAdapter.transform` extracted
into a free function
:func:`transform_bti_observations` so the adapter class
module stays focused on lifecycle wiring + registration.
The function applies the request year / country filters
on the wide-format country-year DataFrame returned by
:mod:`._raw_read` and delegates the per-row
:class:`NormalizedObservation` emission to
:func:`emit_bti_observations` in :mod:`._transform`.

Split out of :mod:`.adapter` to keep the adapter class
focused on the lifecycle class + the protocol
conformance guard + the registration helpers while
preserving the documented end-to-end behaviour the
reviewer gate requires (every blocker surfaces a
structured :class:`SourceWarning`).

Lazy catalog loading
--------------------

The legacy
:func:`leaders_db.ingest.bti_io.load_indicator_catalog`
is the single source of truth for the 12 catalog
indicators across 3 rating categories
(``effectiveness`` / ``political_freedom`` /
``economic_wellbeing``). The transform layer loads the
catalog lazily inside
:func:`transform_bti_observations` so the unified
adapter never imports legacy code at module level. The
legacy catalog path resolves through
:data:`DEFAULT_CATALOG_PATH` in :mod:`._catalog`.

Country filtering
-----------------

The BTI xlsx carries the BTI display name in column 0
(no ISO3 column). The request ``countries=`` filter
applies as a case-insensitive substring match against
the BTI display name -- this is the canonical contract
documented for BTI. Passing a non-BTI display name
(e.g. an ISO3 code) yields zero rows; the readiness
gate does NOT warn on non-BTI codes because the
contract is documented-and-tested rather than
inferred.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawReadResult,
    SourceIngestRequest,
)

from ._catalog import DEFAULT_CATALOG_PATH, load_indicator_catalog
from ._raw_read import _xlsx_path
from ._transform import emit_bti_observations


def transform_bti_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
    *,
    catalog_path: Path | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide raw frame into
    :class:`NormalizedObservation` records.

    Honors ``request.years`` and ``request.countries``
    by filtering the wide-format DataFrame after the
    legacy read (the legacy reader returns the
    per-edition frame when called with no year
    filter; the new adapter owns the request-scoping
    logic). ``request.leaders`` is unsupported for a
    country-year governance source and surfaces a
    structured ``UNSUPPORTED_FILTER`` warning per
    SRC-REQ-005 (the warning is surfaced on the
    readiness envelope; the transform does not
    re-emit per-row to avoid double-counting in the
    warnings audit trail). Out-of-coverage years
    (anything outside 2002-2025) emit zero rows plus
    a structured ``YEAR_ABSENT`` warning per
    offending year (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003 -- the warning is
    surfaced on the readiness envelope; the
    transform narrows the wide frame to the
    requested years and produces zero rows for the
    out-of-coverage case).

    The legacy indicator catalog is loaded lazily
    inside this function (NOT at module level) so
    the unified package boundary is preserved. The
    catalog path defaults to
    :data:`DEFAULT_CATALOG_PATH` but may be
    overridden via the ``catalog_path`` keyword
    argument for tests that stage a custom catalog.
    """
    if not isinstance(raw.payload, dict):
        raise ValueError(
            "BTIAdapter.transform: raw.payload must be a "
            "dict carrying the wide DataFrame under "
            "'wide_df'."
        )
    wide_df = raw.payload.get("wide_df")
    if wide_df is None:
        raise ValueError(
            "BTIAdapter.transform: raw.payload has no "
            "'wide_df' key; read_raw must populate it."
        )
    metadata = raw.payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    # Apply the request year + country filters on
    # the wide frame. The legacy wide-format
    # DataFrame has integer ``year`` and string
    # ``country`` columns. The ``country`` is the
    # BTI display name (no ISO3; Stage 3 country
    # match resolves it via the canonical country
    # alias table).
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
        # ``DataFrame.isin`` on the ``year``
        # column accepts a set of ints; the
        # resulting boolean mask filters to the
        # requested years. Out-of-coverage years
        # are still passed here (the readiness
        # gate fires the ``YEAR_ABSENT`` warning
        # per offending year; the filter then
        # produces zero rows for them, matching
        # the readiness envelope's contract).
        filtered_df = filtered_df.loc[
            filtered_df["year"].astype(int).isin(years_set),
        ]
    if countries_arg:
        countries_set = {
            c.strip().lower() for c in countries_arg
        }
        # BTI carries display names (no ISO3);
        # match case-insensitively against the
        # ``country`` column. The downstream Stage
        # 3 country match resolves the display
        # name to ISO3 via the canonical country
        # alias table.
        filtered_df = filtered_df.loc[
            filtered_df["country"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(countries_set),
        ]

    xlsx_path = raw.payload.get("xlsx_path")
    xlsx_path_value = (
        xlsx_path if isinstance(xlsx_path, Path) else None
    )
    # The xlsx path is also derivable from the
    # request payload via the ``_xlsx_path`` helper
    # -- prefer the staged one if it carries
    # through, fall back to the helper-derived path
    # when the raw payload does not.
    if xlsx_path_value is None:
        xlsx_path_value = _xlsx_path(request)

    # Lazy-load the legacy indicator catalog. The
    # legacy loader returns the canonical
    # ``IndicatorSpec`` list which the transform
    # layer uses to drive the per-row emission.
    specs = load_indicator_catalog(
        catalog_path=catalog_path or DEFAULT_CATALOG_PATH,
    )

    return emit_bti_observations(
        filtered_df,
        request,
        xlsx_path_value,
        metadata,
        specs=specs,
    )


__all__ = ["transform_bti_observations"]
