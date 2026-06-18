# PTS Architecture Design — Stage 2 Adapter for the Political Terror Scale

> **Status:** architecture design, ready for test-builder and developer.
> **Phase:** C.7 (data acquisition, seventh adapter, after V-Dem, WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7).
> **Target source key:** `pts`.
> **Wiring in:** `src/leaders_db/ingest/__init__.py::STAGE2_ADAPTERS` (replace the existing `"pts": None` stub with `pts.ingest_pts`).
> **Source verdict:** ✅ `vetted_ok` per [`docs/source-vetting-report.md`](../source-vetting-report.md) §3.8.
> **Liveness verified:** 2026-06-18 — `https://www.politicalterrorscale.org/Data/Files/PTS-2025.xlsx` returns HTTP 200 with `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`; the downloaded xlsx is **572,234 bytes (572 KB)**, contains 1 sheet named `PTS-2025`, 10,531 data rows × 14 columns + 1 header row. SHA-256: `6f4d1ccdda1d2fdce382a978922790390ce5f61ae9f4aefa1970e9ca8bd88832` (matches `data/raw/political_terror_scale/metadata.json`).
> **Data-lake path mismatch (architect flag for the developer).** The `metadata.json` says the folder is `political_terror_scale/`, but the dispatch-table key is `pts`. The folder name (`political_terror_scale/`) is kept to preserve the downloaded bundle's name (no need to rename disk files); the source key (`pts`) is the CLI flag and the catalog filename. This is the same pattern as the other multi-word source keys (the folder is the human-readable bundle name; the source key is the dispatch key).

This document is the design contract for the PTS Stage 2 adapter. The test-builder writes tests against the public surface in §3.3; the developer implements against the same surface. The catalog spec in §3 is the only place where PTS's indicator list is decided.

> **Live-data discrepancies flagged by the architect.** The architect probed the real xlsx on 2026-06-18 and found three discrepancies between the prompt's specification and the actual data. Each is flagged inline below and consolidated in §11 (Constraints #17, #18, #19):
> 1. **Region codes**: the prompt and `metadata.json` list 6 codes (`sa`/`ssa`/`eur`/`ame`/`apac`/`mena`) but the live xlsx has **7 single-region codes** (`eap`, `eca`, `lac`, `mena`, `na`, `sa`, `ssa`) — these are the **World Bank country-and-lending-groups codes**, not the prompt's list. Plus 1 multi-region data anomaly (`'mena, ssa'`, 49 rows).
> 2. **NA_Status code coverage**: the prompt says `0/66/77/88/99`; live data confirms all 5 codes are present (with `99` being the rarest).
> 3. **The 4th sentinel case (the inconsistency case)** is real and observable in the data: row "Bahamas 2017" has `PTS_A='NA'` and `NA_Status_A=0`. This is the "data inconsistency" row the §6 table flags; the developer must log a warning and treat as missing, not crash.
>
> The architect's design addresses all 3 findings explicitly. The developer does NOT silently change the spec — the developer surfaces these findings in the same commit and updates `metadata.json` to match the live data (mirror the WGI "1996-2023" → "1996-2022" docs fix pattern).

---

## 1 — Purpose

This is the Stage 2 adapter for the **Political Terror Scale (PTS)**, the academic standard for measuring state-perpetrated political terror and physical integrity abuses. It is the seventh Stage 2 adapter built (after V-Dem, WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7).

PTS contributes to the **`domestic_violence`** category per [`docs/source-vetting-report.md`](../source-vetting-report.md) §3.8. The category's three sources are:

| Source | Indicators fed to `domestic_violence` |
|---|---|
| **UCDP one-sided** (type=3 events + fatalities) | 2 indicators (`ucdp_onesided_events`, `ucdp_onesided_fatalities`) |
| **V-Dem repression** (`v2csreprss`, `v2clkill`, `v2x_clphy`) | 3 indicators (per the V-Dem catalog) |
| **PTS** (this adapter) | **3 indicators** (`pts_amnesty_score`, `pts_human_rights_watch_score`, `pts_state_dept_score`) |

PTS is **event-count-light, score-heavy**: it does not count events or fatalities; it carries an expert-coded ordinal score (1-5) per country-year from 3 independent coding teams (Amnesty, HRW, US State). The Stage 12 cross-source comparison can therefore triangulate the 3 PTS scores against UCDP's event/fatality counts to identify disagreements between expert-coded scores and event records (a known signal for contested regimes).

The adapter is structurally closer to **WGI / SIPRI milex** (one local xlsx, no network, no HTTP layer) than to WDI (per-indicator HTTP, JSON cache) or UCDP (event-level aggregation). The xlsx is 572 KB and fits in memory; the read pattern is "openpyxl `read_only=True` → single long-format pass → 3-indicator wide pivot". The NA_Status sentinel-precedence logic is the PTS-specific data quirk (the only Stage 2 source with this 2-signal sentinel pattern).

## 2 — Source contract (what PTS gives us, what we extract)

### Canonical URL and file format

| Field | Value |
|---|---|
| Canonical URL | `https://www.politicalterrorscale.org/Data/Files/PTS-2025.xlsx` |
| Alternate URL | `https://www.politicalterrorscale.org/Data/Files/PTS-2025.csv` (CSV mirror; xlsx is canonical) |
| Format | Excel xlsx (single sheet `PTS-2025`) |
| Size | 572,234 bytes (572 KB; verified live 2026-06-18) |
| Auth | none (public, free, no API key) |
| Release cadence | annual; the current release is PTS-2025 (data through 2024) |
| Local storage | `data/raw/political_terror_scale/PTS-2025.xlsx`; `metadata.json` alongside |
| SHA-256 | `6f4d1ccdda1d2fdce382a978922790390ce5f61ae9f4aefa1970e9ca8bd88832` |

> **Why xlsx, not the CSV mirror?** Both are published. The xlsx is canonical (the same `.xlsx` ships as the "official" download on politicalterrorscale.org). The CSV mirror is generated from the xlsx; reading the xlsx directly avoids the `csv → xlsx → csv` round-trip. The `pd.read_excel` path is fine for 572 KB and 10k rows.

### xlsx structure (verified live 2026-06-18)

The xlsx is a **single-sheet workbook** with **14 columns and 10,531 data rows** (one row per country-year). The layout is **long format**: each row is a single `(country, year)` triple with the 3 PTS scores side-by-side.

**Header (14 columns, verified verbatim from live xlsx):**

```
Country, Country_OLD, Year, COW_Code_A, COW_Code_N, WordBank_Code_A, UN_Code_N,
Region, PTS_A, PTS_H, PTS_S, NA_Status_A, NA_Status_H, NA_Status_S
```

**Per-row data shape (verified with `openpyxl.read_only=True`):**

| Col | Name | Type | Example | Notes |
|---|---|---|---|---|
| 0 | `Country` | str | `'Afghanistan'` | display name (current name; changes for renamed countries) |
| 1 | `Country_OLD` | str | `'Afghanistan'` | historical name (same as Country for most rows) |
| 2 | `Year` | int | `1976..2024` | 49 distinct years |
| 3 | `COW_Code_A` | str | `'AFG'` | Correlates of War alphabetic (3-letter) |
| 4 | `COW_Code_N` | int | `700` | COW numeric |
| 5 | `WordBank_Code_A` | str | `'AFG'` | World Bank 3-letter (ISO3-style) |
| 6 | `UN_Code_N` | int | `4` | UN M49 numeric |
| 7 | `Region` | str | `'sa'`, `'ssa'`, `'eap'`, `'eca'`, `'lac'`, `'mena'`, `'na'`, `'mena, ssa'` | **8 distinct values; see §6.4 for the discrepancy** |
| 8 | `PTS_A` | int (1-5) OR str `'NA'` | `2` or `'NA'` | Amnesty International score |
| 9 | `PTS_H` | int (1-5) OR str `'NA'` | `'NA'` | Human Rights Watch score |
| 10 | `PTS_S` | int (1-5) OR str `'NA'` | `2` | US State Department score |
| 11 | `NA_Status_A` | int | `0` / `66` / `77` / `88` / `99` | provenance flag for `PTS_A` |
| 12 | `NA_Status_H` | int | same scale | provenance flag for `PTS_H` |
| 13 | `NA_Status_S` | int | same scale | provenance flag for `PTS_S` |

**NA_Status code semantics (verified live; all 5 codes observed in 2023 subset):**

| Code | Semantics | Stage 2 handling |
|---|---|---|
| `0` | present (valid data) | use `PTS_X` |
| `66` | not covered (PTS does not code this country-year) | missing → drop the indicator |
| `77` | country did not exist (e.g., USSR rows after 1991) | missing → drop the indicator |
| `88` | not coded (the coder has no opinion) | missing → drop the indicator |
| `99` | missing (data is genuinely unavailable) | missing → drop the indicator |

**Live 2023 row counts (probe 2026-06-18):** 215 country rows for Year=2023. Distribution of `NA_Status_A`:

| Code | Count | % of 2023 rows |
|---|---|---|
| `0` | 157 | 73% |
| `88` | 42 | 20% (not coded) |
| `77` | 9 | 4% (country didn't exist) |
| `66` | 7 | 3% (not covered) |
| `99` | 0 | 0% (missing) |

For 2023: `pts_amnesty_score` has 157 valid cells, `pts_human_rights_watch_score` has 108 (HRW covers fewer countries), `pts_state_dept_score` has 197 (State reports cover the most).

### What we extract vs what we defer

**Extract (3 indicators × 1 statistic × 49 years):**

- The 3 PTS scores (`PTS_A`, `PTS_H`, `PTS_S`), all per country-year.
- All 49 years (1976-2024) are kept in the wide frame; the year filter is applied at the orchestrator level.
- ~200 countries per year (varies; the 2023 subset has 215 rows but not all have valid data for all 3 indicators).

**Defer to a future iteration (kept in the xlsx but not written to `source_observations`):**

- The `Country_OLD` column (historical name; same as `Country` for most rows; deferred — not an indicator).
- The 4 ID columns beyond `COW_Code_A` (the secondary `COW_Code_N`, `WordBank_Code_A`, `UN_Code_N` are kept for cross-validation but `COW_Code_A` is the primary `source_row_reference` suffix; see §7).
- The `Region` column is **preserved in the long frame** for the manual-review queue (Stage 14 uses region for stratified review) but is NOT extracted as a separate `source_observations` indicator. The 6/7 region values are audit metadata.

> **Why 3 separate indicators (not collapse to worst-of-three)?** Per the user decision in the prompt (and §3 below), PTS contributes 3 indicators to `domestic_violence` so the Stage 12 cross-source comparison reads all 3 alongside UCDP's 2 and V-Dem's 3. Collapsing to a single worst-of-three would lose the 3-way coder-disagreement signal.

### Indicator catalog scope (this design)

For the prototype, all **3** PTS indicators are extracted, feeding the **1 rating category** PTS serves per the source-vetting report:

1. **`domestic_violence`** — 3 indicators: `pts_amnesty_score` (PTS_A), `pts_human_rights_watch_score` (PTS_H), `pts_state_dept_score` (PTS_S). The 3 PTS scores are the **third source** for `domestic_violence` (after UCDP one-sided and V-Dem repression). The 3-way coding by Amnesty, HRW, and State provides a built-in coder-disagreement signal: when the 3 scores disagree, that is evidence of contested regime classification.

The full per-indicator spec (raw column → canonical `variable_name`, scale, unit, category, one-line description) is in §3. The catalog CSV the developer will author lives at `src/leaders_db/ingest/catalogs/pts.csv` (3 rows + header; sibling to the adapter modules, per Phase C convention #1).

### Integration with downstream schema

None of the PTS indicators populate the `country_years` table directly (those columns are reserved for WDI's `population`, `gdp_current_usd`, `gdp_per_capita` — see [`docs/architecture/wdi.md`](wdi.md) §2.1). All 3 PTS indicators live in `source_observations` and are consumed by the Stage 5 score module for `domestic_violence`.

### License

PTS is distributed under **free academic use with attribution**. The canonical citation is the one in [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `pts`:

> Wood, Reed M., Mark Gibney, and others. *The Political Terror Scale (PTS)*. https://www.politicalterrorscale.org/

The drift-guard test `test_pts_attribution_matches_attributions_doc` (§8.5) enforces byte-for-byte consistency.

### Cited artifacts

- Indicator catalog: `src/leaders_db/ingest/catalogs/pts.csv` (to be authored from §3).
- Per-source `metadata.json`: `data/raw/political_terror_scale/metadata.json` (already on disk; see §11 #17 for the region-code drift fix).
- Attribution: `docs/source-attributions.md` §1 entry for `pts`.

---

## 3 — Indicator catalog (the contract for the test fixture)

The test-builder will author `tests/fixtures/pts/sample.xlsx` based on this spec. The developer will author `src/leaders_db/ingest/catalogs/pts.csv` from this spec. The two artifacts must agree on the indicator list.

> **Source-of-truth principle.** If the test fixture count and the design catalog spec disagree, the design doc is the source of truth; the test fixture must match. This design specifies **3** indicators. The test fixture must therefore cover **3** indicators (one per catalog row).

### Catalog format

Same CSV format as `vdem.csv`, `wdi.csv`, `wgi.csv`, `ucdp.csv`, `sipri_milex.csv`, and `sipri_yearbook_ch7.csv` (Phase C convention #1). The 8 required columns are exactly the V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 8; the test fixture mirrors them.

```
variable_name,raw_column,rating_category,raw_scale,normalized_scale_target,higher_is_better,unit,description
```

### Indicator list (3 indicators, 1 category)

| # | Table col key (`raw_column`) | `variable_name` | Category | Scale | Unit | Direction | Why it matters |
|---|---|---|---|---|---|---|---|
| 1 | `PTS_A` | `pts_amnesty_score` | `domestic_violence` | `ordinal` | `pts_score` | `False` | PTS score from **Amnesty International** annual reports (1-5 scale; higher = more political terror). The "original" PTS series (Wood & Gibney's foundational coding). Cross-validates UCDP one-sided fatalities and V-Dem v2csreprss. |
| 2 | `PTS_H` | `pts_human_rights_watch_score` | `domestic_violence` | `ordinal` | `pts_score` | `False` | PTS score from **Human Rights Watch** annual reports (1-5 scale; higher = more political terror). Independent coder; lower coverage than PTS_A. The HRW disagreement with PTS_A is a known signal for contested regimes. |
| 3 | `PTS_S` | `pts_state_dept_score` | `domestic_violence` | `ordinal` | `pts_score` | `False` | PTS score from **US State Department** Country Reports on Human Rights Practices (1-5 scale; higher = more political terror). Highest coverage of the 3 (State covers nearly all countries every year). The State's political slant is a known caveat. |

> **Why `higher_is_better=False` for all 3?** The raw PTS scale is 1-5 where 1 = least terror (best human rights) and 5 = most terror (worst human rights). The pipeline's scoring convention (per requirement §6 and the source-attributions §1 entry) **inverts** the scale: higher normalized score = less terror = better. The mapping for the Stage 5 score module is:
>
> | Raw PTS (1-5) | Normalized score (0-10) | Semantic |
> |---|---|---|
> | 1 | 10 | least terror (best) |
> | 2 | 7.5 | |
> | 3 | 5.0 | |
> | 4 | 2.5 | |
> | 5 | 0 | most terror (worst) |
>
> Stage 2 only writes the raw 1-5 value to `source_observations.normalized_value` and preserves the `higher_is_better=False` flag so the Stage 5 score module inverts the direction. This is the same convention as SIPRI milex's 4 indicators (more spending = worse peace signal → `higher_is_better=False`).

> **Why exactly 3 indicators (not 1 collapsed, not 6 expanded)?** The PTS xlsx has exactly 3 score columns (`PTS_A`, `PTS_H`, `PTS_S`). The catalog extracts all 3 as separate indicators (not collapsed to a single "worst-of-three" or "average-of-three" indicator) for 2 reasons:
>
> 1. **Cross-source comparison richness.** Stage 12's compare-vs-client step reads all `domestic_violence` indicators across all 3 sources (UCDP's 2 + V-Dem's 3 + PTS's 3 = 8 indicators). Collapsing PTS to a single indicator would reduce the cross-source comparison's power and obscure the 3-way coder disagreement signal.
>
> 2. **Cross-validation with the source-vetting report.** Per [`docs/source-vetting-report.md`](../source-vetting-report.md) §3.8, PTS is listed as one source contributing 3 indicators to `domestic_violence` (matching UCDP's 2 + V-Dem's 3 per-indicator profile). Collapsing to 1 would be inconsistent with the report.
>
> The 3-indicator choice is locked for the prototype. The user can extend to a 4th indicator (e.g., a PTS-derived "disagreement index") in a future iteration as a 1-row catalog addition.

### `raw_scale` convention

| `raw_scale` | Used for | What it means |
|---|---|---|
| `ordinal` | All 3 indicators | An ordinal expert-coded score on the integer scale 1-5. The `source_observations.normalized_value` column shape is `int` (or `NULL` if the cell is `'NA'` with `NA_Status != 0` per §6). |

### `normalized_scale_target` convention

For the prototype, all 3 indicators normalize to `0-10` (matching the PTS project's own reporting convention and the inverted-score convention). The actual normalization is the Stage 5 score module's job, not Stage 2's. Stage 2 only writes the raw 1-5 value to `source_observations.normalized_value` and preserves the target in the catalog. The `normalized_scale_target` column is documentation for Stage 5, not a transformation.

> **Why `0-10` and not `0-1`?** Every prior Stage 2 catalog uses `0-1` as the normalized target (V-Dem, WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7). PTS uses `0-10` because the raw 1-5 scale maps naturally to the 0-10 inverted scale with 2.5-point increments. The Stage 5 score module can rescale to 0-1 internally for the cross-source agreement calculation; the catalog's `0-10` is the user-facing convention. This is the first PTS-specific deviation from the 0-1 convention; the developer documents it in the catalog header.

### `unit` convention

| `unit` | Used for |
|---|---|
| `pts_score` | All 3 indicators |

The PTS unit is an ordinal score (no concrete unit like "events" or "USD"); the `pts_score` tag captures the scale's nature. This is analogous to V-Dem's dimensionless `index` and WGI's dimensionless `z_score`.

### Test fixture shape (2 countries × 2 years × 3 indicators = 12 cells + sentinel cases)

The test-builder's fixture `tests/fixtures/pts/sample.xlsx` is a **real-format PTS xlsx** created by **slicing the real `data/raw/political_terror_scale/PTS-2025.xlsx`** with `openpyxl` (committed under `tests/fixtures/pts/`). The test-builder uses `openpyxl.load_workbook` + iteration to copy 4 rows (2 countries × 2 years) into a new workbook, preserving the **exact 14-column header and the exact mixed int/str PTS_X values and NA_Status values**. Shape:

- **1 sheet** named `PTS-2025` (the canonical sheet name).
- **14 columns** in the same order as the real xlsx (so the `openpyxl.read_only` iteration matches).
- **2 countries**: Afghanistan (`COW_Code_A='AFG'`, region=`'sa'`) and United States (`COW_Code_A='USA'`, region=`'na'`). Chosen because: Afghanistan has all 3 PTS_X populated for both years (Amnesty, HRW, State all code Afghanistan); United States has all 3 populated and a different region code to exercise the 2-region-coverage path.
- **2 years**: 2022 and 2023 (the most recent two years in the xlsx; ensures all 3 indicator columns are populated).
- **Real-format data**: the 4 country-year rows' PTS scores and NA_Status codes are pulled from the live xlsx (no invented values). Example: Afghanistan 2022 has `PTS_A=4, PTS_H=5, PTS_S=5, NA_Status_A=0, NA_Status_H=0, NA_Status_S=0` (per live probe).
- **At least 1 inconsistency-case row**: a row with `PTS_X='NA'` AND `NA_Status_X=0` to exercise the §6 #4 warning path. The live xlsx has Bahamas 2017 as one such row; the test-builder can copy it or any other observed inconsistency row.
- **At least 1 NA_Status=88 row**: a row with a valid `PTS_X` but `NA_Status=88` to exercise the §6 #2 NA_Status-takes-precedence path. The live xlsx has many such rows (e.g., any country coded by Amnesty but not by HRW); the test-builder copies one.

> **Fixture creation by slicing, not authoring.** The test fixture MUST be created by opening the real xlsx with `openpyxl`, iterating rows, and writing a subset to a new xlsx — NOT by hand-authoring cells. This preserves the real format quirks (mixed int/str PTS_X cells, the exact `'NA'` string sentinel, the exact NA_Status integer encoding). A hand-authored fixture would diverge from the real format and mask bugs that only manifest on the real xlsx. This is the same source-of-truth principle as the WGI fixture (real WGI values, sliced with openpyxl).

> **Why `openpyxl`, not `pandas.to_excel`?** `pandas.to_excel` coerces all string cells to objects and may lose the mixed int/str cell type. `openpyxl` preserves the cell types exactly (int stays int, `'NA'` stays str). The test fixture must preserve the real-format quirks.

Total cells in the fixture data: 2 countries × 2 years × 3 indicators = **12 indicator cells** (4 rows × 3 PTS columns), plus the NA_Status columns. The orchestrator writes 4 country-year rows × 3 indicators = **12 `source_observations` rows** when reading the full fixture (no year filter) and 2 × 3 = **6 rows** when filtering to `year=2023`.

---

## 4 — Data flow

```
[PTS-2025.xlsx]
       |
       |  openpyxl.load_workbook(read_only=True, data_only=True)
       v
[long-format DataFrame]
       |   columns: Country, COW_Code_A, Year, Region, PTS_A, PTS_H, PTS_S,
       |            NA_Status_A, NA_Status_H, NA_Status_S
       |   rows: 10,531 (real xlsx) | 4 (test fixture)
       |
       |  read_pts() in pts_xlsx.py:
       |    1. iterate openpyxl rows (streaming)
       |    2. for each row: coerce PTS_X to int or None per §6 sentinel matrix
       |    3. apply NA_Status filter (drop indicator if NA_Status_X != 0)
       |    4. long -> wide pivot on (COW_Code_A, Year) with 3 indicator columns
       v
[wide-format DataFrame]
       |   columns: country, year, pts_amnesty_score, pts_human_rights_watch_score,
       |            pts_state_dept_score (+ pts.attrs["_pts_raw_long"] for raw audit)
       |
       |  write_pts_parquet() in pts_io.py:
       |    df.to_parquet (snappy compression)
       |    + pyarrow schema.metadata: pts_attribution, pts_source_key
       v
[data/processed/pts/pts_country_year.parquet]
       |
       |  open DB session:
       |    register_pts_source()  -> upsert sources row (idempotent)
       |    write_pts_observations() -> one SourceObservation per (country, year, indicator)
       v
[source_observations table: 12 rows (fixture) | ~1200-600 rows (real 2023 subset)]
       |
       |  write_pts_run_manifest() -> audit JSON
       v
[data/processed/pts/pts_run_manifest.json]
```

The data flow is a **single linear pass** through the xlsx (streaming via `openpyxl.read_only=True`), then a long-to-wide pivot, then parquet write, then DB writes. No HTTP layer (the xlsx is staged locally; the download workflow uses `curl`). No aggregation (unlike UCDP's event-to-country-year aggregation; PTS is already country-year). No region filter (unlike SIPRI milex; the 8 region values are all countries, not aggregates).

---

## 5 — Module structure (WGI-style 4-module split with xlsx reader)

PTS is structurally closer to **WGI** (one local xlsx, no network, no HTTP layer) than to WDI (per-indicator HTTP, JSON cache) or UCDP (event-level aggregation). The WGI 4-module split (`wgi.py` / `wgi_io.py` / `wgi_xlsx.py` / `wgi_db.py`) plus an optional `wgi_db_helpers.py` is the template. PTS splits into **4 sibling files** under `src/leaders_db/ingest/`, each under the 400-line convention from [`docs/coding-guidelines.md`](../coding-guidelines.md):

| File | Responsibility | Approx LoC target |
|---|---|---|
| `pts.py` | Public orchestrator: `PtsIngestResult` Pydantic model, `attribution()`, `ingest_pts()` entrypoint. Re-exports `PTS_ATTRIBUTION`, `PTS_SOURCE_KEY`, `IndicatorSpec` from the I/O module. | ~200–260 |
| `pts_io.py` | Catalog, path helpers, parquet write, parquet metadata attachment, the `default_xlsx_path()` and `default_processed_parquet_path()`. Owns `PTS_ATTRIBUTION`, `PTS_SOURCE_KEY`, `IndicatorSpec`, the catalog loader, the `_DEFAULT_CATALOG_PATH`, the `_RAW_XLSX_NAME`, the `_PROCESSED_PARQUET_NAME`, the parquet metadata keys, and the 6-region / 7-region / NA_Status / indicator-name constants (see §11 #11). | ~280–340 |
| `pts_xlsx.py` | xlsx read with `openpyxl.read_only=True`, the single-pass row iteration, the §6 sentinel matrix (4-case precedence rule), the long-to-wide pivot, the `_pts_raw_long` audit attr attachment. | ~200–280 |
| `pts_db.py` | `sources` upsert, `source_observations` write, run manifest, missing-value coercion (the `_coerce_pts_value` helper for the int 1-5 OR 'NA' OR None cell types). The missing-value coercion is small (3 cases) and lives in `pts_db.py`; no separate `_helpers.py` unless the module grows past 350 lines. | ~280–340 |
| **No `pts_db_helpers.py`** | (Optional; only if `pts_db.py` exceeds 350 lines during implementation.) | (0 or ~100–150) |

> **Why 4 modules, not 3 (WGI pattern with `pts_io` + `pts_xlsx`)?** PTS has the same WGI-style split: catalog + paths in `pts_io`, xlsx-specific reader in `pts_xlsx`. The DB layer is in `pts_db` (same as `wgi_db`). The orchestrator is in `pts.py`. This is the closest prior pattern: WGI uses exactly the same 4-module split (`wgi.py` / `wgi_io.py` / `wgi_xlsx.py` / `wgi_db.py`). The `wgi_db_helpers.py` was added later when `wgi_db.py` grew past 350 lines; the developer adds `pts_db_helpers.py` only if `pts_db.py` exceeds 350 lines during implementation (the default is 4 modules, not 5).

> **Why no `pts_http.py`?** PTS has no HTTP layer. The xlsx is staged locally; the read orchestrator opens the xlsx and walks the rows. Same as WGI / SIPRI milex / SIPRI Yearbook Ch.7's pattern (no `_http.py`).

> **No new project dependencies.** PTS uses the same dependencies as WGI: `openpyxl`, `pandas`, `pyarrow`, `pydantic`, `sqlalchemy`. No `pdfplumber` (that was SIPRI Yearbook Ch.7's addition). No new `pyproject.toml` changes.

The split rationale is identical to WGI: `pts_io` owns the data-lake and the I/O contract; `pts_xlsx` owns the xlsx-specific reader; `pts_db` owns the DB contract; `pts.py` is the orchestrator that wires them together. Constants live in `pts_io` (lowest level) to break the import cycle, and are re-exported by `pts.py` for the public surface.

### Read pattern — chosen approach: **single-pass openpyxl iteration → 3-indicator wide pivot**

The PTS xlsx is already in long format (one row per country-year). The read function performs:

1. **Open the xlsx once** with `openpyxl.load_workbook(..., read_only=True, data_only=True)`. The xlsx is 572 KB and fits in memory; the per-row iteration is row-by-row streaming (memory-efficient for the 10k+ rows).
2. **Iterate the single sheet** (`PTS-2025`). For each row:
   a. Extract `Country`, `COW_Code_A`, `Year`, `Region` (the 4 identity columns).
   b. For each of the 3 indicator pairs (`PTS_X`, `NA_Status_X`):
      - Apply the §6 sentinel matrix (4-case precedence rule) to coerce the cell to `int 1-5 | None`.
      - Append `(country, year, variable_name, value)` to a long frame.
   c. Carry the pre-coercion `PTS_X` and `NA_Status_X` cell text in a separate `raw_lookup` dict for the `source_observations.raw_value` audit trail (the WGI / SIPRI milex / SIPRI Yearbook Ch.7 pattern).
3. **Pivot to wide format** (one row per `(COW_Code_A, Year)`, one column per catalog `variable_name`). The `country` column carries the display name (PTS `Country`); the `cow_code` column carries `COW_Code_A` for `source_row_reference`. The `region` column carries the Region code (audit metadata, not extracted as an indicator).
4. **Coerce** the indicator columns to `Int64` (nullable integer; `pd.NA` for the sentinel cases). The `year` column is `int`.
5. **Filter** by year if `year=` is passed (default: keep all years; for the 2023 prototype, the orchestrator passes `year=2023` to get 215 rows).
6. **Attach `df.attrs["_pts_raw_long"]`**: the pre-coercion long frame (or a compact `{(country, year, variable_name): raw_cell_text}` lookup dict) for the `raw_value` audit trail. This attr is JSON-serializable when built as the lookup-dict form (preferred for pyarrow parquet-write compatibility).

The Stage 2 → Stage 11 contract: `confidence` is left `NULL` on every row; Stage 11 fills it. `country_id` is left `NULL`; Stage 3 (country match) fills it from `COW_Code_A` via the canonical country table. The wide frame's `country` column carries the raw PTS `Country` display name; the `source_row_reference` carries `"pts:<COW_Code_A>"` (e.g., `"pts:USA"`).

---

## 6 — Sentinel handling (the PTS-specific data quirk)

PTS uses a **two-signal sentinel pattern**: every indicator cell has a `PTS_X` value (int 1-5 or str `'NA'`) AND a paired `NA_Status_X` code (int 0/66/77/88/99). The precedence rule is **NA_Status takes precedence**: a row's indicator is "valid data" iff `NA_Status_X == 0`. The 4-case matrix below is the design contract.

### 6.1 — The 4-case sentinel matrix (the §6 table)

| # | `PTS_X` | `NA_Status_X` | Stage 2 handling | Audit trail (`raw_value`) |
|---|---|---|---|---|
| 1 | int 1-5 | 0 (present) | **valid; keep the indicator** | `str(int)` (e.g., `"3"`) |
| 2 | int 1-5 | != 0 (66/77/88/99) | **drop the indicator** (NA_Status takes precedence) | `str(int)` (audit shows the published value; Stage 5 sees the NA_Status and skips; the inconsistency is logged) |
| 3 | str `'NA'` | != 0 (66/77/88/99) | **drop the indicator** (the sentinel was a missing-value flag, and NA_Status confirms it) | `"NA"` (literal string preserved per the V-Dem / WGI / SIPRI milex / SIPRI Yearbook Ch.7 audit-trail pattern) |
| 4 | str `'NA'` | 0 (present) | **drop the indicator AND log a warning** (the inconsistency case: the cell says `'NA'` but the provenance flag says "present") | `"NA"` (literal string preserved) |

> **Why is case 4 an inconsistency, not valid data?** The xlsx's contract is: `NA_Status=0` means "PTS has coded this country-year and the value is in PTS_X". If `PTS_X='NA'` AND `NA_Status=0`, the row is contradictory: the provenance flag says the data exists, but the value cell says it's missing. The architect's probe found this case in the live xlsx (Bahamas 2017 has `PTS_A='NA'` and `NA_Status_A=0`); it is a real but rare data-entry error in the PTS xlsx. The Stage 2 read function logs a warning with the country, year, and indicator, then treats the indicator as missing (case 3 behavior). This is the "no silent fallbacks" rule from Constraint #2: every fall-through must log and emit a warning, not silently default.

### 6.2 — Implementation note: the `_coerce_pts_value` helper

The sentinel matrix is implemented in a single helper in `pts_xlsx.py` (and mirrored in `pts_db.py` for the DB write):

```python
def _coerce_pts_value(
    pts_cell: object, na_status: int,
    *, country: str, year: int, indicator: str,
) -> int | None:
    """Apply the 4-case sentinel matrix.

    Returns the int 1-5 for valid cells, None for missing/inconsistent.
    Logs a warning for case 4 (the inconsistency case).
    """
    if na_status != 0:
        # Cases 2 and 3: NA_Status takes precedence; drop the indicator.
        return None
    if isinstance(pts_cell, int) and 1 <= pts_cell <= 5:
        # Case 1: valid data.
        return pts_cell
    if pts_cell == "NA":
        # Case 4: inconsistency. Log and treat as missing.
        _logger.warning(
            "PTS data inconsistency: country=%s year=%d indicator=%s "
            "has PTS_X='NA' with NA_Status=0. Treating as missing.",
            country, year, indicator,
        )
        return None
    # Defensive: anything else (e.g., a float, a different string).
    # Treat as missing and log.
    _logger.warning(
        "PTS unexpected cell value: country=%s year=%d indicator=%s "
        "PTS_X=%r NA_Status=%d. Treating as missing.",
        country, year, indicator, pts_cell, na_status,
    )
    return None
```

### 6.3 — `raw_value` audit trail (the per-cell text)

For each `(country, year, variable_name)` triple, the Stage 2 read function captures the **pre-coercion** cell text in a lookup dict (`df.attrs["_pts_raw_lookup"]` or a `df.attrs["_pts_raw_long"]` long frame), so the DB write can populate `source_observations.raw_value` with the original cell text. The mapping is:

| Case | `raw_value` (the audit-trail string in `source_observations.raw_value`) |
|---|---|
| 1 (valid) | `str(int_value)` (e.g., `"3"`) |
| 2 (NA_Status != 0 + int PTS_X) | `str(int_value)` (the published value, even though it's dropped; the `NA_Status` is recorded in `notes`) |
| 3 (NA_Status != 0 + 'NA' PTS_X) | `"NA"` (the literal string) |
| 4 (inconsistency) | `"NA"` (the literal string; the warning is in the run log) |

### 6.4 — Region codes (the architect flag for the developer)

The xlsx's `Region` column has **8 distinct values** in the live data (verified 2026-06-18):

| Code | Count | Meaning |
|---|---|---|
| `eap` | 1568 | East Asia & Pacific (World Bank code) |
| `eca` | 3087 | Europe & Central Asia |
| `lac` | 1666 | Latin America & Caribbean |
| `mena` | 1274 | Middle East & North Africa |
| `mena, ssa` | 49 | **Data anomaly: 2-region cell** (the African Union rows for 1976-2024) |
| `na` | 98 | North America |
| `sa` | 392 | South Asia |
| `ssa` | 2397 | Sub-Saharan Africa |

These are the **World Bank country-and-lending-groups codes**, NOT the 6 codes listed in the prompt and the metadata.json (`sa`/`ssa`/`eur`/`ame`/`apac`/`mena`). The prompt's list is an approximation; the live data uses the World Bank codes. The `mena, ssa` cell is a data anomaly (a comma-separated 2-region cell appearing 49 times for the African Union); it is passed through verbatim to `source_observations.notes` (the `region` column is preserved in the wide frame for the manual-review queue's region stratification, but is NOT extracted as an indicator).

> **Architect flag for the developer (Constraint #17):** The `metadata.json` and the prompt list 6 region codes; the live xlsx has 7 single-region codes + 1 anomaly. **The developer updates `metadata.json` to match the live data** in the same commit as the adapter lands, mirroring the WGI "1996–2023" → "1996–2022" docs fix pattern. The constant `_PTS_REGION_CODES` in `pts_io.py` reflects the 7 observed single-region codes (the anomaly is not in the constant; it's a defensive check).

> **The `mena, ssa` anomaly is preserved, not normalized.** Splitting the cell into 2 rows or filtering it out would lose the audit trail. The Stage 2 read function passes the literal string through to `source_observations.notes` (column: the `region` value, stored in the audit metadata). The manual-review queue can flag these rows for human review.

### 6.5 — NA_Status code semantics (the §6 reference table)

| Code | Semantics | Stage 2 handling | When seen (2023 example) |
|---|---|---|---|
| `0` | present (valid data) | use the `PTS_X` value | 157 rows (73%) |
| `66` | not covered (PTS does not code this country-year) | drop the indicator | 7 rows (3%) |
| `77` | country did not exist (e.g., USSR rows after 1991) | drop the indicator | 9 rows (4%) |
| `88` | not coded (the coder has no opinion) | drop the indicator | 42 rows (20%) |
| `99` | missing (data is genuinely unavailable) | drop the indicator | 0 rows (0% in 2023; rare in other years) |

> **All 5 codes must be in `_PTS_NA_STATUS_CODES`.** The constant lives in `pts_io.py` (Constraint #11 — named constants for the 5 NA_Status values used in 3+ places). The developer adds a defensive check: if a future xlsx release introduces a new code (e.g., a hypothetical `55`), the read function logs a warning and treats it as missing (the same "NA_Status != 0" precedence rule applies).

---

## 7 — Country resolution (the `COW_Code_A` linkage)

### 7.1 — The 4 ID columns in the xlsx

PTS gives 4 ISO/code columns per row:

| Col | Name | Example | Notes |
|---|---|---|---|
| 3 | `COW_Code_A` | `'AFG'` | Correlates of War alphabetic (3-letter); matches V-Dem's `country_text_id` |
| 4 | `COW_Code_N` | `700` | COW numeric |
| 5 | `WordBank_Code_A` | `'AFG'` | World Bank 3-letter (ISO3-style) |
| 6 | `UN_Code_N` | `4` | UN M49 numeric |

### 7.2 — The Stage 2 primary key: `COW_Code_A`

**Decision: Stage 2 uses `COW_Code_A` as the primary `country_id`-linking column**, and stores it in `source_row_reference` as `"pts:<COW_Code_A>"` (e.g., `"pts:USA"`). The 3 secondary columns (`COW_Code_N`, `WordBank_Code_A`, `UN_Code_N`) are kept in the wide frame's audit metadata but NOT used for the primary linkage.

**Justification:**

1. **V-Dem alignment.** V-Dem uses `country_text_id` (the COW alphabetic code) as its primary country key. Using `COW_Code_A` for PTS means Stage 3 (country match) can join PTS to V-Dem on the same key. This is the same alignment as UCDP's `country_id` (which uses UCDP's own numeric ID, NOT ISO3; the Stage 3 lookup handles the V-Dem and UCDP joins separately).
2. **Coverage.** `COW_Code_A` is populated for **every** row in the live xlsx (10,531/10,531); the other 3 columns are also fully populated, so coverage is not a discriminator.
3. **Backward compatibility.** `COW_Code_A` is the canonical 3-letter alphabetic code; downstream Stage 3 join logic can map it to ISO3 via the canonical country table.

### 7.3 — `country_id` is NULL at Stage 2

At Stage 2, `source_observations.country_id` is left **NULL** (Stage 3 fills it via the country-match step). The `source_row_reference` carries `"pts:<COW_Code_A>"` so Stage 3 can resolve it. This is the same pattern as WGI's `"wgi:MEX"`, V-Dem's `"vdem:<country_text_id>"`, UCDP's `"ucdp:<country_id>"`, SIPRI milex's `"sipri_milex:<display_name>"`, and SIPRI Yearbook Ch.7's `"sipri_yearbook_ch7:<display_name>"`. The **`<COW_Code_A>`** pattern is PTS-specific (V-Dem uses `country_text_id` which is also COW, but V-Dem's identifier is the V-Dem-internal ID; PTS's COW code is a different identifier space).

### 7.4 — The 3 secondary ID columns

The `COW_Code_N`, `WordBank_Code_A`, and `UN_Code_N` columns are preserved in the wide frame's audit metadata (via `df.attrs["_pts_id_lookup"]` or a dedicated lookup dict) so a future Stage 3 cross-validation can use them. The Stage 2 read function does NOT extract them as indicators.

### 7.5 — Stage 3 join table

Stage 3 maintains a `pts_country_iso3` lookup table (analogous to `ucdp_country_iso3.csv`) that maps `COW_Code_A` → ISO3. Stage 2 does not depend on this table; Stage 2's contract is to write the `COW_Code_A` verbatim.

---

## 8 — Test plan (what the test-builder writes)

The test plan covers the 6 Phase C convention #5 categories (catalog, xlsx read, wide frame, parquet write + DB, orchestrator end-to-end, drift-guard) plus the CLI dispatch and public surface. Every test has a defined fixture, an assertion, and a 1-line description. The WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 test files are the template (specifically `test_ingest_wgi.py` which is the closest xlsx-reader analog).

The test file will be `tests/test_ingest_pts.py`. The fixture will be `tests/fixtures/pts/sample.xlsx`.

### §8.1 — Catalog loader (3-4 tests)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_load_indicator_catalog_returns_3_specs` | The checked-in catalog has **3** indicators (matches §3 spec). | `pts_catalog_path` |
| `test_load_indicator_catalog_required_columns` | The 8 required CSV columns are present; `rating_category` is exactly `{"domestic_violence"}`; `higher_is_better` is `0` for all 3. | same |
| `test_load_indicator_catalog_missing_file` | Missing catalog raises `FileNotFoundError`, not a silent empty list. | `tmp_path` |
| `test_indicator_spec_from_csv_row` | `higher_is_better=0` round-trips to `False` (matching V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7). | inline dict |
| `test_catalog_raw_columns_match_pts_xlsx_headers` | The 3 `raw_column` values are exactly the xlsx header names: `PTS_A`, `PTS_H`, `PTS_S` (case-sensitive, no whitespace — SIPRI-milex lesson #16). | `pts_catalog_path` |

### §8.2 — xlsx reader (8-10 tests)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_pts_returns_full_fixture` | The fixture (2 countries × 2 years × 3 indicators) produces a wide DataFrame: 4 rows, 5 columns (`country`, `year`, `cow_code`, `region`, 3 indicator columns). | `pts_xlsx_dir` (stages the sample xlsx) |
| `test_read_pts_filters_to_year` | `year=2023` keeps only the 2 rows for 2023; `set(df["year"]) == {2023}`. | same |
| `test_read_pts_coerces_na_string_to_none` | A cell with `PTS_X='NA'` AND `NA_Status=88` (case 3) becomes `pd.NA` in the wide frame; `normalized_value` is `None` in `source_observations`. | same |
| `test_read_pts_coerces_na_status_dropped_int` | A cell with `PTS_X=3` (int) AND `NA_Status=88` (case 2) is dropped: the indicator is `pd.NA` even though the published value was 3. The audit trail preserves `"3"` in `raw_value`. | same |
| `test_read_pts_preserves_valid_int` | A cell with `PTS_X=4` AND `NA_Status=0` (case 1) becomes `4` in the wide frame; `normalized_value=4`, `raw_value="4"`. | same |
| `test_read_pts_warns_on_inconsistency` | A cell with `PTS_X='NA'` AND `NA_Status=0` (case 4) is dropped and a warning is logged with the country + year + indicator. The test captures the warning via `caplog`. | same (the fixture MUST have at least one case-4 row; see §3 fixture shape) |
| `test_read_pts_year_filter_returns_empty_for_out_of_range` | `year=1900` (out of the 1976-2024 range) returns an empty wide DataFrame with the expected column shape (no crash). | `pts_xlsx_dir` |
| `test_read_pts_missing_xlsx` | Missing xlsx raises `FileNotFoundError` with an actionable message. | `tmp_path` |
| `test_read_pts_handles_all_5_na_status_codes` | The fixture exercises all 5 NA_Status codes (0, 66, 77, 88, 99); each is coerced to missing or valid per §6. | `pts_xlsx_dir` (the test-builder extends the fixture to include rows with NA_Status=66, 77, 99) |
| `test_read_pts_preserves_8_region_codes` | The wide frame's `region` column includes all 7 single-region codes from the live data + the `'mena, ssa'` anomaly (the test asserts the anomaly is preserved verbatim, not normalized away). | `pts_xlsx_dir` (extended fixture with rows from 3+ regions) |

### §8.3 — Wide frame (4-5 tests)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_pts_wide_frame_columns_match_catalog` | The 3 indicator columns are named exactly `pts_amnesty_score`, `pts_human_rights_watch_score`, `pts_state_dept_score` (matching the catalog `variable_name` values verbatim). | `pts_xlsx_dir` |
| `test_read_pts_wide_frame_country_column` | The `country` column has the PTS `Country` display name verbatim (e.g., `"Afghanistan"`, `"United States"`). | same |
| `test_read_pts_wide_frame_year_column_is_int` | The `year` column is `int` (coerced from openpyxl's int cells). | same |
| `test_read_pts_wide_frame_cow_code_column` | The `cow_code` column has the `COW_Code_A` value (e.g., `"AFG"`, `"USA"`); `source_row_reference` is `"pts:<COW_Code_A>"`. | same |
| `test_read_pts_wide_frame_carries_raw_lookup_attr` | `df.attrs["_pts_raw_lookup"]` is a dict mapping `(country, year, variable_name) -> raw_cell_text`; the dict has at least 4 × 3 = 12 entries (one per country-year × indicator). | same |

### §8.4 — DB writers (4-5 tests)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_pts_parquet_creates_file` | `write_pts_parquet(df)` writes a valid parquet under `data/processed/pts/`; round-trip preserves shape and columns. | `pts_xlsx_dir` |
| `test_write_pts_parquet_attaches_attribution_metadata` | The parquet's file-level metadata carries `pts_attribution` (= `PTS_ATTRIBUTION`) and `pts_source_key` (= `b"pts"`) (Rule #15). | same |
| `test_register_pts_source_is_idempotent` | Two calls to `register_pts_source` return the same `sources.id`; the row has `source_name="Political Terror Scale (PTS)"`, `version="PTS-2025"`, `source_type="academic"`. | `database_url` + `_init_test_db` |
| `test_write_pts_observations_row_count` | `len(df) * len(specs)` observations are written. With the full fixture (4 rows × 3 indicators) the count is 12; after filtering to 2023 (2 rows × 3 indicators) the count is 6. | `pts_xlsx_dir` + `database_url` |
| `test_write_pts_observations_country_id_is_null` | `country_id` is `None` for every row (Stage 3 fills it); `confidence` is `None` for every row (Stage 11 fills it); `source_row_reference` starts with `"pts:"` and carries the `COW_Code_A`. | same |
| `test_write_pts_observations_is_idempotent` | Re-running `write_pts_observations` produces the same count, not 2× the count. | same |
| `test_write_pts_observations_preserves_raw_value` | `raw_value` is `"NA"` for case-3/case-4 cells; `raw_value` is `str(int)` for case-1/cells; the case-2 audit preserves the published int (e.g., `"3"`) even though the row was dropped. | same |
| `test_pts_ingest_result_field_count` | The `PtsIngestResult` has exactly 8 fields (matches §10 spec): `source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`, `regions_covered`, `year_window`. | same |

### §8.5 — Drift-guard (1 test)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_pts_attribution_matches_attributions_doc` | `PTS_ATTRIBUTION` is a substring of `docs/source-attributions.md` (drift guard, same pattern as V-Dem's `test_vdem_attribution_matches_attributions_doc`, WGI's `test_wgi_attribution_matches_attributions_doc`, UCDP's `test_ucdp_attribution_matches_attributions_doc`, SIPRI milex's `test_sipri_milex_attribution_matches_attributions_doc`, and SIPRI Yearbook Ch.7's `test_sipri_yearbook_ch7_attribution_matches_attributions_doc`). | project root |

### §8.6 — Test fixture shape (the contract for the test-builder)

The test-builder creates `tests/fixtures/pts/sample.xlsx` by **slicing the real `data/raw/political_terror_scale/PTS-2025.xlsx`** with `openpyxl`. The slicing helper script is committed as `tests/fixtures/pts/build_sample_xlsx.py` (idempotent: re-running overwrites the fixture). The fixture:

- **2 countries**: Afghanistan and United States.
- **2 years**: 2022 and 2023.
- **At least 1 case-4 row**: the test-builder can copy the live "Bahamas 2017" row (or any other observed case-4 row) to exercise the inconsistency path. **Note: the fixture's case-4 row must be one of the 4 country-year rows in the wide frame OR an additional row that the Stage 2 read function processes and drops.** The simplest approach: include a 5th country-year row (e.g., Bahamas 2017) in the fixture's 4 rows, replacing one of the 4 to keep the fixture at 4 rows; OR extend the fixture to 5 rows.
- **At least 1 case-2 row**: a row with `PTS_X=int` AND `NA_Status=88` (e.g., a country-year where HRW didn't code but Amnesty did). The test-builder copies a live row.
- **At least 1 row covering each region code**: the fixture should include rows from at least 2 different regions (e.g., `sa` for Afghanistan, `na` for United States) so the region-preservation test has coverage.
- **Real-format data**: no invented values. All PTS_X and NA_Status_X values are copied verbatim from the live xlsx.

> **Why slice, not author.** Constraint #12 says: "the test fixture must be a slice of the real data, not a hand-authored mock." Hand-authored values would diverge from the live xlsx's quirks (the `'NA'` string sentinel, the mixed int/str cell types, the exact NA_Status integer encoding) and mask bugs that only manifest on the real xlsx. The test-builder writes a 30-line `build_sample_xlsx.py` that does:
>
> ```python
> import openpyxl
> src = openpyxl.load_workbook("data/raw/political_terror_scale/PTS-2025.xlsx", read_only=True)
> dst = openpyxl.Workbook()
> dst_ws = dst.active
> dst_ws.title = "PTS-2025"
> # Copy header row + selected data rows
> for i, row in enumerate(src["PTS-2025"].iter_rows(values_only=True)):
>     if i == 0 or is_selected_row(row):
>         dst_ws.append(row)
> dst.save("tests/fixtures/pts/sample.xlsx")
> ```
>
> The committed fixture (`sample.xlsx`) is what the tests use; the script is the source of truth for the fixture's contents. This is the WGI fixture pattern (real-format xlsx, sliced with openpyxl).

### §8.7 — End-to-end smoke (1 test, gated on real xlsx)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_pts_end_to_end_against_real_xlsx_year_2023` | `ingest_pts(year=2023)` against the real 572 KB xlsx returns ~200 rows (215 total minus dropped cells) for the 3 indicators; the count of valid observations is approximately 157 + 108 + 197 = 462 (sum across 3 indicators; each is a separate row). The test asserts `len(df) == 215` (the 215 country rows for 2023) and `len(specs) == 3`. The full run writes 462 ± a-few `source_observations` rows. | `pts_xlsx_dir` (the fixture includes the real 572 KB xlsx; gated on file presence) |

> **The end-to-end smoke is gated on the real xlsx on disk.** The test skips if the real `data/raw/political_terror_scale/PTS-2025.xlsx` is not present (the `isolated_data_lake` fixture overrides `LEADERSDB_PROJECT_ROOT`; the test only runs when the real xlsx is at the data-lake path). This is the WGI smoke pattern (live-xlsx smoke gated on file presence).

### §8.8 — Orchestrator end-to-end (Phase C convention #5d)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_ingest_pts_end_to_end` | `ingest_pts()` writes the parquet, the sources row, the 12 `source_observations` rows (full fixture), and the manifest in one call. Result has `countries=2, years=(2022,2023), indicators=3, regions_covered=[...], year_window=(2022,2023)`. | `pts_xlsx_dir` + `database_url` |
| `test_ingest_pts_filters_to_year` | `year=2023` keeps 2 countries × 1 year × 3 indicators = 6 observation rows; `result.years == (2023,)`. | same |
| `test_ingest_pts_is_idempotent` | Two consecutive `ingest_pts()` calls produce the same `observation_rows` count, the same `source_id`, and the parquet's mtime is the same (no re-write). | same |
| `test_ingest_pts_result_carries_attribution` | The `PtsIngestResult.attribution` property returns `PTS_ATTRIBUTION` byte-for-byte; `result.attribution == PTS_ATTRIBUTION`. | same |
| `test_ingest_pts_result_carries_regions_and_year_window` | The `PtsIngestResult.regions_covered` is a sorted list of the 2 region codes in the fixture; the `year_window` is `(2022, 2023)`. | same |

### §8.9 — CLI dispatch

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_stage2_adapters_dispatch_table` | `STAGE2_ADAPTERS["pts"] is pts.ingest_pts`; the full key set is unchanged (25 keys, with the `pts` value changing from `None` to the orchestrator). The existing `"pts": None,` line in `__init__.py` is REPLACED, not duplicated. | — |
| `test_cli_ingest_source_rejects_unknown` | `leaders-db ingest-source --source nope` exits non-zero. | `CliRunner` |

### §8.10 — Public surface

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_pts_module_public_surface` | The `pts` module exports the items in `__all__` from §10: `PTS_ATTRIBUTION`, `PTS_SOURCE_KEY`, `IndicatorSpec`, `PtsIngestResult`, `attribution`, `ingest_pts`, `register_pts_source`, `write_pts_observations`, `write_pts_run_manifest`. | — |

### Live-xlsx smoke (manual, not in pytest)

| Test name | What it asserts | When |
|---|---|---|
| `manual: smoke PTS end-to-end against real xlsx for 2023` | `ingest_pts(year=2023)` against the real 572 KB xlsx returns 215 country rows for 2023, of which ~462 `source_observations` rows are written (157 amnesty + 108 HRW + 197 State); `result.countries == 215`, `result.indicators == 3`, `result.regions_covered` contains all 7 single-region codes + the `'mena, ssa'` anomaly. | After implementation, manual one-shot, recorded in `docs/testing-guide-stage2-pts.md` |

The manual smoke is gated on a real on-disk xlsx (already on disk at `data/raw/political_terror_scale/PTS-2025.xlsx`). The test fixture (`tests/fixtures/pts/sample.xlsx`) is a 4-row slice that fits in <10 KB and is what the unit tests use. The unit tests prove the contract; the manual smoke proves the real xlsx still works.

---

## 9 — Public surface (exact function signatures)

The test-builder writes against these signatures; the developer implements against these signatures. The names and types are the contract; the docstrings below describe the contract for both audiences.

### 9.1 — Constants (in `pts_io.py`, re-exported by `pts.py`)

```python
PTS_SOURCE_KEY: str = "pts"
```

The single source key used everywhere in the data lake, the CLI dispatch, and the test imports. Matches the `--source` CLI flag. The data lake folder name is `political_terror_scale/` (the human-readable bundle name); the source key is the dispatch key.

```python
PTS_ATTRIBUTION: str = (
    "Wood, Reed M., Mark Gibney, and others. "
    "The Political Terror Scale (PTS). "
    "https://www.politicalterrorscale.org/"
)
```

The exact citation text. Lives in `pts_io` to break the import cycle. The canonical long-form lives in [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `pts`; the drift-guard test `test_pts_attribution_matches_attributions_doc` (§8.5) enforces byte-for-byte consistency. **The text above is byte-identical to the citation in the doc; the developer copies it verbatim into the constant.**

```python
#: Default location of the indicator catalog.
_DEFAULT_CATALOG_PATH: Path = Path(__file__).resolve().parent / "catalogs" / "pts.csv"

#: Raw xlsx file name inside ``data/raw/political_terror_scale/``.
_RAW_XLSX_NAME: str = "PTS-2025.xlsx"

#: Narrow parquet that Stage 2 writes under ``data/processed/pts/``.
_PROCESSED_PARQUET_NAME: str = "pts_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "pts_attribution"
_PARQUET_META_SOURCE_KEY: str = "pts_source_key"

#: The 3 indicator names (used in 3+ places; named constant per Constraint #11).
_PTS_INDICATOR_NAMES: frozenset[str] = frozenset({
    "PTS_A", "PTS_H", "PTS_S",
})

#: The 7 single-region codes observed in the live xlsx (Constraint #11).
#: The 'mena, ssa' anomaly is NOT in this set; it is preserved verbatim
#: in source_observations.notes per §6.4.
_PTS_REGION_CODES: frozenset[str] = frozenset({
    "eap", "eca", "lac", "mena", "na", "sa", "ssa",
})

#: The 5 NA_Status code values (Constraint #11). A cell is valid iff
#: NA_Status_X == 0 (case 1 in §6.1). All other values drop the indicator.
_PTS_NA_STATUS_CODES: frozenset[int] = frozenset({0, 66, 77, 88, 99})
```

### 9.2 — Indicator catalog (in `pts_io.py`)

```python
@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the PTS indicator catalog.

    The V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7
    :class:`IndicatorSpec` shape is reused verbatim: every Stage 2
    adapter resolves its raw column from this dataclass so the
    score modules in Stage 9-10 can normalize and direct indicators
    consistently across sources.
    """
    variable_name: str
    raw_column: str
    rating_category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str
    description: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "IndicatorSpec": ...
```

```python
def load_indicator_catalog(catalog_path: Path | None = None) -> list[IndicatorSpec]:
    """Load the PTS indicator catalog from ``catalogs/pts.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7
    loaders: handles the leading ``#`` comment block, drops comment-only
    lines, validates the required column set, and returns one
    :class:`IndicatorSpec` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
```

### 9.3 — Read (in `pts_xlsx.py` and re-exported by `pts_io.py`)

```python
def read_pts(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read PTS from the xlsx and pivot to wide format (one row per country per year).

    Steps:

    1. Load the catalog.
    2. Open the xlsx at ``xlsx_path`` (default: data-lake path).
    3. Iterate the single ``PTS-2025`` sheet with ``openpyxl.read_only=True``.
    4. For each row, apply the §6 sentinel matrix to coerce each of the 3
       indicator cells (case 1: int 1-5 + NA_Status=0 → int; case 2: int
       1-5 + NA_Status != 0 → drop; case 3: 'NA' + NA_Status != 0 → drop;
       case 4: 'NA' + NA_Status=0 → drop + log warning).
    5. Pivot to wide format: one row per ``(COW_Code_A, Year)``, one
       column per catalog ``variable_name``.
    6. Coerce the ``year`` column to ``int`` and the indicator columns
       to ``Int64`` (nullable; ``pd.NA`` = missing per §6).
    7. Attach ``df.attrs["_pts_raw_lookup"]`` (the pre-coercion raw cell
       text lookup dict) for the ``source_observations.raw_value`` audit
       trail.

    Args:
        year: filter to a single year (e.g., ``2023``). Default: all years
            present in the xlsx (1976-2024, 49 distinct years).
        xlsx_path: override the input xlsx. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.

    Returns:
        A pandas DataFrame with columns ``country`` (display name string),
        ``cow_code`` (the ``COW_Code_A`` 3-letter code, used for
        ``source_row_reference``), ``year`` (int), ``region`` (the Region
        code; audit metadata, not an indicator), then one column per
        catalog indicator (named with the ``variable_name``). Indicator
        columns are ``Int64`` (nullable; ``pd.NA`` = missing per §6).
        The wide frame is dense: every (country, year) cross-product
        row from the xlsx is present, even when all 3 indicator cells
        are missing.

    Raises:
        FileNotFoundError: if the xlsx is missing.
        ValueError: if the xlsx has no sheet named ``PTS-2025``.
    """
```

### 9.4 — Path helpers (in `pts_io.py`)

```python
def default_xlsx_path() -> Path:
    """Return the conventional PTS xlsx path inside the data lake.

    Resolves to ``<project_root>/data/raw/political_terror_scale/PTS-2025.xlsx``.
    Raises ``FileNotFoundError`` if the file is missing (per the design
    contract in §9.3); the adapter expects the user to have downloaded
    the xlsx via the project's download workflow first.
    """


def default_processed_parquet_path() -> Path:
    """Return the conventional PTS narrow parquet path.

    Creates the ``data/processed/pts/`` directory if missing.
    """
```

### 9.5 — Parquet write (in `pts_io.py`)

```python
def write_pts_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet`,
    :func:`wgi_io.write_wgi_parquet`,
    :func:`sipri_milex_io.write_sipri_milex_parquet`, and
    :func:`sipri_yearbook_ch7_io.write_sipri_yearbook_ch7_parquet`:
    writes the parquet via ``df.to_parquet``, then re-writes the file
    with the PTS attribution + source key attached as file-level
    schema metadata (Rule #15). Best-effort on the metadata rewrite —
    if pyarrow fails, the data parquet is still valid and a warning is
    logged.

    The ``_pts_raw_lookup`` attr (carried in ``df.attrs`` by
    :func:`pts_xlsx.read_pts`) is intentionally stripped before the
    write (the lookup dict is non-JSON-serializable when it contains
    int keys; the raw_value audit trail is reconstructed from
    ``source_observations``).
    """
```

### 9.6 — DB writes (in `pts_db.py`)

```python
def register_pts_source(session: Session) -> int:
    """Upsert the PTS source row into the ``sources`` table.

    Keyed by ``(source_name='Political Terror Scale (PTS)',
    version='PTS-2025')``. Idempotent: returns the same ``sources.id``
    on every call. Reads the bundle's ``metadata.json`` for
    ``source_url``, ``download_date``, ``license_note``,
    ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source`, WGI's
    :func:`wgi_db.register_wgi_source`, UCDP's
    :func:`ucdp_db.register_ucdp_source`, SIPRI milex's
    :func:`sipri_milex_db.register_sipri_milex_source`, and SIPRI
    Yearbook Ch.7's :func:`sipri_yearbook_ch7_db.register_sipri_yearbook_ch7_source`).
    """


def write_pts_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    Same shape as V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7:

    - ``country_id`` is left ``NULL``; Stage 3 (country match) fills it
      from the PTS ``COW_Code_A`` via the country lookup table (a
      future Stage 3 deliverable).
    - ``source_row_reference`` carries the ``COW_Code_A`` prefixed with
      ``"pts:"`` (e.g., ``"pts:USA"``) so Stage 3 can resolve it.
    - ``raw_value`` preserves the original cell text per the §6.3
      audit-trail matrix.
    - ``normalized_value`` is the int 1-5, or ``None`` if the cell is
      missing per §6 (any of the 4 cases that drop the indicator).
    - Idempotent: deletes existing rows for the requested years (from
      the frame) before inserting. Years outside the frame are
      untouched.

    Returns the number of ``source_observations`` rows inserted.
    """


def write_pts_run_manifest(
    result,  # PtsIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest is the audit trail for ``processed/``: it records
    ``source_id``, the parquet path, the observation row count, the
    countries count, the years, the indicator count, the
    ``regions_covered``, the ``year_window``, the catalog path, and
    the attribution. Written every run (not best-effort) so Stage 15
    reports can find the attribution without re-reading the parquet
    metadata.
    """
```

### 9.7 — Orchestrator and Pydantic result (in `pts.py`)

```python
class PtsIngestResult(BaseModel):
    """Summary of a single ``ingest_pts`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads these
    fields to print the end-of-run summary, and the manifest writer in
    :mod:`pts_db` consumes the same fields. Same shape as V-Dem's
    :class:`vdem.IngestResult`, WGI's :class:`wgi.WGIIngestResult`,
    UCDP's :class:`ucdp.UCDPIngestResult`, SIPRI milex's
    :class:`sipri_milex.SipriMilexIngestResult`, and SIPRI Yearbook
    Ch.7's :class:`sipri_yearbook_ch7.SipriYearbookCh7IngestResult`
    for consistency.

    PTS-specific extras vs the WGI :class:`WGIIngestResult`:

    - ``regions_covered``: a sorted list of the Region codes found in
      the wide frame (e.g., ``["lac", "mena", "sa", "ssa"]``). Carried
      forward from ``df.attrs["regions_covered"]``. The 7 single-region
      codes plus the ``'mena, ssa'`` anomaly are preserved verbatim;
      the constant `_PTS_REGION_CODES` (7 codes) is the canonical set.
    - ``year_window``: a ``(start_year, end_year)`` tuple representing
      the min/max year in the wide frame (e.g., ``(2022, 2023)`` for
      a 2-year filtered run, or ``(1976, 2024)`` for the full unfiltered
      run). Carried forward from ``df.attrs["year_window"]``. Useful
      for confirming the wide frame's temporal coverage.

    These are the PTS-specific equivalents of UCDP's
    ``events_total`` / ``events_filtered` and SIPRI milex's
    ``regions_covered`` / ``country_count``: they capture the
    audit-trail metadata for end-to-end audit.

    Fields: 8 total.
    """
    source_id: int = Field(..., ge=1, description="The ``sources.id`` row created/updated.")
    parquet_path: Path = Field(..., description="Path to the narrow PTS parquet.")
    observation_rows: int = Field(..., ge=0, description="Number of ``source_observations`` rows written by this run.")
    countries: int = Field(..., ge=0, description="Distinct ``COW_Code_A``s in the narrow frame.")
    years: tuple[int, ...] = Field(..., description="Years included in the run, sorted.")
    indicators: int = Field(..., ge=0, description="Number of catalog indicators used.")
    regions_covered: list[str] = Field(
        default_factory=list,
        description="Sorted list of Region codes found in the wide frame.",
    )
    year_window: tuple[int, int] = Field(
        ...,
        description="(start_year, end_year) tuple representing the min/max year in the wide frame.",
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]: ...

    @field_validator("regions_covered")
    @classmethod
    def _regions_covered_is_sorted_unique(cls, value: list[str]) -> list[str]: ...

    @field_validator("year_window")
    @classmethod
    def _year_window_is_ordered_pair(cls, value: tuple[int, int]) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("year_window must be a 2-tuple")
        if value[0] > value[1]:
            raise ValueError("year_window must have start <= end")
        return value

    @property
    def attribution(self) -> str:
        """The PTS attribution text (Always-On Rule #15)."""
        return PTS_ATTRIBUTION
```

> **Note on the IngestResult field count.** V-Dem / WGI have 6 fields. WDI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 have 8 fields (each adds 2 source-specific extras). PTS has **8 fields** (6 from WGI plus `regions_covered` and `year_window` for the region + temporal audit trail). The end-to-end test asserts all 8.

```python
def attribution() -> str:
    """Return the PTS attribution block for public output (Rule #15)."""


def ingest_pts(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> PtsIngestResult:
    """Run Stage 2 for PTS end-to-end.

    Steps (each idempotent):

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_pts`. Open the xlsx
       with ``openpyxl.read_only=True``, iterate the single sheet,
       apply the §6 sentinel matrix, pivot long → wide.
    3. Write the narrow parquet under ``data/processed/pts/`` and
       attach the PTS attribution to the parquet's file-level metadata.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Build the :class:`PtsIngestResult` and write the run manifest.
    6. Return the result.

    The function is the single public entry point — both the CLI
    command ``leaders-db ingest-source --source pts`` and the tests
    call it. The DB session resolves through :func:`session_scope`,
    which honors the ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g., ``2023``). Default: all years.
        xlsx_path: override the input xlsx. Default: data-lake path.
        parquet_path: override the output parquet. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.
    """
```

### 9.8 — `__all__` (in `pts.py`)

```python
__all__ = [
    "PTS_ATTRIBUTION",
    "PTS_SOURCE_KEY",
    "IndicatorSpec",
    "PtsIngestResult",
    "attribution",
    "default_xlsx_path",
    "default_processed_parquet_path",
    "ingest_pts",
    "load_indicator_catalog",
    "read_pts",
    "register_pts_source",
    "write_pts_observations",
    "write_pts_parquet",
    "write_pts_run_manifest",
]
```

---

## 10 — Acceptance criteria (Phase C.7 done)

Phase C.7 is done when **all** of the following are true:

- [ ] `src/leaders_db/ingest/pts.py` exists, imports cleanly, and is under 400 lines.
- [ ] `src/leaders_db/ingest/pts_io.py` exists, imports cleanly, and is under 400 lines.
- [ ] `src/leaders_db/ingest/pts_xlsx.py` exists, imports cleanly, and is under 400 lines.
- [ ] `src/leaders_db/ingest/pts_db.py` exists, imports cleanly, and is under 400 lines.
- [ ] (Optional) `src/leaders_db/ingest/pts_db_helpers.py` exists ONLY if `pts_db.py` exceeds 350 lines during implementation.
- [ ] `src/leaders_db/ingest/catalogs/pts.csv` exists with exactly 3 data rows + 1 header row + comment block.
- [ ] `STAGE2_ADAPTERS["pts"]` in `src/leaders_db/ingest/__init__.py` is `pts.ingest_pts` (replacing the existing `"pts": None` stub).
- [ ] `tests/test_ingest_pts.py` exists with ~30-35 tests across the 6 categories in §8 (catalog, xlsx read, wide frame, parquet+DB, orchestrator, drift-guard).
- [ ] `tests/fixtures/pts/sample.xlsx` exists, is created by slicing the real `PTS-2025.xlsx` (not hand-authored), and is <50 KB.
- [ ] `pytest -q tests/test_ingest_pts.py` passes (all green).
- [ ] `pytest -q` passes for the full suite (no regressions in the prior 252 tests).
- [ ] `PTS_ATTRIBUTION` is byte-identical to the citation in `docs/source-attributions.md` §1 (drift-guard test green).
- [ ] No new project dependencies added to `pyproject.toml` (PTS uses the same deps as WGI: `openpyxl`, `pandas`, `pyarrow`, `pydantic`, `sqlalchemy`).
- [ ] `ruff check` passes on all new modules.
- [ ] No `print()` calls in `src/leaders_db/ingest/pts*.py` (use `logging`; the orchestrator prints the result JSON to stdout ONLY at CLI end-of-run via the `cli.py` boundary, like V-Dem does).
- [ ] No `# type: ignore` comments in the new modules.
- [ ] No `TODO(debug)`, no commented-out code, no "fix later" notes.
- [ ] The `metadata.json` in `data/raw/political_terror_scale/` is updated to reflect the live-data region codes (7 single-region codes + the `'mena, ssa'` anomaly) per Constraint #17.
- [ ] The run-manifest at `data/processed/pts/pts_run_manifest.json` is written on every orchestrator call.
- [ ] Manual smoke against the real 572 KB xlsx for `year=2023` produces 215 country rows × 3 indicators = ~462 `source_observations` rows (summed across 3 indicators). Recorded in `docs/testing-guide-stage2-pts.md`.
- [ ] D2 review (per [`docs/coding-guidelines.md`](../coding-guidelines.md) review checklist) passes with no blockers.

---

## 11 — Out of scope (what the adapter does NOT do)

The PTS Stage 2 adapter explicitly does NOT do the following (per the architect's contract):

1. **Collapse to a worst-of-three indicator.** PTS contributes 3 separate indicators (`pts_amnesty_score`, `pts_human_rights_watch_score`, `pts_state_dept_score`); the Stage 5 score module may compute a "worst-of-three" or "median" as a derived metric, but Stage 2 writes all 3 raw values.

2. **Compute coder-disagreement indices.** The disagreement between the 3 PTS scores (e.g., the standard deviation across the 3 values) is a useful Stage 14 / Stage 5 derived metric, but Stage 2 does not compute it.

3. **Resolve `COW_Code_A` to ISO3.** Stage 3 (country match) does this; Stage 2 stores the `COW_Code_A` verbatim in `source_row_reference`.

4. **Normalize the `mena, ssa` anomaly.** The multi-region cell is passed through verbatim to `source_observations.notes` (via the `region` column). Splitting it into 2 rows would lose the audit trail; the manual-review queue flags it for human review.

5. **Download the xlsx.** The adapter assumes the xlsx is pre-staged at `data/raw/political_terror_scale/PTS-2025.xlsx`; the download workflow uses `curl` (or the project's `scripts/` helpers).

6. **Apply score inversion (1-5 → 0-10).** Stage 2 writes the raw 1-5 value to `source_observations.normalized_value`. The Stage 5 score module applies the inversion (`higher_is_better=False`).

7. **Compute confidence scores.** Stage 11 fills `confidence`; Stage 2 leaves it `NULL`.

8. **Mutate the schema.** The orchestrator does NOT DROP/CREATE indexes or tables (Constraint #1). It uses SQLAlchemy upserts via the migrations system.

9. **Cross-validate with V-Dem repression or UCDP one-sided.** The Stage 12 cross-source comparison reads all `domestic_violence` indicators (UCDP's 2 + V-Dem's 3 + PTS's 3) and computes agreement; Stage 2 does not perform cross-source validation.

10. **Extend the catalog beyond 3 indicators.** A 4th indicator (e.g., a coder-disagreement index) is a future 1-row catalog extension. The 3-indicator choice is locked for the prototype.

---

## 12 — Constraints (the 16+3 architect checklist)

These are the 16 constraints from the prompt, addressed one paragraph each. The 3 additional live-data constraints (#17, #18, #19) are the architect's findings from probing the real xlsx.

### #1 — No schema mutation (Constraint #1)

The orchestrator does NOT DROP/CREATE indexes or tables. All DDL is in `src/leaders_db/db/migrations/0001_initial.sql` (the canonical checked-in migration). The `register_pts_source` function uses SQLAlchemy upserts only (no DDL); the `write_pts_observations` function inserts rows only (no schema changes). This is the WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 pattern (the WGI reviewer's #3 blocker was a release-blocker for index-swap SQL; PTS does not repeat this mistake).

### #2 — No silent fallbacks (Constraint #2)

The sentinel matrix in §6 has 4 cases. Cases 2, 3, and 4 each have explicit Stage 2 handling:
- Case 2 (int + NA_Status != 0): drop the indicator, log to debug (no warning; this is the expected path for most non-zero NA_Status cells).
- Case 3 ('NA' + NA_Status != 0): drop the indicator, log to debug (expected path).
- Case 4 ('NA' + NA_Status = 0): drop the indicator AND log a **warning** with the country + year + indicator column (the inconsistency case). The warning is surfaced via `logging.warning()` (NOT `print()`); the orchestrator's run log captures it.

No silent defaults. The `_coerce_pts_value` helper explicitly handles each case.

### #3 — Pydantic models for cross-boundary data (Constraint #3)

`PtsIngestResult` is a `pydantic.BaseModel` (not a dataclass). The 8 fields are typed (with `Field(..., ge=...)` constraints where applicable) and validated. The orchestrator's return type is a `PtsIngestResult` instance. This is the V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 pattern.

### #4 — Constants live in the lowest-level IO module (Constraint #4)

`PTS_ATTRIBUTION`, `PTS_SOURCE_KEY`, and the 4 named constants (`_PTS_INDICATOR_NAMES`, `_PTS_REGION_CODES`, `_PTS_NA_STATUS_CODES`, `_DEFAULT_CATALOG_PATH`, `_RAW_XLSX_NAME`, `_PROCESSED_PARQUET_NAME`, `_PARQUET_META_ATTRIBUTION`, `_PARQUET_META_SOURCE_KEY`) live in `pts_io.py`. The orchestrator `pts.py` re-exports them for the public surface.

### #5 — Drift-guard test (Constraint #5)

`test_pts_attribution_matches_attributions_doc` (§8.5) asserts `PTS_ATTRIBUTION` is a substring of `docs/source-attributions.md`. The test reads `docs/source-attributions.md` as text and asserts the constant is present (byte-for-byte). This is the WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 pattern.

### #6 — No `print()` in `src/` (Constraint #6)

No `print()` calls in `src/leaders_db/ingest/pts*.py`. The orchestrator uses `logging` for all internal output; the CLI boundary (`cli.py`) prints the result JSON to stdout at end-of-run (NOT the orchestrator).

### #7 — No commented-out code, no `TODO(debug)` markers (Constraint #7)

None in the new modules. The `build_sample_xlsx.py` fixture script is a one-shot helper (committed; idempotent; re-runnable), not a `TODO(debug)` marker.

### #8 — `is_obs` / `is_country` use the right pandas idiom (Constraint #8)

`pd.isna(value)` for null detection (used in `_coerce_pts_value` for the defensive "unexpected cell value" case); `df["col"]` for value access (used in the wide-frame construction). No `df.col` (deprecated) and no `df.is_obs` (non-existent).

### #9 — No `LEADERSDB_PROJECT_ROOT` env-var handling duplicated (Constraint #9)

The PTS modules do NOT touch `os.environ` or `LEADERSDB_PROJECT_ROOT`. Only `env.py` and `paths.py` read it. The test fixture `isolated_data_lake` sets the env var via `monkeypatch.setenv` and the PTS modules use `paths.raw_dir(PTS_SOURCE_KEY)` (which honors the env var via the `paths` module).

### #10 — No module over 400 lines (Constraint #10)

The 4 modules' line budgets are: `pts.py` ~200-260, `pts_io.py` ~280-340, `pts_xlsx.py` ~200-280, `pts_db.py` ~280-340. The closest to the cap is `pts_db.py` (estimated 320 lines). If implementation exceeds the cap, the developer splits into `pts_db_helpers.py` (the default is 4 modules, not 5).

### #11 — No raw string fragments that should be enum/constants (Constraint #11)

The 7 single-region codes (`_PTS_REGION_CODES`), the 3 indicator names (`_PTS_INDICATOR_NAMES` — `PTS_A`/`PTS_H`/`PTS_S`), and the 5 NA_Status values (`_PTS_NA_STATUS_CODES` — `0`/`66`/`77`/`88`/`99`) are all named frozensets in `pts_io.py`. Each is used in 3+ places (the catalog loader, the xlsx read function, the DB writer). The `'mena, ssa'` anomaly is NOT in `_PTS_REGION_CODES`; it is handled as a literal in the code with a defensive comment.

### #12 — No inventing data (Constraint #12)

The xlsx reader returns what `openpyxl` returns; no transformations are applied to the cell values beyond the §6 sentinel matrix (which is the documented Stage 2 contract). The test fixture is a slice of the real `PTS-2025.xlsx`, not a hand-authored mock. The 4-case sentinel matrix is the explicit design contract; no "creative" coercion is applied.

### #13 — Year is a parameter, not hard-coded (Constraint #13)

The orchestrator accepts a `--year` flag (passed as `year=` kwarg). Short-circuit behavior: `year=1900` (out of the 1976-2024 range) returns an empty wide DataFrame with the expected column shape (no crash). `year=None` keeps all 49 years. The function is symmetric: same return type for any year value.

### #14 — No schema/fixture changes during Phase C/D (Constraint #14)

Once the test-builder lands `test_ingest_pts.py` and `tests/fixtures/pts/sample.xlsx`, the developer does NOT change the fixture to make a test pass. If a test fails because the fixture doesn't match the test's expectation, the developer fixes the TEST (or, for genuine discrepancies, fixes the design doc and re-syncs the fixture + catalog + constant in the same commit). This is the WGI reviewer's #3 release-blocker rule.

### #15 — No duplicate dispatch key (Constraint #15)

The `STAGE2_ADAPTERS` dict in `src/leaders_db/ingest/__init__.py` has exactly one `"pts"` key. The current value is `None` (Phase A placeholder); the developer changes it to `pts.ingest_pts` in the same commit. No second `"pts"` entry is added. The dispatch-table test `test_stage2_adapters_dispatch_table` asserts the key set is exactly the 25 keys.

### #16 — All 5 prior lessons baked into the test plan (Constraint #16)

1. **(WDI) End-to-end smoke runs against a fixture mirroring real-file quirks.** §8.7: the fixture is a slice of the real `PTS-2025.xlsx` (not a hand-authored mock), preserving the mixed int/str `PTS_X` cells, the exact `'NA'` string sentinel, and the exact `NA_Status` integer encoding. The §8.2 sentinel-coercion tests (`test_read_pts_coerces_na_string_to_none`, `test_read_pts_warns_on_inconsistency`, etc.) exercise all 4 §6 cases.

2. **(WGI) Drift-guard test is byte-identical.** §8.5: `test_pts_attribution_matches_attributions_doc` asserts `PTS_ATTRIBUTION in doc_text` (a substring check that is byte-for-byte exact).

3. **(UCDP) NA_Status filtering is in the reader, not the orchestrator.** §6.2: the sentinel matrix is implemented in `_coerce_pts_value` inside `pts_xlsx.py` (the reader), not in `pts.py` (the orchestrator). The data flow is a single linear pass: xlsx → sentinel matrix → wide frame → parquet → DB. No post-processing.

4. **(SIPRI milex) The 3 indicator names match the xlsx header row EXACTLY (case-sensitive, no whitespace).** §8.1: `test_catalog_raw_columns_match_pts_xlsx_headers` asserts the catalog's `raw_column` values are exactly `PTS_A`, `PTS_H`, `PTS_S` (matching the xlsx header verbatim, case-sensitive, no whitespace).

5. **(SIPRI Yearbook Ch.7) The `source_row_reference` uses the same pattern as the other 5 sources.** §7.3: `source_row_reference` is `"pts:<COW_Code_A>"` (e.g., `"pts:USA"`), mirroring WGI's `"wgi:MEX"`, V-Dem's `"vdem:<country_text_id>"`, UCDP's `"ucdp:<country_id>"`, SIPRI milex's `"sipri_milex:<display_name>"`, and SIPRI Yearbook Ch.7's `"sipri_yearbook_ch7:<display_name>"`. The §8.4 test `test_write_pts_observations_country_id_is_null` asserts the prefix.

### #17 — Region-code drift fix (architect flag, Constraint #17)

**Live-data finding:** The prompt and `metadata.json` list 6 region codes (`sa`/`ssa`/`eur`/`ame`/`apac`/`mena`) but the live xlsx has **7 single-region codes** (`eap`, `eca`, `lac`, `mena`, `na`, `sa`, `ssa`) — these are the **World Bank country-and-lending-groups codes**, NOT the prompt's list. Plus 1 multi-region data anomaly (`'mena, ssa'`, 49 rows for the African Union).

**Action for the developer:** Update `data/raw/political_terror_scale/metadata.json` to reflect the live data: change the `"notes"` field to list the 7 single-region codes (`eap`, `eca`, `lac`, `mena`, `na`, `sa`, `ssa`) and flag the `'mena, ssa'` anomaly. The constant `_PTS_REGION_CODES` in `pts_io.py` already reflects the live data (the architect wrote it from the live probe). This is the same docs-drift fix pattern as the WGI "1996–2023" → "1996–2022" correction (mirrored in [`docs/architecture/wgi.md`](wgi.md) §2.8).

### #18 — NA_Status code coverage is correct (architect confirmation, Constraint #18)

**Live-data confirmation:** The prompt's 5 NA_Status codes (`0`/`66`/`77`/`88`/`99`) are all present in the live data. The 2023 subset has `0` (157), `88` (42), `77` (9), `66` (7), `99` (0 in 2023 but present in other years). The constant `_PTS_NA_STATUS_CODES = frozenset({0, 66, 77, 88, 99})` matches the live data. No drift fix needed for §6.5.

### #19 — Inconsistency case (PTS_X='NA' AND NA_Status=0) is real and observable (architect confirmation, Constraint #19)

**Live-data finding:** The §6 case-4 row (PTS_X='NA' AND NA_Status=0) is rare but real. The probe found at least one such row (Bahamas 2017, PTS_A='NA' with NA_Status_A=0). The §6 case-4 handling (drop + log warning) is the correct design contract. The test fixture (§8.6) must include at least one case-4 row to exercise the warning path; the test-builder copies the live Bahamas 2017 row (or any other observed case-4 row) into the fixture.

---

## 13 — Dispatch table entry (Constraint #15)

The `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py` needs one change: replace the existing `"pts": None` stub with the live import, and add the `from . import pts` line.

### Exact changes

In `src/leaders_db/ingest/__init__.py`:

```python
# Add the import alongside the vdem, wdi, wgi, ucdp, sipri_milex, sipri_yearbook_ch7 imports at the top of the import block:
from . import pts, sipri_milex, sipri_yearbook_ch7, ucdp, vdem, wdi, wgi

# In the STAGE2_ADAPTERS dict, change the existing line:
    "pts": None,
# to:
    "pts": pts.ingest_pts,
```

The full dispatch table stays the same shape (25 keys); only the value of the `pts` key changes from `None` to the orchestrator. All other `None` stubs (`undp_hdi`, `who_gho_api`, `polity_v`, `pwt`, `archigos`, `reign`, `leader_survival`, `transparency_cpi`, `fas`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`, `freedom_house`, `imf_weo`, `cow_mid`, `cirights`, `nti`, `bti`, `cia_world_leaders`) are untouched and remain for the next batches.

> **Reviewer-bug from WDI / UCDP history (apply the lesson):** the WDI review found 1 blocker (a duplicate `"world_bank_wgi"` dispatch key that had been silently masked); the UCDP review found 1 blocker (a duplicate `"sipri_milex"` dispatch key from an earlier copy-paste). The current dispatch table (post-UCDP fix) has exactly **one** `"pts"` entry, with value `None`. Do not accidentally add a second one. The dispatch-table test (`test_stage2_adapters_dispatch_table` in the new `tests/test_ingest_pts.py`) asserts the key set is exactly the 25 keys.

The `__all__` does not need to change. No CLI code change is needed — the CLI already iterates over the dispatch table.

---

## 14 — Workplan / docs updates (for the project-manager)

When the PTS adapter lands and the reviewer signs off, the project-manager will add the following entries to `docs/workplan.md` (Done History) and update `docs/source-attributions.md`, `docs/source-vetting-report.md`, and `docs/data-sources.md`.

### `docs/workplan.md` — new Done History entry

> **Phase C.7 — PTS Stage 2 ingest landed (DATE).** Seventh Stage 2 adapter implemented via the architect → test-builder → developer → reviewer pipeline. ~30 new tests in `tests/test_ingest_pts.py` (~280 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/pts.csv` lists 3 PTS indicators (pts_amnesty_score, pts_human_rights_watch_score, pts_state_dept_score), all under `domestic_violence` (cross-validation source for UCDP one-sided and V-Dem repression). Read pattern: open the 572 KB `PTS-2025.xlsx` with `openpyxl.read_only=True`, walk the single sheet (1 sheet, 10,531 rows × 14 columns), apply the 4-case sentinel matrix (NA_Status takes precedence over PTS_X; case 4 inconsistency is logged + dropped), pivot long → wide. The wide frame is ~200 country-year rows × 3 indicator columns for `year=2023`. Test fixture at `tests/fixtures/pts/sample.xlsx` is a 2-country × 2-year slice of the real xlsx (4 rows + 1 inconsistency row + 1 NA_Status=88 row; created by `build_sample_xlsx.py` which slices the real file with `openpyxl`). End-to-end run against the real 572 KB xlsx for `year=2023` produces 215 country rows × 3 indicators = ~462 `source_observations` rows (summed across 3 indicators). The `PTS_ATTRIBUTION` constant is byte-identical to the citation in `docs/source-attributions.md` (drift-guard test added). No new project dependencies. The `metadata.json` is updated to reflect the live-data region codes (7 single-region codes + the `'mena, ssa'` anomaly, replacing the 6-code approximation in the original metadata). `STAGE2_ADAPTERS["pts"]` is now `pts.ingest_pts` in `src/leaders_db/ingest/__init__.py`. PTS follows the WGI 4-module split (`pts.py` / `pts_io.py` / `pts_xlsx.py` / `pts_db.py`). Reviewer caught N blockers, M important, K nits — all fixed in a single iteration. **PASS on the second pass. Moving to the next adapter per the priority list.**

### `docs/source-attributions.md` — no change required

The `pts` entry in `docs/source-attributions.md` §1 is already correct and matches the `PTS_ATTRIBUTION` constant byte-for-byte. The developer does NOT update the doc; the drift-guard test confirms consistency.

### `docs/source-vetting-report.md` — one minor update

§3.8 ("Domestic violence / repression sources") `pts` row gets a one-line note: "Stage 2 adapter landed; see `src/leaders_db/ingest/pts.py`. 3 indicators under `domestic_violence`: pts_amnesty_score, pts_human_rights_watch_score, pts_state_dept_score. The xlsx is long-format (10,531 country-year rows × 14 columns); Stage 2 applies the 4-case NA_Status sentinel matrix. Stage 3 resolves the `COW_Code_A` to ISO3 via the country lookup table."

§6 ("Caveats the Stage 2 ingest must handle") `pts` row gets an update:

| Source | Caveat to handle |
|---|---|
| `pts` | (was) "Free academic; cite Wood, Gibney, et al." → (now) "**The xlsx uses a 2-signal sentinel pattern: `PTS_X` (int 1-5 or str `'NA'`) AND `NA_Status_X` (int 0/66/77/88/99). The Stage 2 read applies a 4-case precedence rule: NA_Status takes precedence over PTS_X. Cases: (1) `int 1-5 + NA_Status=0` → valid; (2) `int 1-5 + NA_Status != 0` → drop; (3) `'NA' + NA_Status != 0` → drop; (4) `'NA' + NA_Status=0` → drop + warning (the inconsistency case, rare but observed in the live xlsx). The `raw_value` audit trail preserves the literal `'NA'` string or the stringified int. The xlsx uses 7 World Bank country-and-lending-groups region codes (`eap`/`eca`/`lac`/`mena`/`na`/`sa`/`ssa`) plus 1 data anomaly (`'mena, ssa'`, 49 rows for the African Union); the anomaly is passed through verbatim to `source_observations.notes`. The xlsx gives 4 ID columns per row; Stage 2 uses `COW_Code_A` as the primary `source_row_reference` suffix (`pts:<COW_Code_A>`, e.g., `pts:USA`). Stage 3 resolves the COW code to ISO3 via the country lookup table. All 5 NA_Status codes are present in the live data; the constant `_PTS_NA_STATUS_CODES = frozenset({0, 66, 77, 88, 99})` is the canonical set.**" |

### `docs/data-sources.md` — one update

The existing `pts` row says "xlsx; 572 KB; 1 sheet; 10,531 rows × 14 columns; ~200 countries × 49 years (1976-2024); free academic with attribution." Update to: "xlsx download; 572 KB; 1 sheet (`PTS-2025`); 10,531 country-year rows × 14 columns; 3 PTS scores (Amnesty, HRW, State) per row; 5 NA_Status codes per row; 7 World Bank region codes (eap, eca, lac, mena, na, sa, ssa) plus 1 data anomaly (`mena, ssa`); Stage 2 adapter landed."

### `docs/architecture.md` — no change required

The existing `architecture.md` already lists PTS as one of the per-source Stage 2 adapters (the "Domestic violence / repression sources" section). No structural change is needed.

### `pyproject.toml` — no change required

No new project dependencies. PTS uses the same `openpyxl` / `pandas` / `pyarrow` / `pydantic` / `sqlalchemy` deps that WGI uses. The `reportlab` test fixture dep (added for SIPRI Yearbook Ch.7) is not needed for PTS (the test fixture is created by slicing the real xlsx with `openpyxl`, not by authoring with `reportlab`).

### `data/raw/political_terror_scale/metadata.json` — minor update (Constraint #17)

The `notes` field is updated to reflect the live-data region codes (replacing the 6-code approximation with the 7 single-region codes + the `'mena, ssa'` anomaly). The other fields (`coverage_start_year: 1976`, `coverage_end_year: 2024`, `sha256`, `source_url`, `license`) are unchanged.

### `docs/requirements-core.md` — no change required

The existing `domestic_violence` category in `docs/requirements-core.md` already lists PTS as the third source (alongside UCDP and V-Dem); the new adapter does not change the requirement set, only the implementation.

---

## 15 — Lessons from WDI / WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 reviews (apply to PTS from day one)

These are the WDI review findings, the WGI review findings, the UCDP review findings, the V-Dem review findings, the SIPRI milex review findings, and the SIPRI Yearbook Ch.7 review findings. Apply them to PTS from the start so we don't repeat them.

### WDI lessons (apply all 8)

1. **No duplicate dispatch-table keys.** The `__init__.py` already has exactly one `"pts": None` entry (Phase A placeholder). Do not add a second one. The dispatch-table test asserts the 25-key set.

2. **No ruff warnings in the test file.** Hoist all imports to the top; no unused imports; no lines >100 chars. The test-builder must follow the WGI / V-Dem convention (`from __future__ import annotations` first, then `import json, shutil`, then `from pathlib`, then third-party, then `from leaders_db...`).

3. **End-to-end test for orchestrator-level fields.** The `PtsIngestResult` has 8 fields. The end-to-end test must assert all 8, not just internal function call counts.

4. **Docstring accuracy.** Match the runtime default in the docstring (e.g., `year: int | None = None` should be documented as "Default: all years 1976–2024", not "Required"). The `pts.py` docstring should NOT say "400-line convention" or similar lies; each module's line count will be reported in the Done History entry, not in the source docstring.

5. **Design doc accuracy.** The catalog CSV is the source of truth; the design doc must match exactly. If the developer discovers a discrepancy (e.g., the live xlsx has a different cell value than the design says), update the design doc in the same commit.

6. **`confidence IS NULL` assertion.** The Stage 2 → Stage 11 contract requires `confidence` NULL; the test must assert it (`assert all(r.confidence is None for r in rows)`).

7. **`raw_value` assertion.** The test must assert the `raw_value` for non-missing cells is the stringified int, and for missing cells it is the literal `"NA"`. This is the PTS-specific corollary of V-Dem's `"-999.0"` assertion, WGI's `"#N/A"` assertion, WDI's `"nan"` assertion, UCDP's `str(0)` for 0-fatality events assertion, SIPRI milex's `"..."` / `"xxx"` assertions, and SIPRI Yearbook Ch.7's `"–"` / `".."` / `"c. 24 j"` assertions.

8. **Live-xlsx smoke verification.** Run the adapter against the real 572 KB xlsx after tests pass; verify row count (215 country rows for 2023, ~462 `source_observations` rows summed across 3 indicators), the `regions_covered` (all 7 single-region codes + the `'mena, ssa'` anomaly), the `year_window` ((2023, 2023) for a year-filtered run, (1976, 2024) for a full unfiltered run), and the PTS attribution in the CLI end-of-run output. Recorded in `docs/testing-guide-stage2-pts.md`.

### WGI lessons (apply all 6)

1. **The WGI reviewer's #3 (index-swap SQL) was a release-blocker because the developer changed the schema to make a test pass. Never change the schema or canonical text to make a test pass. Fix the test instead.** Specifically for PTS:
   - If a test uses a fragile dict-comprehension pattern, fix the test to sort the rows before building the dict, or use `.order_by()`.
   - If a test asserts on a canonical text (like `"PTS" in attribution`), change the test to assert on a substring that's actually in the canonical text (like `"Political Terror Scale" in attribution` or `"Wood, Reed M." in attribution`), not the canonical text itself.
   - If a test fails because the catalog column name doesn't match the real data, change the test to match the data, not the data to match the test.

2. **WGI line counts exceeded 400.** For PTS, design the module split upfront so no file exceeds 400 lines. The 4-module split (`pts.py` ~200-260, `pts_io.py` ~280-340, `pts_xlsx.py` ~200-280, `pts_db.py` ~280-340) is the target. If a module grows past 400, split it during implementation.

3. **WGI `default_xlsx_path()` raise semantics.** PTS's `default_xlsx_path()` must also raise `FileNotFoundError` if the file is missing (per the design's stated contract in §9.4). The test `test_default_path_helpers` verifies this.

### UCDP lessons (apply all 5)

1. **No duplicate dispatch-table keys (the UCDP reviewer's #1 blocker).** The `__init__.py` already has exactly one `"pts"` entry. Do not accidentally add a second one.

2. **No stale stub comment.** The UCDP reviewer's #3 was a stale comment in `ucdp.py` that said "UCDP is the second Stage 2 adapter" (it was the fourth). For PTS, the module docstring must say "seventh Stage 2 adapter" (matching the actual order: V-Dem, WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, PTS).

3. **No stale `# type: ignore` comments.** UCDP had a stale `# type: ignore` that hid a real type error. PTS must use `from __future__ import annotations` and proper type hints throughout; no `# type: ignore` unless the upstream type system is genuinely wrong (and a comment explains why).

4. **No design-doc contradictions.** The UCDP reviewer's #2 blocker was a "dense vs sparse frame" contradiction in the design doc. For PTS, the wide frame is **dense** (every country-year row from the xlsx is present, even when all 3 indicator cells are missing — the indicator cells are `pd.NA`); the design must consistently say "dense" in both the read docstring and the public surface docstring.

5. **No schema mutation.** UCDP had a release-blocker (the WGI pattern: never DROP/CREATE indexes in the orchestrator). PTS must not touch the schema; the `register_pts_source` function only does an upsert via SQLAlchemy, no DDL.

### V-Dem lessons (apply all 4)

1. **`_coerce_int` handles all the missing-data sentinels in one place** (defense in depth). PTS's `_coerce_pts_value` must handle the 4 §6 cases, the V-Dem / WGI / WDI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 sentinels (defense in depth for future multi-source ingestion), and the `'NA'` string + 5 NA_Status codes for the primary path.

2. **`_raw_value_to_string` preserves the original cell for the audit trail** (per the V-Dem pattern in `vdem_db.py`). For PTS, the audit-trail string is `str(int)` for present cells, `"NA"` for `'NA'` cells (cases 3 and 4), and `str(int)` for case-2 cells (even though they're dropped). The test asserts all 3 patterns.

3. **V-Dem's `_delete_existing_observations` is the same pattern as PTS's** — delete existing rows for the requested years before inserting (so re-runs are idempotent for the year filter, but older years are untouched).

4. **V-Dem's `country_id` rename (to `vdem_country_id`) does NOT apply to PTS.** PTS's wide frame's `country` column carries the raw PTS `Country` display name (NOT a V-Dem-style `vdem_country_id`). The wide frame's `cow_code` column carries the `COW_Code_A` 3-letter code (used for `source_row_reference`). The `source_observations.country_id` is left NULL (Stage 3 fills it). This is the PTS-specific pattern.

### SIPRI milex lessons (apply all)

The SIPRI milex adapter is the closest xlsx-read analog. The lessons are:

1. **No ISO3 column in the source data.** SIPRI milex's display-name passthrough pattern is the template for the PTS `country` column: store the raw display name in the wide frame's `country` column, leave `country_id` NULL for Stage 3. PTS uses the same pattern for the `country` column AND uses `COW_Code_A` for the `source_row_reference` (a hybrid pattern).

2. **The missing-value convention differs from V-Dem / WGI / UCDP / WDI sentinels.** SIPRI milex's `"..."` / `"xxx"` / `""` are the SIPRI-specific sentinels. PTS's `"NA"` + 5 NA_Status codes are the PTS-specific sentinels. PTS has a `_PTS_NA_STATUS_CODES` frozenset + a `_PTS_INDICATOR_NAMES` frozenset + a `_PTS_REGION_CODES` frozenset that are the PTS-specific named constants.

3. **The `_coerce_*` helper pattern.** SIPRI milex's `_coerce_float` (in `sipri_milex_db.py`) is the model for PTS's `_coerce_pts_value` (in `pts_xlsx.py`). Both helpers handle the source-specific sentinels in one place and return `None` for the "not available" case.

4. **The `df.attrs` audit pattern.** SIPRI milex's `df.attrs["regions_covered"]` and `df.attrs["country_count"]` are surfaced in `SipriMilexIngestResult`. PTS's `df.attrs["regions_covered"]` and `df.attrs["year_window"]` are surfaced in `PtsIngestResult` (same pattern, different fields).

5. **No cross-validate-with-other-source output.** SIPRI milex is the 2nd source for `international_peace` (cross-validating UCDP). PTS is the 3rd source for `domestic_violence` (cross-validating UCDP one-sided and V-Dem repression). The Stage 5 score module's confidence formula will have full cross-validation coverage for `domestic_violence` (3 sources); handled in Stage 5, not Stage 2.

### SIPRI Yearbook Ch.7 lessons (apply all)

1. **No ISO3 column in the source data.** SIPRI Yearbook Ch.7 uses display names + PDF structure; PTS uses display names + 4 ID columns. Both leave `country_id` NULL for Stage 3; both use a per-source prefix for `source_row_reference`.

2. **The `df.attrs` audit pattern.** SIPRI Yearbook Ch.7's `df.attrs["pdf_pages_total"]` and `df.attrs["snapshot_year"]` are surfaced in `SipriYearbookCh7IngestResult`. PTS's `df.attrs["regions_covered"]` and `df.attrs["year_window"]` are surfaced in `PtsIngestResult`.

3. **The 8-field IngestResult pattern.** SIPRI Yearbook Ch.7 has 8 fields (6 from WGI + 2 source-specific extras). PTS also has 8 fields (6 from WGI + 2 source-specific extras). The end-to-end test asserts all 8.

4. **The drift-guard test pattern.** SIPRI Yearbook Ch.7's `test_sipri_yearbook_ch7_attribution_matches_attributions_doc` is the model for PTS's `test_pts_attribution_matches_attributions_doc`. Both assert the constant is a substring of `docs/source-attributions.md`.

### Source-of-truth principle (the prompt's specific instruction)

The prompt's instruction: "If the test fixture count and the design catalog spec disagree (e.g., 3 vs 4 indicators), the design doc is the source of truth; the test must match." For PTS, the design says **3** indicators; the test fixture must have **3** indicator columns. The test-builder does not negotiate this; the developer does not negotiate this. The 3 indicators in §3 are the contract.

### `df.attrs` survival (the UCDP-style extras pattern)

The `df.attrs["regions_covered"]` and `df.attrs["year_window"]` pattern applies to PTS. The orchestrator surfaces both in `PtsIngestResult`. The end-to-end test asserts both fields. The parquet writer strips any non-JSON-serializable keys (if present) but preserves the JSON-serializable `regions_covered` (list of strings) and `year_window` (2-tuple of ints).

### Fixture slicing (the WGI-style real-format preservation)

The test fixture is created by slicing the real `PTS-2025.xlsx` with `openpyxl`, NOT by hand-authoring cells. This preserves the real format quirks (mixed int/str `PTS_X` cells, the exact `'NA'` string sentinel, the exact NA_Status integer encoding). If the test-builder writes the fixture by hand and the reader fails to parse it, the developer **fixes the reader**, not the fixture. The fixture is the contract; the reader is the implementation. This is the same source-of-truth principle as the WGI fixture convention.

---

## Open questions for the developer

1. **The `metadata.json` region-code drift (#17).** The metadata.json lists 6 codes; the live xlsx has 7 single-region codes + 1 anomaly. The developer updates the metadata.json's `notes` field to reflect the live data in the same commit as the adapter lands. The constant `_PTS_REGION_CODES` in `pts_io.py` is already correct (the architect wrote it from the live probe).

2. **The score inversion convention (PTS 1-5 → 0-10).** The catalog's `normalized_scale_target` is `0-10` (the user-facing convention). The Stage 5 score module applies the inversion (`higher_is_better=False`). The developer confirms the mapping (1→10, 2→7.5, 3→5, 4→2.5, 5→0) with the user before implementing the score module (out of scope for Stage 2).

3. **Should the `mena, ssa` anomaly be normalized?** The architect's recommendation is to preserve it verbatim (passed through to `source_observations.notes` via the `region` column). The alternative is to split the cell into 2 rows (one for `mena`, one for `ssa`) or filter it out as a data error. The architect recommends preservation for the audit trail; the developer confirms with the user before implementing.

4. **The `Country_OLD` column (historical name).** Stage 2 does not extract it as an indicator. Stage 2 also does not write it to `source_observations.notes` (the field is too verbose for the notes column). The display name `Country` is sufficient for the wide frame. The developer confirms with the user if a future iteration needs the historical name.

5. **The 3 secondary ID columns (`COW_Code_N`, `WordBank_Code_A`, `UN_Code_N`).** Stage 2 preserves them in the wide frame's audit metadata (via `df.attrs["_pts_id_lookup"]`) but does NOT extract them as indicators. The developer confirms with the user if Stage 3 needs all 3 for cross-validation (a future Stage 3 deliverable).

---

**Ready for the test-builder.** The design doc, catalog CSV, and fixture-slicing strategy are written. The architect's findings (#17 region-code drift, #18 NA_Status code coverage confirmation, #19 inconsistency case) are documented and the developer is expected to address them in the same commit as the adapter lands. No source code or test code has been written (per the architect's contract — that is Phase B's and Phase C's job, respectively).
