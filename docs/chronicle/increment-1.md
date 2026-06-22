# Country-Year Chronicle — Increment 1 Implementation Notes

Date: 2026-06-20

Sub-project: **Country-Year Chronicle** (`cyc`)

Scope: incremental implementation notes for Increment 1 (experimental
read-only CSV vertical slice) per
[`docs/chronicle/workplan.md`](workplan.md)
§7 and the Increment 0 findings in
[`docs/chronicle/increment-0.md`](increment-0.md).

This document is intentionally concise. The full Increment 0 contract,
column order, and taxonomy decisions remain authoritative in Increment 0;
this document only records what was shipped, what is deferred, and the
runtime/test wiring.

## 1. What landed

- **New package `src/leaders_db/chronicle/`** with focused modules:
  `constants.py`, `sources.py`, `regime.py`, `system_type.py`,
  `row_builder.py`, `csv_writer.py`, `runner.py`, `__init__.py`.
- **New CLI command `leaders-db run-country-year-chronicle`** registered
  via `src/leaders_db/cli/commands_chronicle.py` and exported through
  `src/leaders_db/cli/__init__.py`.

CLI usage:

```bash
leaders-db run-country-year-chronicle \
  --start-year 1900 --end-year 2026 \
  --countries USA,GBR,FRA,IND,RUS,SUN,CHN \
  --output data/outputs/country-year-chronicle/pilot.csv
```

Defaults: ISO3 scope `USA,GBR,FRA,IND,RUS,SUN,CHN`; year window
`1900-2026`; output path
`<project_root>/data/outputs/country-year-chronicle/country_year_chronicle.csv`.

## 2. Runtime boundaries

- **Read-only.** No writes to the prototype SQLite catalog, no
  `client_matrix` import, no LLM adapter import.
- **Sources consumed** (in production): raw V-Dem CSV at
  `data/raw/vdem/V-Dem-CY-Full+Others-v16.csv`; processed WDI parquet
  at `data/processed/world_bank_wdi/wdi_country_year.parquet`;
  processed SIPRI milex parquet at
  `data/processed/sipri_milex/sipri_milex_country_year.parquet`.
- **Output** is one CSV row per requested `(iso3, year)` pair regardless
  of source coverage. Missing fields are empty cells and the row
  carries the appropriate `missing_*` / `*_gap` flag.
- **Atomic write** through `tempfile` + `os.replace`; no partial files
  in `data/outputs/` after a failed run.
- **Attribution block** is the leading `#` comment lines. Each line is
  a byte-for-byte substring of `docs/source-attributions.md` §1
  (drift-guarded by `test_vdem_attribution_matches_attributions_doc`,
  `test_wdi_attribution_matches_attributions_doc`, and
  `test_sipri_attribution_matches_attributions_doc`).

## 3. Country-status and regime classifier contract

- **`country_status` is dynamic per row.** IND pre-1947 emits
  `colonial/dependent` (the row builder reads
  `colonial_status_until=1946` from `COUNTRY_METADATA` and flips the
  status for `year <= 1946`); IND 1947+ emits `independent`. SUN emits
  `successor_state`; all other pilot identities emit `independent`.
- **System-type classifier is conservative and deterministic.**
  Curated country-period mappings cover only the documented
  authoritative cases: `SUN 1922-1991`, `CHN 1949-2026`,
  `IND 1858-1946`. RUS is intentionally NOT curated; RUS rows fall
  through to the regime-bucket fallback (Full/Flawed democracy ->
  `Liberal capitalist democracy`; Hybrid/Authoritarian ->
  `Mixed / unclear`; Unknown -> `Unknown` + low-confidence flag).
- **SIPRI military-spend flag tracks `milex_constant_usd` only.**
  Ancillary fields (per-capita, share-of-GDP) do not clear
  `missing_military_spend` on their own.

## 4. Test coverage

124 focused pytest tests across 5 files:

- `tests/test_chronicle_constants.py` — column contract, attribution,
  CSV writer, atomic write, country metadata, curated mapping
  invariants.
- `tests/test_chronicle_regime.py` — direct `v2x_regime` mapping,
  polyarchy fallback, 2025 proxy flag,
  `RegimeSource.from_vdem_lookup` proxy logic.
- `tests/test_chronicle_system_type.py` — curated mappings
  (SUN/CHN/IND), RUS fallback behavior for Full/Flawed/Hybrid/
  Authoritarian buckets, notes content.
- `tests/test_chronicle_row_builder.py` — row shape, one row per
  identity-year, missing-flag propagation, pre/post-existence gaps,
  successor-state / colonial flags, proxy-year flag,
  `row_confidence` aggregate, RUS fallback, IND dynamic
  `country_status`, SIPRI flag-from-`milex_constant_usd`-only contract,
  no-client-matrix import guard.
- `tests/test_cli_chronicle.py` — Typer registration, `--help` content,
  default output path resolution, `--output` / `--countries` /
  `--start-year` / `--end-year` validation, `--allow-regime-proxy` /
  `--no-allow-regime-proxy` behavior, 7-country pilot end-to-end smoke,
  reviewer-mandated parsed-row assertions for IND 1900/1946/1947 and
  RUS Authoritarian/Hybrid fallback.

## 5. Deferred to later increments

- ~~Ruler fields are emitted as empty placeholders with
  `missing_ruler` (no full ruler resolver yet — Stage 4 work).~~ —
  **closed by Increment 2** (2026-06-21). See
  [`increment-2.md`](increment-2.md)
  for the Archigos + REIGN ruler resolver.
- ~~Pre-1960 GDP/population is empty because the local WDI parquet
  only contains 2022 today (full WDI re-run is a Stage 2/3 task,
  not Increment 1).~~ — **closed by Increment 2** for the
  Maddison-backed path (Maddison provides the historical real
  economy signal for 1900-2022). WDI re-run for the recent window
  is still deferred.
- Country area and controlled-area fields are empty with
  `missing_area` and `controlled_area_not_modeled`.
- All-countries extension (Increment 3 — was Increment 2).

## 6. Open follow-ups

- None outstanding for Increment 1. The chronicle package currently
  ships 11 focused modules (`__init__.py`, `constants.py`, `sources.py`,
  `regime.py`, `system_type.py`, `row_builder.py`, `csv_writer.py`,
  `runner.py`, plus `_formatters.py`, `_flags.py`, and `_wdi_fields.py`
  extracted from the original 559-line `row_builder.py`); most are under
  the 400-line convention, except `constants.py`, which is 422 lines.
