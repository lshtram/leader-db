"""World Bank WDI transform pipeline (``transform`` body).

Owns the body of :meth:`WDIAdapter.transform` extracted into
a free function :func:`transform_world_bank_wdi_observations`
so the adapter class module stays focused on lifecycle wiring
+ registration. The function applies the request year +
country filters on the wide-format DataFrame returned by
:func:`read_world_bank_wdi_cache`, resolves the catalog spec
mapping, pre-computes the ``(year, raw_indicator_code) ->
{countryiso3code: numeric_index}`` cache index map, and
delegates to :func:`emit_world_bank_wdi_observations` for
the actual :class:`NormalizedObservation` build loop.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi.adapter`
so the adapter class file stays under the 400-line
convention while preserving the same end-to-end behaviour
the reviewer gate requires (year/country filters honored,
``/1/<numeric_index>`` pointers resolved, no silent
stale-proxy fill).

Behavior contract
-----------------

Honors ``request.years`` and ``request.countries`` by
filtering the wide-format DataFrame after the cache-only
read returns the full frame (the local read returns the
full frame when called with ``years=None``; the new
adapter owns the request-scoping logic). ``request.years=``
outside the documented 1960+ coverage envelope emits zero
observations (no stale-proxy fill); the readiness envelope
already surfaced the ``YEAR_ABSENT`` warning per offending
year.

Pre-computes a ``(year, raw_indicator_code) ->
{countryiso3code: numeric_index}`` map by reading each
cache file once via :func:`load_wdi_cache_index`. The map
lets the transform layer stamp each emitted observation's
``raw_locator.json_pointer`` with a real
``/1/<numeric_index>`` value so audit code can resolve the
pointer to the underlying cache record byte-for-byte (per
``docs/requirements/sources.md`` §6 SRC-PROV-001).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawReadResult,
    SourceIngestRequest,
)

from ._paths import _resolve_spec_by_variable_name
from ._transform import (
    emit_world_bank_wdi_observations,
    load_wdi_cache_index,
)


def transform_world_bank_wdi_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    """Convert the wide raw frame into
    :class:`NormalizedObservation` records. See the module
    docstring for the full behavior contract.
    """
    if not isinstance(raw.payload, dict):
        raise ValueError(
            "WDIAdapter.transform: raw.payload must be a "
            "dict carrying the wide DataFrame under 'wide_df'."
        )
    wide_df = raw.payload.get("wide_df")
    if wide_df is None:
        raise ValueError(
            "WDIAdapter.transform: raw.payload has no "
            "'wide_df' key; read_raw must populate it."
        )
    cache_root = raw.payload.get("cache_root")
    cache_root_value = (
        cache_root if isinstance(cache_root, Path) else None
    )

    # Apply the request year + country filters on the wide
    # frame. The wide frame has integer ``year`` and string
    # ``iso3`` columns.
    years_arg: tuple[int, ...] | None = (
        tuple(int(y) for y in request.years)
        if request.years else None
    )
    countries_arg: tuple[str, ...] | None = (
        tuple(str(c) for c in request.countries)
        if request.countries else None
    )

    filtered_df = wide_df
    if years_arg is not None:
        # Honor the documented 1960+ coverage envelope:
        # years outside the envelope are dropped silently
        # (the readiness envelope already surfaced the
        # YEAR_ABSENT warning). When the caller asked for
        # only out-of-coverage years, the filtered frame is
        # empty so we emit zero observations (no stale-proxy
        # fill per SRC-COV-003).
        in_coverage = [
            y for y in years_arg
            if y >= 1960
        ]
        if not in_coverage:
            filtered_df = filtered_df.iloc[0:0]
        else:
            filtered_df = filtered_df.loc[
                filtered_df["year"].astype(int).isin(in_coverage),
            ]
    if countries_arg:
        country_set = set(countries_arg)
        filtered_df = filtered_df.loc[
            filtered_df["iso3"].astype(str).isin(country_set),
        ]

    # Resolve the catalog spec mapping (variable_name ->
    # IndicatorSpec). The catalog loader returns the
    # canonical 14-indicator set; missing specs (e.g. for
    # forward-compatible catalog additions) fall back to the
    # economic-family default + the default unit hint inside
    # ``emit_world_bank_wdi_observations``.
    spec_by_variable_name = _resolve_spec_by_variable_name(
        catalog_path=None,
    )

    # Pre-compute the (year, raw_indicator_code) cache index
    # map so the transform can stamp each observation with a
    # real ``/1/<numeric_index>`` JSON pointer. We enumerate
    # the (year, indicator) pairs that survive the filter; for
    # every pair we look up the catalog ``raw_column`` (the
    # WDI v2 indicator code) and load the cache file once.
    # Missing / malformed cache files yield ``None`` so the
    # transform falls back to the documented ``/1/{iso3}``
    # placeholder pointer (no silent corruption of the audit
    # envelope).
    cache_index_by_year_indicator: dict[
        tuple[int, str], dict[str, int] | None
    ] = {}
    if (
        isinstance(cache_root_value, Path)
        and not filtered_df.empty
    ):
        for column_name in filtered_df.columns:
            if column_name in {"iso3", "year"}:
                continue
            spec = spec_by_variable_name.get(column_name)
            raw_indicator_code = (
                getattr(spec, "raw_column", None) or column_name
            )
            for year_int in (
                int(y) for y in filtered_df["year"].unique()
            ):
                key = (year_int, raw_indicator_code)
                if key in cache_index_by_year_indicator:
                    continue
                cache_file = (
                    cache_root_value
                    / str(year_int)
                    / f"{raw_indicator_code}.json"
                )
                cache_index_by_year_indicator[key] = (
                    load_wdi_cache_index(cache_file)
                )

    return emit_world_bank_wdi_observations(
        filtered_df, request, cache_root_value,
        spec_by_variable_name,
        cache_index_by_year_indicator=(
            cache_index_by_year_indicator
            if cache_index_by_year_indicator
            else None
        ),
    )


__all__ = ["transform_world_bank_wdi_observations"]
