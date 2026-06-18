# Local data lake

This folder is governed by [`docs/local-data-store.md`](../docs/local-data-store.md).
Layout:

- `raw/<source>/` — immutable downloaded files + per-source `metadata.json`.
- `processed/` — deterministic normalized parquet/csv.
- `interim/` — mid-pipeline scratch.
- `outputs/` — reports, validation CSVs, manual-review queue, summary markdown.
- `logs/` — per-run log files.
- `metadata/` — cross-source catalog metadata (aliases, authority, indicators).
- `catalog/` — SQLite database file (`leaders_db.sqlite`).

Files inside this folder are gitignored (see root `.gitignore`).
Only the folder structure and this README are committed.
