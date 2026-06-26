"""Unified-source Transparency International CPI
transform-pipeline orchestration.

Owns the body of
:meth:`TransparencyCPIAdapter.transform` extracted into a
free function :func:`transform_transparency_cpi_observations`
so the adapter class module stays focused on lifecycle
wiring + registration. The function applies the request
year / country filters on the wide-format country-year
DataFrame returned by :mod:`._raw_read` and delegates
the per-row :class:`NormalizedObservation` emission to
:func:`emit_transparency_cpi_observations` in
:mod:`._transform`.

Split out of :mod:`.adapter` to keep the adapter class
focused on the lifecycle class + the protocol conformance
guard + the registration helpers while preserving the
documented end-to-end behaviour the reviewer gate
requires (every blocker surfaces a structured
:class:`SourceWarning`).

Lazy catalog loading
--------------------

The legacy
:func:`leaders_db.ingest.transparency_cpi_io.load_indicator_catalog`
is the single source of truth for the single catalog
indicator (``cpi_score``). The transform layer loads the
catalog lazily inside
:func:`transform_transparency_cpi_observations` so the
unified adapter never imports legacy code at module
level. The legacy catalog path resolves through
:data:`DEFAULT_CATALOG_PATH` in :mod:`._catalog`.

Country filtering
-----------------

The CPI ``iso3`` column is the canonical ISO3 alpha-3
country code (e.g. ``MEX`` / ``USA`` / ``SWE``). The
request ``countries=`` filter applies as an exact match
against the CPI ``iso3`` column -- this is the canonical
contract documented in the brief. Passing a non-ISO3
code (e.g. ``"United States"``) yields zero rows; the
readiness gate does NOT warn on non-ISO3 codes because
the contract is documented-and-tested rather than
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
from ._raw_read import _csv_path
from ._transform import emit_transparency_cpi_observations


def transform_transparency_cpi_observations(
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
    called with ``year=Y``; the new adapter owns the
    request-scoping logic). ``request.leaders`` is
    unsupported for a country-year corruption-perception
    source and surfaces a structured
    ``UNSUPPORTED_FILTER`` warning per SRC-REQ-005 (the
    warning is surfaced on the readiness envelope; the
    transform does not re-emit per-row to avoid
    double-counting in the warnings audit trail).
    Out-of-coverage years (anything outside 1995-2023)
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
            "TransparencyCPIAdapter.transform: raw.payload "
            "must be a dict carrying the wide DataFrame "
            "under 'wide_df'."
        )
    wide_df = raw.payload.get("wide_df")
    if wide_df is None:
        raise ValueError(
            "TransparencyCPIAdapter.transform: raw.payload "
            "has no 'wide_df' key; read_raw must populate "
            "it."
        )
    metadata = raw.payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    # Apply the request year + country filters on the
    # wide frame. The legacy wide-format DataFrame has
    # integer ``year`` and string ``iso3`` columns. The
    # ``iso3`` is the canonical ISO3 alpha-3 country
    # code (e.g. ``MEX``); the unified transform
    # surfaces it verbatim on the observation
    # ``country_code`` field. Downstream Stage 3 country
    # match resolves ISO3 to our canonical ISO3 (the
    # same string in this case).
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
        # ``DataFrame.isin`` on the ``year`` column
        # accepts a set of ints; the resulting boolean
        # mask filters to the requested years.
        # Out-of-coverage years are still passed here
        # (the readiness gate fires the ``YEAR_ABSENT``
        # warning per offending year; the filter then
        # produces zero rows for them, matching the
        # readiness envelope's contract).
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

    csv_path = raw.payload.get("csv_path")
    csv_path_value = (
        csv_path if isinstance(csv_path, Path) else None
    )
    # The CSV path is also derivable from the request
    # payload via the ``_csv_path`` helper -- prefer the
    # staged one if it carries through, fall back to the
    # helper-derived path when the raw payload does not.
    if csv_path_value is None:
        csv_path_value = _csv_path(request)

    # Annotate the metadata payload with the canonical
    # raw year so the transform layer can build the
    # per-year raw asset id without re-resolving the
    # request scope. The CPI unified adapter always
    # reads the canonical 2023 CSV (the staged bundle's
    # only CSV); the request's ``years=`` filter is
    # honored by the transform layer (which narrows the
    # wide frame after the legacy read). The helper
    # keeps the transform layer isolated from the
    # raw-read year's identity.
    raw_year = raw.payload.get("year")
    if isinstance(raw_year, int):
        metadata_for_transform = dict(metadata)
        metadata_for_transform["raw_year"] = int(raw_year)
    else:
        metadata_for_transform = dict(metadata)
        metadata_for_transform["raw_year"] = 2023

    # Lazy-load the legacy indicator catalog. The legacy
    # loader returns the canonical ``IndicatorSpec`` list
    # which the transform layer uses to drive the
    # per-row emission.
    specs = load_indicator_catalog(
        catalog_path=catalog_path or DEFAULT_CATALOG_PATH,
    )

    return emit_transparency_cpi_observations(
        filtered_df,
        request,
        csv_path_value,
        metadata_for_transform,
        specs=specs,
    )


__all__ = ["transform_transparency_cpi_observations"]
