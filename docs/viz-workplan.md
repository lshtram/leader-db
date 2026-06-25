# Visualization Workplan

## Purpose

Build a visualization layer for `leaders-db` that supports both:

1. **Human access** — a client-facing browser interface for changing metric,
   country, date range, filters, grouping, and chart type.
2. **Agent/programmatic access** — Python/CLI/query specs, so agents never need
   to operate Superset's UI.

## Architecture decision

Use a hybrid architecture:

```text
leaders-db data lake / database
        ↓
leaders_db.viz semantic query + metrics layer
        ↓
core analytic facts + optional cached query outputs
        ↓
Apache Superset for human dashboards
        ↓
Cloudflare Tunnel + Cloudflare Access for client access
```

Superset is the human visualization surface. `leaders_db.viz` owns metric
contracts, transformations, filters, provenance, attribution, and query logic.
Superset consumes prepared outputs; it must not own official scoring,
confidence, source-precedence, or client-matrix logic.

## Deployment decisions

- Domain/subdomain: `viz.chopsworkshop.com`.
- DNS: `chopsworkshop.com` is already managed by Cloudflare.
- Access mode: ongoing client access.
- Client authentication: Cloudflare Access email OTP allowlist first.
- Initial host: this local machine will run Superset and `cloudflared`.
- Vercel is not the first deployment target for Superset because Superset is a
  stateful Python app; it may make sense later for a custom static/Next.js
  frontend.
- Client scope: broad exploration is desired, but not admin access, source-data
  mutation, analytic database writes, or secret access. SQL Lab / Explore access
  may be enabled only against read-only analytic views after least-privilege
  roles are verified.

## Core design principle

The core abstraction is:

1. `viz_country_year_metrics` — long-form country-year metric facts.
2. `viz_metric_catalog` — metric metadata, units, aggregation/transform rules,
   attribution keys, and policy metadata.
3. The semantic query layer — derives user-requested comparisons, filters,
   aggregations, and chart-ready tables from those core facts.

Specific outputs such as `viz_regime_year_population` are **cached/materialized
example queries**, not the pattern for every future question. They may exist when
useful for performance, dashboard stability, or proof surfaces, but new user
questions should generally be expressed through generic queries over the core
facts.

## Increment 1 — semantic query design

Status: **complete / reviewed 2026-06-22**

Completed:

- `leaders_db.viz` package skeleton.
- Pydantic query-spec models and validation.
- Metric registry seed.
- Read-only output contract with provenance, attribution, coverage, confidence,
  missingness, and separate client/system/final score fields.
- Tests for validation and client-matrix reference-only rules.

## Increment 2 — first analytic views/tables

Status: **complete / reviewed 2026-06-22**

Completed:

- Core tables:
  - `viz_country_year_metrics`
  - `viz_metric_catalog`
- Helper/cached tables:
  - `viz_regime_year_population` — cached example/proof query for population by
    year and regime bucket.
  - `viz_source_coverage` — audit/helper table for source coverage.
- Initial metrics: population, GDP, GDP per capita, political regime bucket, and
  existence status.
- Deterministic CSV export under:

```text
data/processed/viz/country-year-chronicle/
```

Implemented CSV outputs:

```text
viz_country_year_metrics.csv
viz_metric_catalog.csv
viz_regime_year_population.csv
viz_source_coverage.csv
```

The builder is pure/read-only: it accepts detailed Chronicle rows plus a
`CountryScopeEntry` mapping and returns in-memory dataframes. The writer emits
deterministic CSV files atomically. Parquet remains deferred until needed by a
consumer; CSV is sufficient for the first Superset/local-agent handoff.

## Increment 3 — generic agent access CLI

Status: **complete / implemented 2026-06-23; pending independent reviewer pass**

Primary goal: expose the generic query path, not more bespoke tables.

Planned commands:

- `leaders-db viz-query --spec ... --output csv`
- `leaders-db viz-metrics`

Implemented Increment 3 behavior:

- `leaders-db viz-metrics` lists the seed semantic metric registry for humans and
  agents (`--output table`, or `--output json` for machine-readable metadata).
- `leaders-db viz-query --spec <json> --output csv` executes the documented
  compact query spec against `viz_country_year_metrics.csv` and prints CSV to
  stdout.
- `leaders-db viz-query --spec <json> --output <path.csv>` writes the same
  generic query result to a file.
- `--data-dir <dir>` lets tests or agents point at a specific directory
  containing `viz_country_year_metrics.csv`; the default remains
  `data/processed/viz/country-year-chronicle/` under the project root.

Example generic query that should produce the same kind of result as the cached
`viz_regime_year_population` table:

```json
{
  "metric": "chronicle.population",
  "group_by": ["year", "political_regime_bucket"],
  "aggregation": "sum",
  "filters": {"existence_status": "exists"}
}
```

## Increment 4 — local Superset integration

Status: **complete / reviewed 2026-06-23**

- Docker Compose or documented local setup for Superset.
- Superset connects only to a read-only analytic database/view layer.
- First dashboard set: country metric over time, compare metrics over time,
  population by regime bucket, YoY growth by regime bucket, provenance table.

Implemented local integration artifacts:

- `infra/superset/docker-compose.yml` runs local Superset on
  `127.0.0.1:8088` with Postgres metadata storage and Redis cache.
- `infra/superset/superset.env.template` documents required local secrets;
  `infra/superset/superset.env` is gitignored.
- `infra/superset/superset_config.py` keeps `DEBUG=False`, reads secrets from
  the local env file, and avoids committed credentials.
- `leaders-db viz-build-superset-db` builds the derived analytic SQLite file
  `superset_viz.sqlite` from the deterministic CSV exports.
- The compose file mounts `data/processed/viz/country-year-chronicle` into the
  Superset container as `/leaders-db-viz:ro`; the Superset database connection
  URI is `sqlite:////leaders-db-viz/superset_viz.sqlite`.
- Manual and automated checks are documented in
  `docs/testing-guide-viz-superset.md`.

## Increment 5 — secure client access

Status: **implemented as safe activation package 2026-06-23; pending live Cloudflare credentials/email allowlist**

- Cloudflare Tunnel route from `viz.chopsworkshop.com` to local Superset.
- Cloudflare Access policy with explicit email allowlist.
- Superset hardening: HTTPS through Cloudflare, strong local secret, no default
  credentials, `DEBUG=False`, secure sessions where applicable, read-only DB.

Implemented safe activation artifacts:

- `infra/cloudflare/docker-compose.yml` runs `cloudflared` without publishing any
  inbound ports and expects a tunnel token from an ignored env file.
- `infra/cloudflare/cloudflared.env.template` documents the required local
  `TUNNEL_TOKEN`; the copied `cloudflared.env` is gitignored.
- `infra/cloudflare/config.yml.template` provides an optional local-managed
  tunnel config for `viz.chopsworkshop.com` with the required catch-all
  `http_status:404` rule.
- `docs/testing-guide-viz-cloudflare.md` documents the activation order:
  create Cloudflare Access application and explicit email allowlist **before**
  adding the public tunnel hostname route.
- `tests/test_viz_cloudflare_templates.py` checks that templates do not publish
  inbound ports, secret-bearing files are ignored, and the runbook preserves the
  Access-before-route safety gate.

Live activation still requires:

- Cloudflare tunnel token from the account that manages `chopsworkshop.com`.
- Final client/internal email allowlist.
- Manual verification that non-allowlisted users see Cloudflare Access denial and
  never reach Superset directly.

## Increment 6 — investigation-slice vertical slice (end-to-end proof flow)

Status: **landed 2026-06-25; pending independent reviewer pass**

Primary goal: prove the updated source architecture can carry a single
constrained question from "question string" all the way to a chart-ready
CSV + displayable graph artifact + Superset SQLite table without any
free-form LLM parsing or rewrite of legacy ingest.

Implemented in:

- `src/leaders_db/viz/investigation_slice/` — `run_investigation_slice()`
  is a deterministic, side-effect-bounded function split across
  focused submodules (`__init__.py` re-exports the public API;
  `_models.py` carries the dataclasses + supported question catalog;
  `_api.py` owns the entry point and the per-source lifecycle driver;
  `_csv.py` writes the chart-ready long-form CSV; `_html.py` renders
  the dependency-free SVG line chart). The public import surface
  (`from leaders_db.viz.investigation_slice import ...`) is unchanged
  so callers and tests do not need to update their imports. The
  slice wires PWT, Maddison, and WDI through the unified
  `SourceIngestRunner`, flattens the resulting `NormalizedObservation`
  tuples, runs `extract_concept_result(..., concept_key="gdp_per_capita")`
  over the stream, writes a long-form CSV under
  `data/processed/viz/country-year-chronicle/`, and emits the
  dependency-free HTML+SVG line chart beside it. **The chart groups
  by ``(country_code, source_id, series_label)`` and plots one polyline
  per indicator-or-recipe series, with legend labels rendered as
  ``"{country_code} \u00b7 {source_slug} \u00b7 {series_label}"``, so multiple
  sources or multiple same-source indicators for the same country/year
  are never collapsed into a single time-series line.** It also calls
  `build_superset_sqlite_db()` so the new investigation table is
  loaded into `superset_viz.sqlite` (only when the canonical core CSV
  is present; otherwise the rebuild is skipped and surfaced on the
  result envelope).
- `src/leaders_db/cli/commands_viz.py::viz-run-investigation-slice` —
  Typer CLI surface for the slice.
- `tests/test_viz_investigation_slice.py` — focused pytest coverage
  with fake adapters; proves the runner drives the lifecycle, the
  CSV/HTML are written, the Superset SQLite has the new table, and
  the slice refuses to invent data on not-ready sources.
- `VIZ_CSV_TABLES` in `src/leaders_db/viz/superset_db.py` — the new
  investigation CSV is registered as an optional entry so the
  Superset builder picks it up when present and skips it when absent.

Supported question keys are restricted to a small registry in
`SUPPORTED_QUESTIONS` (currently `gdp_per_capita_major_powers`,
mapping to the `gdp_per_capita` concept for USA / GBR / FRA / IND / CHN
over 1950-2023). Unknown keys fail fast via
`UnknownInvestigationQuestionError`. Source readiness gaps surface as
structured coverage rows on the result envelope — the slice never
silently invents data and only fails hard when zero concept rows
materialise.

### How to run

```bash
# 1. Optional: pre-stage the canonical core CSV (otherwise the slice
#    still writes CSV + HTML but skips the Superset SQLite rebuild).
leaders-db run-country-year-chronicle --config configs/prototype-2023.yaml

# 2. Run the slice against the local data lake. The default registry
#    covers PWT + Maddison + WDI; partial coverage is fine -- the
#    slice continues with whichever sources emitted observations.
leaders-db viz-run-investigation-slice \
  --question gdp-per-capita-major-powers \
  --start-year 1950 --end-year 2023

# 3. Rebuild the Superset SQLite artifact (the slice does this
#    automatically when the core CSV is present; this is for
#    re-running after manual CSV edits).
leaders-db viz-build-superset-db
```

Output artifacts:

- `data/processed/viz/country-year-chronicle/viz_investigation_gdp_per_capita_major_powers.csv`
  — long-form chart-ready table with stable column order.
- `data/processed/viz/country-year-chronicle/viz_investigation_gdp_per_capita_major_powers.html`
  — dependency-free HTML+SVG line chart (no extra packages). One
  polyline per ``(country_code, source_id, series_label)``
  indicator-or-recipe series; legend labels are
  ``"{country_code} \u00b7 {source_slug} \u00b7 {series_label}"`` so the source
  and exact indicator/recipe are visible.
- `data/processed/viz/country-year-chronicle/superset_viz.sqlite`
  — read-only analytic SQLite artifact; the new table is registered
  under `viz_investigation_gdp_per_capita_major_powers`.
