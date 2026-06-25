"""Deterministic dependency-free HTML+SVG line chart for the slice.

The chart groups :class:`ConceptObservation` rows by the
``(country_code, source_slug, series_label)`` tuple so the same
country/source never gets multiple series-identifier values joined
into a single polyline -- each polyline is one indicator/recipe
series for one source and one country, and its legend label renders
as ``"{country_code} \u00b7 {source_slug} \u00b7 {series_label}"``
so the indicator / recipe is visible to the reader.

The ``series_label`` is the recipe key for derived concept rows (e.g.
PWT's ``pwt_gdp_per_capita_via_rgdpo_over_pop``) and the
source-specific indicator code for direct concept rows (e.g. WDI's
``wdi_gdp_per_capita`` and ``wdi_gdp_per_capita_ppp_constant_2017``).
Including the third key element is required because a single source
can expose multiple indicator codes for the same concept (WDI
publishes GDP per capita in current USD and PPP constant 2017 intl
$); without it the chart would chain distinct scales into a single
misleading polyline.

Coordinates are computed in the local SVG viewBox so the SVG is
pixel-deterministic for any given input -- the same set of
``concept_rows`` always produces the same pixel positions.

The low-level SVG primitives (layout constants, palette, coordinate
encoders, axes/grid, HTML wrapper) live in :mod:`._html_svg` so this
module can stay close to the 400-line convention while keeping the
high-level orchestration (key construction, ordering, range
computation, polyline rendering, legend rendering) cohesive.
"""

from __future__ import annotations

import html as _html_stdlib
from collections.abc import Mapping, Sequence
from pathlib import Path

from ...sources.concepts import ConceptObservation
from ._html_svg import (
    _DETERMINISTIC_PALETTE,
    _SVG_HEIGHT,
    _SVG_MARGIN_BOTTOM,
    _SVG_MARGIN_LEFT,
    _SVG_MARGIN_RIGHT,
    _SVG_MARGIN_TOP,
    _SVG_WIDTH,
    _svg_axes_and_grid,
    _svg_header,
    _wrap_html_document,
    _x_encoder,
    _XEncoder,
    _y_encoder,
    _YEncoder,
)

# Stable key for one SVG series: ``(country_code, source_slug,
# series_label)``. We key by slug strings (not the :class:`SourceId`
# instance) so the dict round-trips through JSON / set comparisons
# deterministically. ``series_label`` distinguishes indicators for the
# same source (WDI direct) or names the recipe for derived rows
# (PWT); see :func:`_series_label_for_row`.
SeriesKey = tuple[str, str, str]


def _series_label_for_row(row: ConceptObservation) -> str:
    """Return a stable per-row series label for grouping + legend text.

    Derived rows (PWT ``gdp_per_capita = rgdpo / pop``) carry no single
    source indicator code; their :attr:`recipe_key` is the stable
    identifier of the derivation that produced the row. Direct rows
    (WDI, Maddison) carry one or more source indicator codes; the
    first code is the canonical alias for the concept on that source
    (the catalog publishes the codes in a stable order).

    The fallback ``"unknown"`` only fires for a malformed concept row
    that has neither a recipe key nor any source indicator codes; the
    concept catalog never emits such a row in practice.
    """
    if row.recipe_key:
        return row.recipe_key
    if row.source_indicator_codes:
        return row.source_indicator_codes[0]
    return "unknown"


def write_static_line_chart(
    *,
    html_path: Path,
    title: str,
    concept_rows: Sequence[ConceptObservation],
    countries: Sequence[str],
) -> None:
    """Render a dependency-free HTML+SVG line chart of ``concept_rows``.

    The chart groups rows by ``(country_code, source_slug,
    series_label)`` and plots one polyline per group. The
    ``series_label`` distinguishes indicators for the same source
    (WDI direct: current USD vs. PPP constant 2017) or names the
    recipe for derived rows (PWT: ``gdp_per_capita_via_rgdpo_over_pop``),
    so values from different indicator codes / recipes for the same
    country/year/source are NEVER joined into a single polyline --
    that would falsely imply a time series that does not exist in the
    data. Legend labels render as
    ``"{country_code} \u00b7 {source_slug} \u00b7 {series_label}"``
    so the indicator / recipe is visible. Coordinates are computed in
    the local SVG viewBox so the SVG is pixel-deterministic for any
    given input -- the same set of ``concept_rows`` always produces
    the same pixel positions.
    """
    by_series = _group_rows_by_series_key(concept_rows)
    ordered_series = _ordered_series_list(countries, by_series)
    year_range = _compute_year_range(by_series)
    value_range = _compute_value_range(concept_rows)
    if year_range is None or value_range is None:
        html_path.write_text(
            "<!doctype html><html><body><h1>No data</h1></body></html>",
            encoding="utf-8",
        )
        return
    min_year, max_year = year_range
    min_value, max_value = value_range
    svg_parts = _render_svg(
        title=title,
        by_series=by_series,
        ordered_series=ordered_series,
        min_year=min_year,
        max_year=max_year,
        min_value=min_value,
        max_value=max_value,
    )
    legend_html = _render_legend_html(
        ordered_series=ordered_series, by_series=by_series,
    )
    html_path.write_text(
        _wrap_html_document(title=title, body_parts=[*svg_parts, legend_html]),
        encoding="utf-8",
    )


def _group_rows_by_series_key(
    concept_rows: Sequence[ConceptObservation],
) -> dict[SeriesKey, list[ConceptObservation]]:
    """Return ``{(country, source_slug, series_label): [rows]}`` for usable rows.

    The key includes the source slug AND the per-row series label
    (indicator code for direct rows, recipe key for derived rows) so
    each polyline carries exactly one source's series for one country
    and one indicator/recipe. Rows with ``None`` value or year are
    filtered out.
    """
    by_key: dict[SeriesKey, list[ConceptObservation]] = {}
    for row in concept_rows:
        if row.value is None or row.year is None:
            continue
        country_code = row.country_code or "?"
        source_slug = row.source_id.slug if row.source_id else "?"
        series_label = _series_label_for_row(row)
        by_key.setdefault(
            (country_code, source_slug, series_label), [],
        ).append(row)
    return by_key


def _ordered_series_list(
    requested: Sequence[str],
    by_series: Mapping[SeriesKey, Sequence[ConceptObservation]],
) -> list[SeriesKey]:
    """Return a stable ``(country, source, series_label)`` series order.

    Order rules:

    1. Requested countries first, in the order the caller asked for.
    2. Within each country, sources are sorted alphabetically by
       their slug so the per-country ordering is deterministic.
    3. Within each ``(country, source)``, series labels are sorted
       alphabetically so the per-source ordering is deterministic
       and the WDI direct + PPP constant 2017 pair land in a stable
       order across runs.
    4. Any ``(country, source, series_label)`` triple not covered by
       the requested list is appended in lexicographic order so the
       result is fully deterministic across runs.
    """
    ordered: list[SeriesKey] = []
    seen: set[SeriesKey] = set()
    for code in requested:
        for source_slug in sorted({k[1] for k in by_series if k[0] == code}):
            for series_label in sorted(
                k[2]
                for k in by_series
                if k[0] == code and k[1] == source_slug
            ):
                key = (code, source_slug, series_label)
                if key not in seen:
                    ordered.append(key)
                    seen.add(key)
    # Trailing extras (countries outside the requested list), in full
    # lex order so the result is fully deterministic.
    for key in sorted(by_series):
        if key not in seen:
            ordered.append(key)
            seen.add(key)
    return ordered


def _compute_year_range(
    by_series: Mapping[SeriesKey, Sequence[ConceptObservation]],
) -> tuple[int, int] | None:
    """Return ``(min_year, max_year)`` across all rows, or ``None`` when empty."""
    years: set[int] = set()
    for rows in by_series.values():
        for row in rows:
            if row.year is not None:
                years.add(row.year)
    if not years:
        return None
    sorted_years = sorted(years)
    return sorted_years[0], sorted_years[-1]


def _compute_value_range(
    concept_rows: Sequence[ConceptObservation],
) -> tuple[float, float] | None:
    """Return ``(min_value, max_value)`` across all rows, or ``None`` when empty."""
    all_values = [
        float(row.value) for row in concept_rows if row.value is not None
    ]
    if not all_values:
        return None
    return min(all_values), max(all_values)


def _render_svg(
    *,
    title: str,
    by_series: Mapping[SeriesKey, Sequence[ConceptObservation]],
    ordered_series: Sequence[SeriesKey],
    min_year: int,
    max_year: int,
    min_value: float,
    max_value: float,
) -> list[str]:
    """Render the inner SVG fragments as a list of strings."""
    plot_width = _SVG_WIDTH - _SVG_MARGIN_LEFT - _SVG_MARGIN_RIGHT
    plot_height = _SVG_HEIGHT - _SVG_MARGIN_TOP - _SVG_MARGIN_BOTTOM
    year_span = max(1, max_year - min_year)
    value_span = max(1e-9, max_value - min_value)

    def _x(year: int) -> float:
        return _x_encoder(
            year,
            min_year=min_year,
            year_span=year_span,
            plot_width=plot_width,
        )

    def _y(value: float) -> float:
        return _y_encoder(
            value,
            min_value=min_value,
            value_span=value_span,
            plot_height=plot_height,
        )

    parts: list[str] = []
    parts.append(_svg_header(title=title))
    parts.append(
        _svg_axes_and_grid(
            plot_width=plot_width,
            plot_height=plot_height,
            min_year=min_year,
            max_year=max_year,
            min_value=min_value,
            value_span=value_span,
        )
    )
    parts.append(
        _svg_polylines(
            by_series=by_series,
            ordered_series=ordered_series,
            x=_x,
            y=_y,
        )
    )
    parts.append("</svg>")
    return parts


def _svg_polylines(
    *,
    by_series: Mapping[SeriesKey, Sequence[ConceptObservation]],
    ordered_series: Sequence[SeriesKey],
    x: _XEncoder,
    y: _YEncoder,
) -> str:
    """Return one polyline per ``(country, source, series_label)`` series.

    Each polyline contains ONLY the rows for one
    ``(country, source, series_label)`` triple, so values from
    different indicators / recipes for the same country/source are
    never chained into a single line. The polyline carries
    ``data-country``, ``data-source``, and ``data-indicator``
    attributes so downstream tooling (and tests) can identify the
    series unambiguously; ``data-indicator`` is the same string
    used in the legend label.
    """
    parts: list[str] = []
    for index, (country, source_slug, series_label) in enumerate(ordered_series):
        rows = sorted(
            by_series.get((country, source_slug, series_label), []),
            key=lambda r: r.year if r.year is not None else 0,
        )
        if not rows:
            continue
        colour = _DETERMINISTIC_PALETTE[
            index % len(_DETERMINISTIC_PALETTE)
        ]
        points: list[str] = []
        for row in rows:
            if row.value is None or row.year is None:
                continue
            points.append(f"{x(row.year):.2f},{y(float(row.value)):.2f}")
        parts.append(
            f'<polyline fill="none" stroke="{colour}" '
            f'stroke-width="2" '
            f'data-country="{_html_stdlib.escape(country)}" '
            f'data-source="{_html_stdlib.escape(source_slug)}" '
            f'data-indicator="{_html_stdlib.escape(series_label)}" '
            f'points="{" ".join(points)}"/>'
        )
    return "".join(parts)


def _render_legend_html(
    *,
    ordered_series: Sequence[SeriesKey],
    by_series: Mapping[SeriesKey, Sequence[ConceptObservation]],
) -> str:
    """Return the legend as plain HTML below the SVG.

    The legend lives outside the SVG so arbitrarily long
    ``(country, source, series_label)`` labels (e.g.
    ``USA \u00b7 world_bank_wdi \u00b7 wdi_gdp_per_capita_ppp_constant_2017``)
    fit without being clipped by the SVG viewBox. Each entry is a
    ``<span class="legend-entry">`` carrying the colour swatch and
    the label text; entries are emitted in the same order as the
    polylines so the legend mirrors the series order.
    """
    parts: list[str] = ['<div class="legend">']
    for index, (country, source_slug, series_label) in enumerate(ordered_series):
        if (country, source_slug, series_label) not in by_series:
            continue
        colour = _DETERMINISTIC_PALETTE[
            index % len(_DETERMINISTIC_PALETTE)
        ]
        label = (
            f"{country} \u00b7 {source_slug} \u00b7 {series_label}"
        )
        parts.append(
            f'<span class="legend-entry">'
            f'<span class="legend-swatch" '
            f'style="background:{_html_stdlib.escape(colour)};"></span>'
            f'{_html_stdlib.escape(label)}'
            f'</span>'
        )
    parts.append('</div>')
    return "".join(parts)


__all__ = [
    "SeriesKey",
    "write_static_line_chart",
]
