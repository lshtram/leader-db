"""Unified-source RSF transform-pipeline orchestration.

Owns the body of
:meth:`RSFPressFreedomAdapter.transform` extracted into
a free function
:func:`transform_rsf_press_freedom_observations` so the
adapter class module stays focused on lifecycle wiring
+ registration. The function applies the request
year / country filters on the narrow-format
country-year DataFrame returned by :mod:`._raw_read`
and delegates the per-row
:class:`NormalizedObservation` emission to
:func:`emit_rsf_press_freedom_observations` in
:mod:`._transform`.

Split out of :mod:`.adapter` to keep the adapter
class focused on the lifecycle class + the protocol
conformance guard + the registration helpers while
preserving the documented end-to-end behaviour the
reviewer gate requires (every blocker surfaces a
structured :class:`SourceWarning`).

Lazy catalog loading
--------------------

The legacy
:func:`leaders_db.ingest.rsf_press_freedom_io.load_rsf_press_freedom_catalog`
is the single source of truth for the 7 catalog
indicators (``rsf_press_freedom_score`` +
``rsf_press_freedom_rank`` + the 5
component-context indicators). The transform layer
loads the catalog lazily inside
:func:`transform_rsf_press_freedom_observations` so
the unified adapter never imports legacy code at
module level. The legacy catalog path resolves
through :data:`DEFAULT_CATALOG_PATH` in
:mod:`._catalog`.

Country filtering
-----------------

The RSF CSVs carry the ``ISO`` 3-letter alphabetic
column (e.g. ``USA`` / ``MEX`` / ``SWE``); the
``ISO`` is the canonical primary key per the legacy
Stage 2 DB writer and the per-row
``source_row_reference`` shape. The request
``countries=`` filter applies as an exact match
against the ``ISO`` column -- this is the canonical
contract documented in
``docs/architecture/rsf_press_freedom.md`` §6 (when
that is finalized; in the meantime see the legacy
ingest module's per-row emission). Passing a non-ISO3
code (e.g. ``"United States"``) yields zero rows;
the readiness gate does NOT warn on non-ISO3 codes
because the contract is documented-and-tested rather
than inferred.
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
from ._transform import emit_rsf_press_freedom_observations


def transform_rsf_press_freedom_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
    *,
    catalog_path: Path | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the narrow raw frame into
    :class:`NormalizedObservation` records.

    Honors ``request.years`` and ``request.countries``
    by filtering the narrow-format DataFrame after the
    legacy read (the legacy reader returns the
    combined per-year frame when called with no year
    filter; the new adapter owns the request-scoping
    logic). ``request.leaders`` is unsupported for a
    country-year press-freedom source and surfaces a
    structured ``unsupported_filter`` warning per
    SRC-REQ-005 (the warning is surfaced on the
    readiness envelope; the transform does not
    re-emit per-row to avoid double-counting in the
    warnings audit trail). Out-of-coverage years
    (anything outside 2002-2026) emit zero rows plus
    a structured ``year_absent`` warning per offending
    year (no stale-proxy fill per SRC-COV-002 /
    SRC-COV-003 -- the warning is surfaced on the
    readiness envelope; the transform narrows the
    narrow frame to the requested years and produces
    zero rows for the out-of-coverage case). Year=2011
    surfaces a structured ``rsf_year_2011_absent``
    warning per the documented 2011 caveat (the
    direct ``2011.csv`` is absent; the 2012 file
    represents the combined 2011/2012 edition).

    The legacy indicator catalog is loaded lazily
    inside this function (NOT at module level) so the
    unified package boundary is preserved. The
    catalog path defaults to
    :data:`DEFAULT_CATALOG_PATH` but may be overridden
    via the ``catalog_path`` keyword argument for
    tests that stage a custom catalog.
    """
    if not isinstance(raw.payload, dict):
        raise ValueError(
            "RSFPressFreedomAdapter.transform: raw.payload "
            "must be a dict carrying the narrow DataFrame "
            "under 'narrow_df'."
        )
    narrow_df = raw.payload.get("narrow_df")
    if narrow_df is None:
        raise ValueError(
            "RSFPressFreedomAdapter.transform: raw.payload "
            "has no 'narrow_df' key; read_raw must populate "
            "it."
        )
    metadata = raw.payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    # Apply the request year + country filters on the
    # narrow frame. The legacy narrow-format DataFrame
    # has integer ``year`` and string ``iso3``
    # columns. The ``iso3`` is the canonical ISO
    # 3166-1 alpha-3 3-letter alphabetic code (e.g.
    # ``USA``); the unified transform surfaces it
    # verbatim on the observation ``country_code``
    # field.
    filtered_df = narrow_df
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
        # ``DataFrame.isin`` on the ``year`` column
        # accepts a set of ints; the resulting
        # boolean mask filters to the requested
        # years. Out-of-coverage years are still
        # passed here (the readiness gate fires the
        # ``year_absent`` warning per offending
        # year; the filter then produces zero rows
        # for them, matching the readiness
        # envelope's contract).
        filtered_df = filtered_df.loc[
            filtered_df["year"].astype(int).isin(years_set),
        ]
    if countries_arg:
        countries_set = {
            c.strip().upper() for c in countries_arg
        }
        filtered_df = filtered_df.loc[
            filtered_df["iso3"].astype(str).str.upper().isin(
                countries_set,
            ),
        ]

    csv_paths_raw = raw.payload.get("csv_paths")
    csv_paths = (
        list(csv_paths_raw)
        if isinstance(csv_paths_raw, list)
        else None
    )

    # Lazy-load the legacy indicator catalog. The
    # legacy loader returns the canonical
    # ``IndicatorSpec`` list which the transform
    # layer uses to drive the per-row emission.
    specs = load_indicator_catalog(
        catalog_path=catalog_path or DEFAULT_CATALOG_PATH,
    )

    return emit_rsf_press_freedom_observations(
        filtered_df,
        request,
        csv_paths,
        metadata,
        specs=specs,
    )


__all__ = ["transform_rsf_press_freedom_observations"]
