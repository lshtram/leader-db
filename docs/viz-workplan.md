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

Status: **not started**

- Cloudflare Tunnel route from `viz.chopsworkshop.com` to local Superset.
- Cloudflare Access policy with explicit email allowlist.
- Superset hardening: HTTPS through Cloudflare, strong local secret, no default
  credentials, `DEBUG=False`, secure sessions where applicable, read-only DB.
