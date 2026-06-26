#!/usr/bin/env python3
# ruff: noqa: E501
"""Build the standalone `/reports/country-metrics-dashboard.html` page.

The page is a static HTML artifact: this script reads the local Superset-facing
SQLite extract and embeds the selected metric rows as JSON. The browser renders
the selector, cards, and SVG line charts from that embedded JSON; no backend is
called at page-view time.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/processed/viz/country-year-chronicle/superset_viz.sqlite"
DEFAULT_OUTPUT = PROJECT_ROOT / "infra/superset/reports/country-metrics-dashboard.html"


def _load_rows(db_path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    con = sqlite3.connect(db_path)
    try:
        metric_rows = con.execute(
            """
            select country_iso3, country_name, year, metric_id, value
            from viz_country_year_metrics
            where metric_id in (
                'chronicle.population',
                'chronicle.gdp',
                'chronicle.gdp_per_capita'
            )
              and value is not null
            order by country_name, year, metric_id
            """
        ).fetchall()
        latest_rows = con.execute(
            """
            select country_iso3, country_name, latest_year, latest_population,
                   latest_gdp, latest_gdp_per_capita, political_regime_bucket
            from viz_country_latest_metrics
            order by country_name
            """
        ).fetchall()
    finally:
        con.close()

    metrics = [
        {
            "country_iso3": country_iso3,
            "country_name": country_name,
            "year": year,
            "metric_id": metric_id,
            "value": value,
        }
        for country_iso3, country_name, year, metric_id, value in metric_rows
    ]
    latest = [
        {
            "country_iso3": country_iso3,
            "country_name": country_name,
            "latest_year": latest_year,
            "latest_population": latest_population,
            "latest_gdp": latest_gdp,
            "latest_gdp_per_capita": latest_gdp_per_capita,
            "political_regime_bucket": political_regime_bucket,
        }
        for (
            country_iso3,
            country_name,
            latest_year,
            latest_population,
            latest_gdp,
            latest_gdp_per_capita,
            political_regime_bucket,
        ) in latest_rows
    ]
    return metrics, latest


def _render_html(metrics: list[dict[str, object]], latest: list[dict[str, object]]) -> str:
    rows_json = json.dumps(metrics, separators=(",", ":"))
    latest_json = json.dumps(latest, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Country Metrics Dashboard</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; background: #f8fafc; color: #111827; }}
    header {{ background: linear-gradient(135deg, #111827, #1d4ed8); color: white; padding: 28px 36px; }}
    main {{ padding: 24px; max-width: 1180px; margin: auto; }}
    select {{ font-size: 16px; padding: 10px 12px; min-width: 300px; border-radius: 10px; border: 1px solid #cbd5e1; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 20px 0; }}
    .card, .chart {{ background: white; border: 1px solid #e5e7eb; border-radius: 16px; padding: 16px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(15, 23, 42, .05); }}
    .label {{ color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; }}
    .v {{ font-size: 24px; font-weight: 800; margin-top: 8px; }}
    svg {{ width: 100%; height: 300px; }}
    .axis {{ stroke: #94a3b8; }}
    .grid {{ stroke: #e5e7eb; }}
    .line {{ fill: none; stroke: #2563eb; stroke-width: 3; }}
    .dot {{ fill: #2563eb; }}
    .note {{ color: #64748b; }}
  </style>
</head>
<body>
  <header>
    <h1>CHOPS Workshop — Country Metrics</h1>
    <p>Select a country to view population, GDP, and GDP per capita over time.</p>
  </header>
  <main>
    <label><b>Country</b><br /><select id="country"></select></label>
    <section id="cards" class="cards"></section>
    <div class="chart"><h2>Population</h2><svg id="chronicle.population"></svg></div>
    <div class="chart"><h2>GDP</h2><svg id="chronicle.gdp"></svg></div>
    <div class="chart"><h2>GDP per capita</h2><svg id="chronicle.gdp_per_capita"></svg></div>
    <p class="note">Static dashboard generated from the local visualization SQLite extract.</p>
  </main>
  <script>
    const rows = {rows_json};
    const latest = {latest_json};
    function fmt(x) {{
      if (x == null) return 'n/a';
      return Intl.NumberFormat('en-US', {{ notation: Math.abs(x) >= 1e6 ? 'compact' : 'standard', maximumFractionDigits: 2 }}).format(x);
    }}
    const sel = document.getElementById('country');
    latest.forEach(c => {{
      const o = document.createElement('option');
      o.value = c.country_iso3;
      o.textContent = `${{c.country_name}} (${{c.country_iso3}})`;
      sel.appendChild(o);
    }});
    if (latest.some(c => c.country_iso3 === 'USA')) sel.value = 'USA';
    sel.onchange = render;
    function card(label, value) {{ return `<div class="card"><div class="label">${{label}}</div><div class="v">${{value}}</div></div>`; }}
    function cards() {{
      const c = latest.find(x => x.country_iso3 === sel.value) || {{}};
      document.getElementById('cards').innerHTML = card('Latest year', c.latest_year || 'n/a') + card('Population', fmt(c.latest_population)) + card('GDP', fmt(c.latest_gdp)) + card('GDP / capita', fmt(c.latest_gdp_per_capita)) + card('Regime bucket', c.political_regime_bucket || 'n/a');
    }}
    function draw(metric) {{
      const svg = document.getElementById(metric);
      svg.innerHTML = '';
      const pts = rows.filter(r => r.country_iso3 === sel.value && r.metric_id === metric).sort((a, b) => a.year - b.year);
      const W = 900, H = 300, m = {{ l: 72, r: 24, t: 18, b: 40 }};
      svg.setAttribute('viewBox', `0 0 ${{W}} ${{H}}`);
      if (!pts.length) {{ svg.innerHTML = '<text x="20" y="40">No data available</text>'; return; }}
      const ys = pts.map(p => p.value), xs = pts.map(p => p.year);
      const minY = Math.min(...ys), maxY = Math.max(...ys), minX = Math.min(...xs), maxX = Math.max(...xs);
      const sx = x => m.l + (x - minX) / (maxX - minX || 1) * (W - m.l - m.r);
      const sy = y => H - m.b - (y - minY) / (maxY - minY || 1) * (H - m.t - m.b);
      for (let i = 0; i <= 4; i++) {{
        const y = m.t + i * (H - m.t - m.b) / 4;
        svg.insertAdjacentHTML('beforeend', `<line class="grid" x1="${{m.l}}" y1="${{y}}" x2="${{W - m.r}}" y2="${{y}}"/>`);
      }}
      svg.insertAdjacentHTML('beforeend', `<line class="axis" x1="${{m.l}}" y1="${{H - m.b}}" x2="${{W - m.r}}" y2="${{H - m.b}}"/><line class="axis" x1="${{m.l}}" y1="${{m.t}}" x2="${{m.l}}" y2="${{H - m.b}}"/><text x="${{m.l}}" y="${{H - 10}}">${{minX}}</text><text x="${{W - m.r - 38}}" y="${{H - 10}}">${{maxX}}</text><text x="8" y="${{m.t + 8}}">${{fmt(maxY)}}</text><text x="8" y="${{H - m.b}}">${{fmt(minY)}}</text>`);
      const path = pts.map((p, i) => `${{i ? 'L' : 'M'}}${{sx(p.year).toFixed(1)}},${{sy(p.value).toFixed(1)}}`).join(' ');
      svg.insertAdjacentHTML('beforeend', `<path class="line" d="${{path}}"/>`);
      pts.forEach(p => svg.insertAdjacentHTML('beforeend', `<circle class="dot" cx="${{sx(p.year)}}" cy="${{sy(p.value)}}" r="3"><title>${{p.year}}: ${{fmt(p.value)}}</title></circle>`));
    }}
    function render() {{ cards(); draw('chronicle.population'); draw('chronicle.gdp'); draw('chronicle.gdp_per_capita'); }}
    render();
  </script>
</body>
</html>
"""


def main() -> None:
    if not DEFAULT_DB.exists():
        raise SystemExit(f"missing Superset SQLite artifact: {DEFAULT_DB}")
    metrics, latest = _load_rows(DEFAULT_DB)
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(_render_html(metrics, latest), encoding="utf-8")
    print(f"wrote {DEFAULT_OUTPUT} ({len(metrics)} metric rows, {len(latest)} countries)")


if __name__ == "__main__":
    main()
