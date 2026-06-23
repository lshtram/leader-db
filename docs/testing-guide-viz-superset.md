# Testing guide — visualization Superset local integration

This guide covers Visualization Increment 4: local Apache Superset integration.

## Automated verification

Run:

```bash
.venv/bin/ruff check \
  src/leaders_db/viz \
  src/leaders_db/cli/commands_viz.py \
  tests/test_cli_viz.py

.venv/bin/pytest tests/test_cli_viz.py tests/test_cli_smoke.py tests/test_imports.py -q
```

What this verifies:

- `leaders-db --help` registers `viz-metrics`, `viz-query`, and
  `viz-build-superset-db` through the real Typer app.
- `viz-query` derives population-by-regime output from the generic
  `viz_country_year_metrics.csv` fact table rather than a bespoke cached table.
- `viz-build-superset-db` writes a SQLite artifact containing
  `viz_country_year_metrics`, optional helper tables when their CSVs exist, and
  `viz_superset_metadata`.
- The builder fails clearly when the required core fact CSV is absent.
- Unsupported transforms cannot be silently ignored.

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

3. Start Superset locally:

   ```bash
   docker compose --env-file infra/superset/superset.env \
     -f infra/superset/docker-compose.yml up
   ```

4. Open `http://localhost:8088` and log in with the admin user/password from
   `infra/superset/superset.env`.

5. Add a database in Superset using this SQLAlchemy URI:

   ```text
   sqlite:////leaders-db-viz/superset_viz.sqlite
   ```

   The compose file mounts `data/processed/viz/country-year-chronicle` at
   `/leaders-db-viz` as read-only (`:ro`). Superset must not connect to the
   mutable project catalog database for this increment.

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
