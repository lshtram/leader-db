"""Low-level SVG primitives for the investigation-slice line chart.

This module owns the dependency-free SVG building blocks:

- layout constants (viewBox, margins, axis dimensions),
- a small deterministic colour palette so successive renders of the
  same input produce the same colours,
- coordinate-encoder helpers that map a domain value (year, numeric
  value) to an SVG viewBox coordinate,
- the SVG header / axes / grid fragment helpers,
- a thin HTML document wrapper and a deterministic axis-label number
  formatter.

The high-level orchestration (series grouping, legend rendering, public
entry point) lives in :mod:`._html`. Keeping the low-level primitives
in their own module lets :mod:`._html` stay close to the 400-line
convention while every helper remains independently testable.
"""

from __future__ import annotations

import html as _html_stdlib
from collections.abc import Callable, Sequence

# Coordinate-encoder protocol: maps a domain value (year or numeric
# value) to an SVG viewBox coordinate. ``_render_svg`` (in :mod:`._html`)
# builds two of these -- one for the X axis, one for the Y axis -- and
# passes them to :func:`_html._svg_series_and_legend`. The aliases make
# the signature self-documenting without re-introducing ``typing.Any``
# for callback parameters.
_XEncoder = Callable[[int], float]
_YEncoder = Callable[[float], float]


def _x_encoder(
    year: int, *, min_year: int, year_span: int, plot_width: float,
) -> float:
    """Map a year to the SVG X coordinate for the given axis bounds."""
    return _SVG_MARGIN_LEFT + (year - min_year) / year_span * plot_width


def _y_encoder(
    value: float, *, min_value: float, value_span: float, plot_height: float,
) -> float:
    """Map a numeric value to the SVG Y coordinate for the given axis bounds."""
    return _SVG_MARGIN_TOP + plot_height - (
        (value - min_value) / value_span * plot_height
    )


# A small palette so the deterministic graph has stable colours.
_DETERMINISTIC_PALETTE: tuple[str, ...] = (
    "#1f77b4",  # blue
    "#ff7f0e",  # orange
    "#2ca02c",  # green
    "#d62728",  # red
    "#9467bd",  # purple
    "#8c564b",  # brown
    "#e377c2",  # pink
    "#7f7f7f",  # grey
    "#bcbd22",  # olive
    "#17becf",  # cyan
)


# SVG layout constants -- shared by every chart so the resulting
# pixel coordinates are stable across runs.
_SVG_WIDTH = 960
_SVG_HEIGHT = 480
_SVG_MARGIN_LEFT = 80
_SVG_MARGIN_RIGHT = 30
_SVG_MARGIN_TOP = 50
_SVG_MARGIN_BOTTOM = 60


def _svg_header(*, title: str) -> str:
    """Return the SVG opening tag + style block + title text."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_SVG_WIDTH} {_SVG_HEIGHT}" '
        f'width="{_SVG_WIDTH}" height="{_SVG_HEIGHT}" '
        f'role="img" aria-label="{_html_stdlib.escape(title)}">'
        '<style>'
        'text { font-family: sans-serif; font-size: 12px; fill: #222; }'
        '.axis { stroke: #444; stroke-width: 1; fill: none; }'
        '.grid { stroke: #ddd; stroke-width: 0.5; }'
        '.label { font-weight: 600; }'
        '</style>'
        f'<text x="{_SVG_WIDTH / 2}" y="25" text-anchor="middle" '
        f'class="label">{_html_stdlib.escape(title)}</text>'
    )


def _svg_axes_and_grid(
    *,
    plot_width: float,
    plot_height: float,
    min_year: int,
    max_year: int,
    min_value: float,
    value_span: float,
) -> str:
    """Return the SVG axes + horizontal grid + x-axis ticks."""
    parts: list[str] = []
    # Vertical and horizontal axis lines.
    parts.append(
        f'<line class="axis" x1="{_SVG_MARGIN_LEFT}" y1="{_SVG_MARGIN_TOP}" '
        f'x2="{_SVG_MARGIN_LEFT}" y2="{_SVG_MARGIN_TOP + plot_height}"/>'
    )
    parts.append(
        f'<line class="axis" x1="{_SVG_MARGIN_LEFT}" '
        f'y1="{_SVG_MARGIN_TOP + plot_height}" '
        f'x2="{_SVG_MARGIN_LEFT + plot_width}" '
        f'y2="{_SVG_MARGIN_TOP + plot_height}"/>'
    )
    # Five horizontal grid lines.
    for i in range(1, 5):
        ratio = i / 5
        gy = _SVG_MARGIN_TOP + plot_height - ratio * plot_height
        parts.append(
            f'<line class="grid" x1="{_SVG_MARGIN_LEFT}" y1="{gy}" '
            f'x2="{_SVG_MARGIN_LEFT + plot_width}" y2="{gy}"/>'
        )
        label_value = min_value + ratio * value_span
        parts.append(
            f'<text x="{_SVG_MARGIN_LEFT - 6}" y="{gy + 4}" '
            f'text-anchor="end">{_format_number(label_value)}</text>'
        )
    # X-axis tick marks (6 evenly spaced).
    for i in range(6):
        year = min_year + round(i * (max_year - min_year) / 5)
        year = min(year, max_year)
        tx = (
            _SVG_MARGIN_LEFT
            + (year - min_year) / max(1, max_year - min_year) * plot_width
        )
        parts.append(
            f'<line class="grid" x1="{tx}" y1="{_SVG_MARGIN_TOP}" '
            f'x2="{tx}" y2="{_SVG_MARGIN_TOP + plot_height}"/>'
        )
        parts.append(
            f'<text x="{tx}" y="{_SVG_MARGIN_TOP + plot_height + 18}" '
            f'text-anchor="middle">{year}</text>'
        )
    return "".join(parts)


def _wrap_html_document(
    *, title: str, body_parts: Sequence[str],
) -> str:
    """Wrap ``body_parts`` in a minimal HTML document.

    The legend is rendered as plain HTML below the SVG so arbitrarily
    long ``(country, source, indicator)`` labels fit without being
    clipped by the SVG viewBox. The SVG fragment is concatenated
    alongside the legend ``body_parts`` in the order supplied.
    """
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{_html_stdlib.escape(title)}</title>\n"
        '<style>'
        '.legend { font-family: sans-serif; font-size: 12px; '
        'margin-top: 12px; }'
        '.legend-entry { display: inline-block; margin-right: 16px; '
        'white-space: nowrap; }'
        '.legend-swatch { display: inline-block; width: 10px; '
        'height: 10px; margin-right: 6px; vertical-align: middle; }'
        '</style>\n'
        "</head>\n"
        "<body>\n"
        + "\n".join(body_parts)
        + "\n</body>\n</html>\n"
    )


def _format_number(value: float) -> str:
    """Render ``value`` for SVG axis labels (compact, deterministic)."""
    if abs(value) >= 1_000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


__all__ = [
    "_DETERMINISTIC_PALETTE",
    "_SVG_HEIGHT",
    "_SVG_MARGIN_BOTTOM",
    "_SVG_MARGIN_LEFT",
    "_SVG_MARGIN_RIGHT",
    "_SVG_MARGIN_TOP",
    "_SVG_WIDTH",
    "_XEncoder",
    "_YEncoder",
    "_format_number",
    "_svg_axes_and_grid",
    "_svg_header",
    "_wrap_html_document",
    "_x_encoder",
    "_y_encoder",
]
