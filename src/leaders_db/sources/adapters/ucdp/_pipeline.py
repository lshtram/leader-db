"""Unified-source UCDP transform-pipeline orchestration.

Owns the body of :meth:`UCDPAdapter.transform` extracted into
a free function :func:`transform_ucdp_observations` so the
adapter class module stays focused on lifecycle wiring +
registration. The function applies the request year / country
filters on the wide-format country-year DataFrame returned by
:mod:`._raw_read` and delegates the per-row
:class:`NormalizedObservation` emission to
:func:`emit_ucdp_observations` in :mod:`._transform`.

Split out of :mod:`.adapter` to keep the adapter class
focused on the lifecycle class + the protocol conformance
guard + the registration helpers while preserving the
documented end-to-end behaviour the reviewer gate requires
(every blocker surfaces a structured
:class:`SourceWarning`).

Lazy catalog loading
--------------------

The legacy :func:`leaders_db.ingest.ucdp_io.load_indicator_catalog`
is the single source of truth for the 6 catalog indicators.
The transform layer loads the catalog lazily inside
:func:`transform_ucdp_observations` so the unified adapter
never imports legacy code at module level. The legacy catalog
path resolves through :data:`DEFAULT_CATALOG_PATH` in
:mod:`._catalog`.

Country filtering
-----------------

The UCDP ``country_id`` column is UCDP's own integer country
identifier (NOT ISO3). The request ``countries=`` filter
applies as an exact match against the UCDP ``country_id``
(supplied as the stringified integer, e.g. ``"645"`` for
Iraq). This is the canonical contract documented in the
brief. Downstream Stage 3 country match resolves the UCDP
``country_id`` to our canonical ISO3.

Callers who want to filter by ISO3 must use the legacy path
or Stage 3 country match to resolve first. Passing an ISO3
code to ``request.countries`` will produce zero observations
(no UCDP row has an ISO3 ``country_id``); the readiness gate
does NOT warn on this because the contract is
documented-and-tested rather than inferred.
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
from ._raw_read import _zip_path
from ._transform import emit_ucdp_observations


def transform_ucdp_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
    *,
    catalog_path: Path | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide raw frame into
    :class:`NormalizedObservation` records.

    Honors ``request.years`` and ``request.countries`` by
    filtering the wide-format DataFrame after the legacy
    read (the legacy reader returns the full frame when
    called with ``year=None``; the new adapter owns the
    request-scoping logic). ``request.leaders`` is
    unsupported for a country-year conflict source and
    surfaces a structured ``UNSUPPORTED_FILTER`` warning per
    SRC-REQ-005 (the warning is surfaced on the readiness
    envelope; the transform does not re-emit per-row to
    avoid double-counting in the warnings audit trail).
    Out-of-coverage years (anything outside 1989-2022)
    emit zero rows plus a structured ``YEAR_ABSENT``
    warning per offending year (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003 -- the warning is surfaced
    on the readiness envelope; the transform narrows the
    wide frame to the requested years and produces zero
    rows for the out-of-coverage case).

    The legacy indicator catalog is loaded lazily inside
    this function (NOT at module level) so the unified
    package boundary is preserved. The catalog path
    defaults to :data:`DEFAULT_CATALOG_PATH` but may be
    overridden via the ``catalog_path`` keyword argument
    for tests that stage a custom catalog.
    """
    if not isinstance(raw.payload, dict):
        raise ValueError(
            "UCDPAdapter.transform: raw.payload must be a "
            "dict carrying the wide DataFrame under 'wide_df'."
        )
    wide_df = raw.payload.get("wide_df")
    if wide_df is None:
        raise ValueError(
            "UCDPAdapter.transform: raw.payload has no "
            "'wide_df' key; read_raw must populate it."
        )
    metadata = raw.payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    # Apply the request year + country filters on the wide
    # frame. The legacy wide-format DataFrame has integer
    # ``year`` and integer ``country_id`` columns. The
    # ``country_id`` is UCDP's own integer id (NOT ISO3);
    # Stage 3 country match resolves it to our canonical
    # ISO3.
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
        # ``DataFrame.isin`` on the ``year`` column accepts
        # a set of ints; the resulting boolean mask filters
        # to the requested years. Out-of-coverage years are
        # still passed here (the readiness gate fires the
        # YEAR_ABSENT warning per offending year; the
        # filter then produces zero rows for them, matching
        # the readiness envelope's contract).
        filtered_df = filtered_df.loc[
            filtered_df["year"].astype(int).isin(years_set),
        ]
    if countries_arg:
        # Match the UCDP ``country_id`` (integer) against
        # the request ``countries`` (string). Cast each
        # request country to int when possible; the legacy
        # wide frame has integer ``country_id`` values.
        countries_int_set: set[int] = set()
        for country in countries_arg:
            try:
                countries_int_set.add(int(country))
            except (TypeError, ValueError):
                # Silently skip non-integer ISO3 codes; the
                # readiness gate does NOT warn on this
                # because the contract is documented in
                # :mod:`._readiness`.
                continue
        if countries_int_set:
            filtered_df = filtered_df.loc[
                filtered_df["country_id"].astype(int).isin(
                    countries_int_set,
                ),
            ]
        else:
            # Every requested country was non-integer (e.g.
            # an ISO3 code); no row can match. Emit zero
            # observations by narrowing to an empty frame.
            filtered_df = filtered_df.iloc[0:0]

    zip_path = raw.payload.get("zip_path")
    zip_path_value = (
        zip_path if isinstance(zip_path, Path) else None
    )
    # The zip path is also derivable from the request
    # payload via the ``_zip_path`` helper -- prefer the
    # staged one if it carries through, fall back to the
    # helper-derived path when the raw payload does not.
    if zip_path_value is None:
        zip_path_value = _zip_path(request)

    # Lazy-load the legacy indicator catalog. The legacy
    # loader returns the canonical ``IndicatorSpec`` list
    # which the transform layer uses to drive the per-row
    # emission.
    specs = load_indicator_catalog(
        catalog_path=catalog_path or DEFAULT_CATALOG_PATH,
    )

    return emit_ucdp_observations(
        filtered_df,
        request,
        zip_path_value,
        metadata,
        specs=specs,
    )


__all__ = ["transform_ucdp_observations"]
