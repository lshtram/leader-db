# Testing guide — visualization Superset local integration

This guide covers Visualization Increment 4: local Apache Superset
integration, and Increment 6: the investigation-slice vertical slice
that exercises the updated source architecture end-to-end.

For the customer-facing runtime that combines Superset under `/superset/welcome/`
with static reports under `/reports/` on `viz.chopsworkshop.com`, see
`docs/testing-guide-viz-customer-portal.md`.

## Automated verification

Run:

```bash
.venv/bin/ruff check \
  src/leaders_db/viz \
  src/leaders_db/cli/commands_viz.py \
  tests/test_cli_viz.py \
  tests/test_viz_investigation_slice.py

.venv/bin/pytest tests/test_cli_viz.py tests/test_cli_smoke.py \
                  tests/test_imports.py \
                  tests/test_viz_investigation_slice.py -q
```

What this verifies:

- `leaders-db --help` registers `viz-metrics`, `viz-query`,
  `viz-build-superset-db`, and `viz-run-investigation-slice` through
  the real Typer app.
- `viz-query` derives population-by-regime output from the generic
  `viz_country_year_metrics.csv` fact table rather than a bespoke cached table.
- `viz-build-superset-db` writes a SQLite artifact containing
  `viz_country_year_metrics`, optional helper tables when their CSVs exist, and
  `viz_superset_metadata`.
- The builder fails clearly when the required core fact CSV is absent.
- Unsupported transforms cannot be silently ignored.
- The investigation-slice command drives registered adapters through
  the documented lifecycle (`check_ready -> read_raw -> transform`)
  via `SourceIngestRunner`, never via the legacy `STAGE2_ADAPTERS`
  table; emits a chart-ready CSV with stable columns; emits a static
  HTML+SVG line chart; rebuilds the Superset SQLite artifact when the
  canonical core CSV is present; refuses to silently invent data on
  unknown question keys or empty concept extractions.

## Investigation-slice smoke check (Increment 6)

The slice is a small end-to-end proof flow built around the unified
source architecture: PWT, Maddison Project, and WDI are registered
through the `SourceIngestRunner`, the `gdp_per_capita` concept is
extracted via the semantic catalog, and the chart-ready CSV +
dependency-free HTML graph are written beside the canonical
`viz_country_year_metrics.csv` artifact. The slice code itself does
not require staged raw bundles to load, but **contributing real rows
to the CSV and chart requires the upstream raw bundles to be staged
under `data/raw/<source>/`** for each source that should emit
concept rows; the unit-test suite in `tests/test_viz_investigation_slice.py`
exercises the slice end-to-end against small synthetic adapter
fixtures and so does NOT need staged raw bundles to run.

Partial readiness is the expected default, not an error. The three
sources have asymmetric raw-bundle availability and coverage:

- WDI covers roughly 1960-present in the upstream raw bundle; the
  on-disk staging for this slice is **not yet complete**, so WDI
  typically reports `ready=False` plus a `missing_raw` warning and
  contributes zero rows for now. Staging the WDI raw bundle will
  flip it to `ready=True` and contribute real rows.
- Maddison Project Database 2023 covers 1-2022 in the upstream raw
  bundle; `data/raw/maddison_project/mpd2023.xlsx` is the expected
  staging path. Until it is staged, Maddison contributes zero rows.
- PWT 10.01 covers 1950-2019; the bundle is staged at
  `data/raw/pwt/pwt1001.xlsx` and PWT typically reports `ready=True`
  and contributes derived `gdp_per_capita` rows.

The slice continues with whatever sources reported observations and
emits the CSV + graph using the rows that materialised. A slice
that completes with **zero** concept rows is treated as a hard
failure (`RuntimeError`) so a silently-empty artefact never ships.
The expected initial output therefore looks like one or more
sources reporting `ready=False` plus a smaller set of source(s)
contributing real rows; that is the documented normal state of the
slice, not a defect.

The HTML chart plots ONE polyline per
`(country_code, source_id, series_label)` triple (not one per
country or per country/source) so values from different sources
**or different indicator codes within the same source** for the
same country/year are never chained into a single misleading line.
The `series_label` is the recipe key for derived concept rows
(e.g. PWT's `pwt_gdp_per_capita_via_rgdpo_over_pop`) and the
source-specific indicator code for direct concept rows (e.g. WDI's
`wdi_gdp_per_capita` and `wdi_gdp_per_capita_ppp_constant_2017`).
Legend labels render as
`"{country_code} \u00b7 {source_slug} \u00b7 {series_label}"`
(e.g. `"USA \u00b7 world_bank_wdi \u00b7 wdi_gdp_per_capita"`) so the
source **and** the indicator / recipe are visible. Each polyline
carries `data-country`, `data-source`, and `data-indicator`
attributes for testability.

```bash
# Optional: stage the canonical core CSV so the slice also rebuilds
# the Superset SQLite artifact. If absent, the slice still writes
# the CSV + HTML and skips the SQLite rebuild (documented behaviour).
# Stage only if upstream raw bundles are available -- otherwise the
# slice will report zero concept rows and raise.
leaders-db run-country-year-chronicle --config configs/prototype-2023.yaml

# Run the slice against the local data lake.
leaders-db viz-run-investigation-slice \
  --question gdp-per-capita-major-powers \
  --start-year 1950 --end-year 2023

# Expected initial output (partial readiness is the default):
#   slice 'gdp_per_capita_major_powers' for ('USA', 'GBR', 'FRA',
#   'IND', 'CHN') (1950-2023):
#     concept rows: <count>
#     source world_bank_wdi: requested=370 emitted=<n> ready=False warnings=<k>
#     source maddison_project: requested=370 emitted=<n> ready=False warnings=<k>
#     source pwt: requested=370 emitted=<n> ready=True warnings=<k>
#     csv: .../viz_investigation_gdp_per_capita_major_powers.csv
#     html: .../viz_investigation_gdp_per_capita_major_powers.html
#     superset sqlite: .../superset_viz.sqlite (only if core CSV present)
#     (tables: viz_country_year_metrics, viz_investigation_gdp_per_capita_major_powers,
#      viz_superset_metadata)
#
# Sources reporting `ready=False` (e.g. WDI until its raw bundle is
# staged) are not a bug -- they are documented partial-readiness
# behaviour. The slice continues with whatever sources reported
# observations.

# Open the HTML in any browser to view the deterministic line chart.
xdg-open data/processed/viz/country-year-chronicle/viz_investigation_gdp_per_capita_major_powers.html

# Open the Superset dashboard and add a database using:
#   sqlite:////leaders-db-viz/superset_viz.sqlite
# The new table ``viz_investigation_gdp_per_capita_major_powers``
# is queryable from Superset's SQL Lab / Explore panes.

# Optional: rebuild the Superset SQLite artifact on its own (e.g.
# after manual CSV edits) without re-running the slice.
leaders-db viz-build-superset-db
```

Notes:

- The slice tolerates partial source readiness: PWT covers
  1950-2019, Maddison 1-2022, WDI 1960-present. Missing years
  surface as `concept_rows` gaps in the resulting CSV, not as
  errors. Missing raw bundles surface as `ready=False` plus a
  `missing_raw` warning per source on the coverage summary.
- The slice never invents data: an unsupported question key fails
  with `UnknownInvestigationQuestionError`; a successful slice that
  produces zero concept rows fails with `RuntimeError` rather than
  silently writing an empty CSV.
- `viz-run-investigation-slice --no-rebuild-superset-db` skips the
  Superset SQLite rebuild so callers can drive the rebuild manually
  via `viz-build-superset-db` afterwards.

## Manual local Superset smoke check

Prerequisites:

- Docker and Docker Compose.
- Visualization CSV exports under
  `data/processed/viz/country-year-chronicle/`, including at least
  `viz_country_year_metrics.csv`.

Steps:

1. Build the Superset-facing SQLite artifact:

   ```bash
   leaders-db viz-build-superset-db
   ```

   Expected output includes:

   ```text
   wrote Superset SQLite DB: .../data/processed/viz/country-year-chronicle/superset_viz.sqlite
   container SQLAlchemy URI (compose): sqlite:////leaders-db-viz/superset_viz.sqlite
   ```

2. Create local Superset secrets:

   ```bash
   cp infra/superset/superset.env.template infra/superset/superset.env
   openssl rand -base64 42
   ```

   Replace every `replace-with-*` value in `infra/superset/superset.env`.
   Do **not** commit `superset.env`.

3. Start Superset and the local nginx path proxy:

   ```bash
   docker compose --env-file infra/superset/superset.env \
     -f infra/superset/docker-compose.yml up
   ```

   If Superset was already running before a config change, restart it so
   `infra/superset/superset_config.py` is reloaded:

   ```bash
   docker compose --env-file infra/superset/superset.env \
     -f infra/superset/docker-compose.yml restart superset
   ```

4. Open `http://localhost:8088/superset/welcome/` and log in with the admin
   user/password from `infra/superset/superset.env`. `http://localhost:8088/`
   redirects to `/reports/`, while `http://localhost:8088/reports/` serves the
   static report landing page through nginx.

5. Add a database in Superset using this SQLAlchemy URI:

   ```text
   sqlite:////leaders-db-viz/superset_viz.sqlite
   ```

   The compose file mounts `data/processed/viz/country-year-chronicle` at
   `/leaders-db-viz` as read-only (`:ro`). Superset must not connect to the
   mutable project catalog database for this increment.

   Superset 6 blocks SQLite data sources unless its unsafe-connection guard is
   explicitly disabled. This local config sets
   `PREVENT_UNSAFE_DB_CONNECTIONS = False` **only** so the read-only mounted
   artifact above can be added as a dashboard data source. The Superset metadata
   database remains PostgreSQL, and the SQLite file must stay mounted read-only.

   If the UI shows:

   ```text
   SQLiteDialect_pysqlite cannot be used as a data source for security reasons
   ```

   then the running container has not loaded the current `superset_config.py`.
   Restart the `superset` service with the command in step 3 and retry adding
   the database.

6. Confirm tables are visible:

   - `viz_country_year_metrics`
   - `viz_metric_catalog` if the CSV exists
   - `viz_regime_year_population` if the cached proof CSV exists
   - `viz_source_coverage` if the CSV exists
   - `viz_superset_metadata`

7. Create or validate the first dashboard set:

   - country metric over time;
   - compare metrics over time;
   - population by regime bucket;
   - YoY growth by regime bucket;
   - provenance/source coverage table.

## Notes

- Increment 4 is localhost-only. Internet exposure through
  `viz.chopsworkshop.com` and Cloudflare Access belongs to Increment 5.
- The Superset metadata database is Postgres inside Docker Compose; the Leaders
  DB analytic data is the separate read-only SQLite mount.
- Apache Superset's own Docker documentation recommends Docker Compose for local
  setup and stresses unique secrets for non-development use; keep the local
  `superset.env` private.
