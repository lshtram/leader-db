# Local Data Store

The project is local-first. We use a small data lake on disk plus a SQLite catalog, not a service. Layer rules below are normative; changes require updating this file plus the Always-On rules in [`AGENTS.md`](../AGENTS.md).

## Folder Layout

```
data/
├── raw/
│   ├── <source>/              # one folder per priority source + client_existing
│   │   ├── <original-files>   # immutable downloaded files
│   │   └── metadata.json      # required; see Data Sources doc
├── processed/                 # normalized parquet/csv, deterministic, idempotent
├── interim/                   # mid-pipeline scratch (joined frames before scoring)
├── outputs/                   # reports, validation CSVs, manual-review queue, summary markdown
├── logs/                      # per-run log files
└── metadata/                  # cross-source catalog metadata (aliases, authority, indicators)
```

## Layer Rules

### `data/raw/<source>/`

- **Immutable.** Never edit a raw file in place. If you must modify it for parsing, copy to `data/interim/<source>/` first.
- One folder per source, matching the module under `src/leaders_db/ingest/<source>.py`.
- A `metadata.json` is **required** (REQ-LAKE-002) before any downstream code may read the folder. Minimum schema:

```json
{
  "source_name": "V-Dem",
  "source_version": "v16",
  "download_date": "YYYY-MM-DD",
  "coverage": "country-year",
  "years_available": "varies by country",
  "license_note": "check source terms",
  "local_files": ["vdem_country_year_v16.csv"],
  "ingestion_status": "downloaded",
  "source_url": "https://www.v-dem.net/",
  "checksum_sha256": "..."
}
```

- `ingestion_status` transitions: `pending → downloaded → ingested`. Special terminal states: `unavailable`, `blocked_login`, `blocked_permission`, `parse_failed`.

### `data/processed/`

- Deterministic normalized parquet/csv. Re-runs are idempotent.
- Outputs from each ingest stage land in `data/processed/<source>/<table>.parquet` or `.csv`.
- Schema is canonical: ISO3 country key, ISO year, normalized columns per the indicator catalog.

### `data/interim/`

- Mid-pipeline scratch: cross-source joined frames before scoring, large intermediate merges, etc.
- Safe to delete between runs. Not intended for cross-process persistence.

### `data/outputs/`

- Public interface for analysts and the manual-review queue.
- Includes:
  - `outputs/source_availability_report.{csv,md}` (Stage 0)
  - `outputs/leader_resolution_<year>.csv` (Stage 4)
  - `outputs/validation_<year>_leader_identity.csv` (Stage 12)
  - `outputs/validation_<year>_scores.csv` (Stage 12)
  - `outputs/validation_<year>_summary.md` (Stage 12)
  - `outputs/validation_<year>_high_delta_cases.csv` (Stage 12)
  - `outputs/validation_<year>_manual_review_queue.csv` (Stage 14)
  - `outputs/llm_calls/<run-id>/` — every LLM request/response, for audit.
- Subdirectories are required once a family has more than one artifact. Do not
  let large runs accumulate unrelated files directly under `data/outputs/`.
  Current grouping convention:
  - `outputs/scoring/<year>/` — per-category score CSVs, indicator coverage,
    missingness summaries, and category-specific country universes.
  - `outputs/scorecards/<year>/` — cross-category scorecards, deltas, and
    associated mismatch analysis.
  - `outputs/source_coverage/` and `outputs/source_coverage_potential/` —
    source coverage audits and planning outputs.
  - `outputs/country-year-chronicle/` — CYC CSV/SQLite artifacts.
  - `outputs/experiments/<slice-name>/` — explicitly experimental slices. The
    legacy `outputs/vertical_slice_2023/` path may remain until code defaults are
    migrated in a source-code pass.
- File names use lowercase, kebab-or-snake as appropriate, year always 4 digits.

### `data/logs/`

- Per-run log files keyed by run-id.
- One subdirectory per run: `data/logs/<run-id>/pipeline.log`, `data/logs/<run-id>/warnings.csv`, `data/logs/<run-id>/run_config.yaml` (a copy of the resolved config).
- Logs may include progress markers but must not include secrets, raw credentials, or full LLM prompts/responses (those go to `data/outputs/llm_calls/<run-id>/`).

### `data/metadata/`

- Cross-source catalog metadata.
- Includes:
  - `country_aliases.csv` — built incrementally by Stage 3.
  - `source_authority_table.csv` — per-source authority weights per indicator family (§11).
  - `indicator_catalog.csv` — obsolete draft location. Stage 5 now derives source-level indicator definitions from committed per-source catalogs under `src/leaders_db/ingest/catalogs/<source>.csv` and category-level source plans from `src/leaders_db/score/source_plans.py`. If a consolidated catalog is needed later, generate it from those code-owned contracts rather than treating `data/metadata/indicator_catalog.csv` as canonical.

## Git Policy

- The folder skeletons under `data/` are committed (each as an empty dir with a `README.md` or `.gitkeep`).
- The actual contents are gitignored via patterns in the root `.gitignore`:
  - `data/raw/client_existing/*.xlsx` and `*.docx` are gitignored (the client bundle lives in its folder).
  - `data/raw/*/*.csv`, `*.parquet`, `*.zip`, `*.json`, `*.xlsx`, `*.dta`, `*.sav`, etc. are gitignored.
  - `data/processed/`, `data/interim/`, `data/outputs/`, `data/logs/`, `data/metadata/` contents are gitignored.
- The SQLite catalog file (`data/catalog/*.sqlite`) is gitignored.
- `research/` is gitignored (derived exploratory analyses and leader memos).

## Idempotency

- Re-running any stage must produce the same outputs without re-downloading source files that are already in `data/raw/<source>/` with a valid `metadata.json`.
- Stage 0 (`check-source-availability`) must check for `metadata.json` and the file's checksum before initiating any network request.
- Ingest scripts must write to a temp path and atomically rename into `data/processed/<source>/` to avoid leaving half-written files on a crash.

## Adding a New Source

1. Create the folder `data/raw/<source_key>/` with a placeholder `metadata.json` (`ingestion_status: pending`).
2. Implement `src/leaders_db/ingest/<source_key>.py`.
3. Add the source to the registry in [`data-sources.md`](data-sources.md).
4. Add a test under `tests/test_ingest_<source_key>.py` that uses a tiny fixture.
5. Wire the CLI command in `src/leaders_db/cli.py` (it should already be enumerated — just point it at the new module).
6. Update `docs/req/requirements-core.md` with any new REQ-* lines.

## Adding a New Output

1. Decide which layer it belongs to (`outputs/` for analyst-facing artifacts; `interim/` for scratch).
2. Write to a temp file then atomically rename, so partial files never appear.
3. Use a deterministic filename pattern that includes the target year.
4. Add a smoke test under `tests/test_export_<name>.py`.
