"""Unified-source V-Dem transform-pipeline orchestration.

Owns the body of :meth:`VDemAdapter.transform` extracted into
a free function :func:`transform_vdem_observations` so the
adapter class module stays focused on lifecycle wiring +
registration. The function applies the request year / country
filters on the narrow DataFrame returned by :mod:`._raw_read`
and delegates the per-row :class:`NormalizedObservation`
emission to :func:`emit_vdem_observations` in
:mod:`._transform`.

Split out of :mod:`.adapter` to keep the adapter class
focused on the lifecycle class + the protocol conformance
guard + the registration helpers while preserving the
documented end-to-end behaviour the reviewer gate requires
(every blocker surfaces a structured
:class:`SourceWarning`).

Lazy catalog loading
--------------------

The legacy :func:`leaders_db.ingest.vdem_io.load_indicator_catalog`
is the single source of truth for the 22 catalog indicators.
The transform layer loads the catalog lazily inside
:func:`transform_vdem_observations` so the unified adapter
never imports legacy code at module level. The legacy
catalog path resolves through :data:`DEFAULT_CATALOG_PATH`
in :mod:`._catalog`.

Country filtering
-----------------

The V-Dem ``country_text_id`` column is the canonical V-Dem
country identifier (the COW code, e.g. ``MEX`` / ``USA`` /
``SWE``). The request ``countries=`` filter applies as an
exact match against ``country_text_id`` -- this is the
canonical contract documented in the brief. Downstream
Stage 3 country match resolves the V-Dem ``country_text_id``
to our canonical ISO3.
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
from ._transform import emit_vdem_observations


def transform_vdem_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
    *,
    catalog_path: Path | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the narrow raw frame into
    :class:`NormalizedObservation` records.

    Honors ``request.years`` and ``request.countries`` by
    filtering the narrow DataFrame after the legacy read
    (the legacy reader returns the full frame when called
    with ``year=None``; the new adapter owns the
    request-scoping logic). ``request.leaders`` is
    unsupported for a country-year political / governance
    source and surfaces a structured ``UNSUPPORTED_FILTER``
    warning per SRC-REQ-005 (the warning is surfaced on the
    readiness envelope; the transform does not re-emit
    per-row to avoid double-counting in the warnings audit
    trail). Out-of-coverage years (anything outside
    1789-2025) emit zero rows plus a structured
    ``YEAR_ABSENT`` warning per offending year (no
    stale-proxy fill per SRC-COV-002 / SRC-COV-003 -- the
    warning is surfaced on the readiness envelope; the
    transform narrows the narrow frame to the requested
    years and produces zero rows for the out-of-coverage
    case).

    The legacy indicator catalog is loaded lazily inside
    this function (NOT at module level) so the unified
    package boundary is preserved. The catalog path
    defaults to :data:`DEFAULT_CATALOG_PATH` but may be
    overridden via the ``catalog_path`` keyword argument for
    tests that stage a custom catalog.
    """
    if not isinstance(raw.payload, dict):
        raise ValueError(
            "VDemAdapter.transform: raw.payload must be a dict "
            "carrying the narrow DataFrame under 'narrow_df'."
        )
    narrow_df = raw.payload.get("narrow_df")
    if narrow_df is None:
        raise ValueError(
            "VDemAdapter.transform: raw.payload has no "
            "'narrow_df' key; read_raw must populate it."
        )
    metadata = raw.payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    # Apply the request year + country filters on the
    # narrow frame. The legacy narrow-format DataFrame has
    # integer ``year`` and string ``country_text_id``
    # columns. ``country_text_id`` is V-Dem's COW code (e.g.
    # ``MEX``); Stage 3 country match resolves it to our
    # canonical ISO3 later.
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
        # ``DataFrame.isin`` on the ``year`` column accepts
        # a set of ints; the resulting boolean mask filters
        # to the requested years. Out-of-coverage years are
        # still passed here (the readiness gate fires the
        # YEAR_ABSENT warning per offending year; the filter
        # then produces zero rows for them, matching the
        # readiness envelope's contract).
        filtered_df = filtered_df.loc[
            filtered_df["year"].astype(int).isin(years_set),
        ]
    if countries_arg:
        countries_set = set(countries_arg)
        filtered_df = filtered_df.loc[
            filtered_df["country_text_id"].astype(str).isin(
                countries_set,
            ),
        ]

    csv_path = raw.payload.get("csv_path")
    csv_path_value = (
        csv_path if isinstance(csv_path, Path) else None
    )

    # Lazy-load the legacy indicator catalog. The legacy
    # loader returns the canonical ``IndicatorSpec`` list
    # which the transform layer uses to drive the per-row
    # emission.
    specs = load_indicator_catalog(
        catalog_path=catalog_path or DEFAULT_CATALOG_PATH,
    )

    return emit_vdem_observations(
        filtered_df,
        request,
        csv_path_value,
        metadata,
        specs=specs,
    )


__all__ = ["transform_vdem_observations"]
