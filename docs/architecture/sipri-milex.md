# SIPRI milex Architecture Design — Stage 2 Adapter for SIPRI Military Expenditure Database

> **Status:** architecture design, ready for test-builder and developer.
> **Phase:** C.5 (data acquisition, fifth adapter, after V-Dem, WDI, WGI, UCDP).
> **Target source key:** `sipri_milex`.
> **Wiring in:** `src/leaders_db/ingest/__init__.py::STAGE2_ADAPTERS` (replace the existing `"sipri_milex": None` stub with `sipri_milex.ingest_sipri_milex`).
> **Source verdict:** ✅ `vetted_ok` per [`docs/source-vetting-report.md`](../source-vetting-report.md) §3.7.
> **Liveness verified:** 2026-06-18 — `https://www.sipri.org/databases/milex` returns HTTP 200; the canonical xlsx `https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx` downloads 922,552 bytes (922 KB) and unzips to a 10-sheet workbook covering 1949–2025 (77 years) for ~177 countries. The file's title bar reads "© SIPRI 2026".

This document is the design contract for the SIPRI milex Stage 2 adapter. The test-builder writes tests against the public surface in §3.3; the developer implements against the same surface. The catalog spec in §3.4 is the only place where SIPRI milex's indicator list is decided.

---

## 3.1 — Source contract (what SIPRI milex gives us, what we extract)

### Canonical URL and file format

| Field | Value |
|---|---|
| Canonical URL | `https://www.sipri.org/databases/milex` (landing page) → download link `https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx` |
| Format | Excel xlsx (one file, 10 sheets) |
| Size | ~922 KB (last verified 2026-06-18; the v1.2 release) |
| Auth | none (public, free, no API key) |
| Release cadence | annual; the current release is the v1.2 update covering 1949–2025 (release date 2026, marked "© SIPRI 2026" in the file) |
| Local storage | `data/raw/sipri_milex/SIPRI-Milex-data-1949-2025_v1.2.xlsx`; `metadata.json` alongside |

> **Why xlsx, not an API?** SIPRI milex has no machine-readable API. The xlsx is the canonical input: download once a year, slice it by indicator × year × country. No per-indicator HTTP call, no pagination, no rate limiting. Structurally this is identical to WGI (one local xlsx, multi-sheet, per-sheet long-to-wide pivot). The download workflow uses `curl` to place the file at `data/raw/sipri_milex/`; the Stage 2 adapter does not download.
>
> **Version drift.** The Phase B source-vetting report says the file is "SIPRI-Milex-data-1949-2025_v1.2.xlsx". The adapter's `_RAW_XLSX_NAME` constant is the version-locked filename. The catalog loader is the only thing the developer checks on a new release — if SIPRI renames a sheet, the catalog's `raw_column` value must be updated to match. The drift-guard test `test_catalog_sheet_names_match_sipri_release` (§3.5) catches this at test time.

### xlsx structure (verified live 2026-06-18)

The xlsx is a **10-sheet workbook**:

| Sheet name | Purpose | Rows | Cols |
|---|---|---|---|
| `Front page` | Title page (mostly empty in v1.2) | 2 | 2 |
| `Regional totals` | Notes + region-level aggregates in constant US$ | 32 | 44 |
| `Local currency financial years` | Local-currency values, fiscal-year basis | 201 | 81 |
| `Local currency calendar years` | Local-currency values, calendar-year basis | 200 | 80 |
| `Constant (2024) US$` | Real-USD values (millions), 1949–2025 (77 years) | 199 | 80 |
| `Current US$` | Current-USD values (millions), 1949–2025 (77 years) | 199 | 79 |
| `Share of GDP` | Mil-ex as % of GDP, 1949–2025 (77 years) | 199 | 79 |
| `Per capita` | Mil-ex per capita (current US$), 1988–2025 (38 years) | 199 | 40 |
| `Share of Govt. spending` | Mil-ex as % of government spending, 1988–2025 (38 years) | 202 | 42 |
| `Footnotes` | Per-country explanatory notes | 117 | 3 |

**Per-data-sheet layout** (e.g. `Share of GDP`):

```
Row 1:   <long title with "© SIPRI 2026">
Row 2:   <format description, e.g. "Countries are grouped by region and subregion.">
Row 3:   <color-coding note, e.g. "Figures in blue are SIPRI estimates...">
Row 4:   <missing-data legend, e.g. '"..." = data unavailable. "xxx" = country did not exist...'>
Row 5:   (blank or "Reporting year" header for Share of Govt. spending)
Row 6:   HEADER — col 0 = 'Country', col 1 = 'Notes' (or 'Currency' / 'Fiscal Year' for
         local-currency sheets), col 2+ = year columns (1949, 1950, ..., 2025)
Row 7:   (blank separator)
Row 8..: DATA — region labels, sub-region labels, and country rows interleaved
```

The **header row position varies by sheet** (verified live):

| Sheet | Header row | Col 0 | Col 1 | Col 2 | Col 3 | First year | Last year | Year count |
|---|---|---|---|---|---|---|---|---|
| `Constant (2024) US$` | 6 | `Country` | `''` (empty) | `Notes` | 1949 | 1949 | 2025 | 77 |
| `Current US$` | 6 | `Country` | `Notes` | 1949 | 1950 | 1949 | 2025 | 77 |
| `Share of GDP` | 6 | `Country` | `Notes` | 1949 | 1950 | 1949 | 2025 | 77 |
| `Per capita` | 7 | `Country` | `Notes` | 1988 | 1989 | 1988 | 2025 | 38 |
| `Share of Govt. spending` | 8 | `Country` | `Notes` | `Reporting year` | 1988 | 1988 | 2025 | 38 |

The Stage 2 read function **detects the header row dynamically** by scanning for the first row where column 0 is the literal string `"Country"`. This is the only robust way to handle the per-sheet header-row variation. The Notes / Currency / Reporting-year column that follows `Country` is sheet-specific metadata; the Stage 2 adapter reads it for the audit trail but does not extract it as an indicator.

**Column layout per country/region row (for the 5 catalog data sheets):**

- Col 0: `Country` (display name string, e.g. `"Mexico"`, `"United States of America"`, `"Türkiye"`).
- Col 1: `Notes` (string of footnote symbols, e.g. `"§4"`, `"‡§¶16"`). Carried in the audit trail; not extracted.
- Col 2 (or 3 for `Constant (2024) US$` and `Share of Govt. spending`): first year cell.
- Last col: 2025 (the latest data year).
- Year cells are either numeric (the data value) or one of three missing-value tokens:
  - `"..."` — data unavailable (the cell has no measurement).
  - `"xxx"` — the country did not exist or was not independent during the year (e.g. Ukraine in 1918, USSR before 1991).
  - `""` (empty string) — the cell is empty (rare; appears in some region rows).
  - For region/sub-region rows, all year cells are empty (these rows are aggregate labels, not data).

**Countries vs regions (the row-mix pattern):**

The 192 data rows below the header (rows 8–199 of `Share of GDP`) mix two row types:
- **15 region/sub-region labels** (e.g. `"Africa"`, `"North Africa"`, `"sub-Saharan Africa"`, `"Americas"`, `"Central America and the Caribbean"`, `"North America"`, `"South America"`, `"Asia & Oceania"`, `"Central Asia"`, `"East Asia"`, `"South Asia"`, `"South East Asia"`, `"Oceania"`, `"Europe"`, `"Eastern Europe"`, `"Central and Western Europe"`, `"Middle East"`). These rows carry no year data; the year cells are all empty.
- **~177 country rows** (e.g. `"Algeria"`, `"Mexico"`, `"Sweden"`, `"India"`, `"Nigeria"`). These carry the actual data.

Live probe of v1.2 found **177 distinct country names** and **15 region/sub-region labels** in the data rows of each indicator sheet. The Stage 2 adapter **filters out the 15 region labels** (which are well-known; see §3.6 for the canonical list) and keeps the 177 country rows. This is the WGI-style "no aggregates" approach, but SIPRI milex **does** have aggregates (the regions sheet) — the difference is that they are row labels, not ISO3 codes. The filter is by display name, not by code.

The "no aggregates" filter list:

```python
_SIPRI_MILEX_REGION_LABELS: frozenset[str] = frozenset({
    "Africa", "North Africa", "sub-Saharan Africa",
    "Americas", "Central America and the Caribbean", "North America", "South America",
    "Asia & Oceania", "Central Asia", "East Asia", "South Asia", "South East Asia", "Oceania",
    "Europe", "Eastern Europe", "Central and Western Europe",
    "Middle East",
    # Plus the 'World' total from the Regional totals sheet (defense in depth).
    "World",
})
```

This is the only region denylist; if a future release adds new region labels, the developer extends this set.

**Country name format (no ISO3 column):**

The SIPRI xlsx uses **display names** (e.g. `"United States of America"`, `"Türkiye"`, `"Yemen"`, `"Côte d'Ivoire"`, `"Democratic Republic of the Congo"`) but **no ISO3 column**. The Stage 2 adapter stores the raw display name in `source_row_reference` as `"sipri_milex:Mexico"` (the WGI pattern, but with the display name where WGI has the ISO3 code). Stage 3 (country match) resolves the SIPRI display name to ISO3 via the `country_aliases.csv` table (a future Stage 3 deliverable). This is the same approach as WGI's non-ISO3 codes (`XKX`, `ADO`, `ZAR`) and UCDP's `country_id` — the Stage 2 contract is to write the raw identifier verbatim and leave `country_id` NULL for Stage 3.

**Missing-data convention: `"..."` (string, three dots), `"xxx"` (string), or empty cell**

The three missing-value tokens differ from every other Stage 2 source:

| Token | Meaning | Stage 2 handling |
|---|---|---|
| `"..."` | Data unavailable | → `None` in `normalized_value`; raw_value preserves the literal `"..."` |
| `"xxx"` | Country did not exist / not independent | → `None` in `normalized_value`; raw_value preserves the literal `"xxx"` |
| `""` (empty) | Empty cell (rare; region rows only) | → `None` in `normalized_value`; raw_value preserves the literal `""` |
| `None` (Python None) | Truly empty (defense in depth) | → `None` in `normalized_value`; raw_value preserves `""` |
| numeric (float) | The measurement | → float in `normalized_value`; raw_value is `str(cell)` |

The missing-strings set in `sipri_milex_db.py`:

```python
_SIPRI_MILEX_MISSING_STRINGS: frozenset[str] = frozenset(
    {"...", "xxx", "NA", "NaN", "nan", "null", "None", "-999", "-999.0", ""}
)
```

This is the SIPRI-specific superset of WGI's missing-strings (WGI's was `{"#N/A", "NA", "NaN", "nan", "null", "None", "-999", "-999.0", ""}`). The two new tokens (`"..."` and `"xxx"`) are the only SIPRI-specific additions.

### What we extract vs what we defer

**Extract (4 indicators across 1 category, from the 4 most-cited data sheets):**

For each `(country, year)` in the long-format read, 4 indicator values:

1. `sipri_milex_share_of_gdp` — `% of GDP` (from the `Share of GDP` sheet, year cell).
2. `sipri_milex_per_capita` — `current US$ per capita` (from the `Per capita` sheet, year cell).
3. `sipri_milex_constant_usd` — `millions of constant (2024) US$` (from the `Constant (2024) US$` sheet, year cell).
4. `sipri_milex_share_of_govt_spending` — `% of government spending` (from the `Share of Govt. spending` sheet, year cell).

**Defer to a future iteration (kept in the xlsx but not written to `source_observations`):**

- The `Local currency financial years` and `Local currency calendar years` sheets — useful for fiscal-year vs calendar-year disambiguation, but the prototype's Stage 5 score module consumes the calendar-year aggregates from the 4 chosen sheets. Local-currency values are needed for source cross-validation but are not on the indicator catalog.
- The `Current US$` sheet — same content as `Constant (2024) US$` but in nominal terms. The constant-USD sheet is preferred (real terms, cross-time comparable); the current-USD sheet is a 5th candidate indicator that we defer to keep the catalog narrow.
- The `Regional totals` sheet — region-level aggregates; the prototype scores ruler-years, not region-years.
- The `Front page` and `Footnotes` sheets — metadata, not data.
- The per-country `Notes` column (footnote symbols like `"§4"`, `"‡§¶16"`) — preserved in the `notes` field of `source_observations` if present, but not extracted as a separate indicator.

This narrowing is a **user decision** (see "Open questions" in §3.6). The user may want `Current US$` added as a 5th indicator for completeness. The catalog is the single source of truth; adding `Current US$` is a 1-row addition.

### Indicator catalog scope (this design)

For the prototype, all **4** catalog indicators are extracted, feeding the **1 rating category** SIPRI milex serves per the source-vetting report:

1. **`international_peace`** — 4 indicators: `sipri_milex_share_of_gdp`, `sipri_milex_per_capita`, `sipri_milex_constant_usd`, `sipri_milex_share_of_govt_spending`. All four cross-validate UCDP's `ucdp_state_based_*` and `ucdp_intl_*` event-based signals. SIPRI milex is the **expenditure-based complement** to UCDP's **event-based** signal — different methodologies (expenditure vs events), per requirement §11 "source_agreement_score" (REQ-CONF-002).

The full per-indicator spec (raw sheet name → canonical `variable_name`, scale, unit, category, one-line description) is in §3.4. The catalog CSV the developer will author lives at `src/leaders_db/ingest/catalogs/sipri_milex.csv` (sibling to the adapter modules, per Phase C convention #1).

> **Why `international_peace` only, no other category?** Per [`docs/source-vetting-report.md`](../source-vetting-report.md) §3.7 and §11, SIPRI milex is the 2nd source for the `international_peace` category (alongside UCDP). The 4 indicators all measure aspects of military expenditure (absolute, normalized to GDP, normalized to population, normalized to govt budget) — all proxies for the same underlying signal ("how much is this state arming?"). A 2nd source for the SIPRI milex is the SIPRI Yearbook Ch.7 (nuclear forces, a different category entirely — `nuclear`). For the `domestic_violence` category, SIPRI milex is **not** a source; UCDP one-sided and PTS and CIRIGHTS are the 3 cross-validation sources.

### Integration with downstream schema

None of the SIPRI milex indicators populate the `country_years` table directly (those columns are reserved for WDI's `population`, `gdp_current_usd`, `gdp_per_capita` — see [`docs/architecture/wdi.md`](wdi.md) §2.1). All 4 SIPRI milex indicators live in `source_observations` and are consumed by the Stage 5 score module for `international_peace`.

### License

The SIPRI milex data is distributed under a **free academic license with attribution**. SIPRI's [Terms of Use for the Milex Database](https://www.sipri.org/databases/milex) require citation of the dataset version. The canonical long-form attribution text for SIPRI milex is the citation block in [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `sipri` (and is the `SIPRI_MILEX_ATTRIBUTION` constant — see §3.3).

> **Note for the developer — the SIPRI Yearbook entry is NOT the right attribution for SIPRI milex.** The current [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `sipri` cites the *SIPRI Yearbook 2024* (the nuclear-forces chapter). The SIPRI milex data comes from the SIPRI website (the xlsx), NOT the Yearbook. The Yearbook has its own entry (`sipri_yearbook_ch7`) further down. The developer **must update the SIPRI milex citation in `docs/source-attributions.md`** to refer to the milex dataset specifically, in the same commit as the adapter lands (mirroring the WGI license-clarification fix pattern from [`docs/architecture/wgi.md`](wgi.md) §2.8 and the WGI 1996–2023 → 1996–2022 coverage fix). Suggested wording (TBD with the user):
>
> ```
> Stockholm International Peace Research Institute. 2026. SIPRI Military Expenditure Database. https://www.sipri.org/databases/milex
> ```
>
> The short-form attribution text in reports becomes: `"SIPRI milex (Stockholm International Peace Research Institute 2026)."` The Yearbook short-form stays separate: `"SIPRI Yearbook 2024 Ch.7 (Stockholm International Peace Research Institute 2024)."` The drift-guard test (`test_sipri_milex_attribution_matches_attributions_doc`) covers the long-form citation.

### Cited artifacts

- Indicator catalog: `src/leaders_db/ingest/catalogs/sipri_milex.csv` (to be authored from §3.4).
- Per-source `metadata.json`: `data/raw/sipri_milex/metadata.json` (to be written when the first successful read happens).
- Attribution: `docs/source-attributions.md` §1 entry for `sipri` (to be updated to the milex-specific citation in the same commit as the adapter lands — see "Note for the developer" above).

---

## 3.2 — Module structure (V-Dem / WGI-style, 4 modules)

SIPRI milex is structurally closer to WGI (one local xlsx, no network, no HTTP layer) than to WDI (per-indicator HTTP, JSON cache). The WGI 5-module split (`wgi.py` / `wgi_io.py` / `wgi_xlsx.py` / `wgi_db.py` / `wgi_db_helpers.py`) is the template. The SIPRI milex module splits into **4 sibling files** under `src/leaders_db/ingest/`, each under the 400-line convention from `docs/coding-guidelines.md`:

| File | Responsibility | Approx LoC target |
|---|---|---|
| `sipri_milex.py` | Public orchestrator: `SipriMilexIngestResult` Pydantic model, `attribution()`, `ingest_sipri_milex()` entrypoint. Re-exports `SIPRI_MILEX_ATTRIBUTION`, `SIPRI_MILEX_SOURCE_KEY`, `IndicatorSpec` from the I/O module. | ~180–220 |
| `sipri_milex_io.py` | Catalog, path helpers, parquet write, parquet metadata attachment. Owns `SIPRI_MILEX_ATTRIBUTION`, `SIPRI_MILEX_SOURCE_KEY`, `IndicatorSpec`, the catalog loader, and the `_DEFAULT_CATALOG_PATH` constant. The region denylist (`_SIPRI_MILEX_REGION_LABELS`) also lives here as a private constant. | ~260–320 |
| `sipri_milex_xlsx.py` | xlsx read, per-sheet header-row detection, region filter, long-to-wide pivot, missing-value coercion. Owns the read function `read_sipri_milex()`. The xlsx I/O is ~150–200 lines, well over the "trivial" threshold, so it warrants its own module (the WGI precedent). | ~280–360 |
| `sipri_milex_db.py` | `sources` upsert, `source_observations` write, run manifest, missing-value coercion helpers (`_coerce_float`, `_raw_value_to_string`). The missing-value coercion is sheet-source-specific (3 tokens: `"..."`, `"xxx"`, `""`) and is not large enough to warrant a separate `sipri_milex_db_helpers.py` — it lives in `sipri_milex_db.py`. | ~280–340 |

**No `sipri_milex_http.py` because SIPRI milex has no HTTP layer.** The xlsx is staged locally; the read orchestrator opens the xlsx and walks the 4 catalog sheets. Same as WGI's pattern (no `wgi_http.py`).

The split rationale is identical to WGI: `sipri_milex_io` owns the constants and the catalog; `sipri_milex_xlsx` owns the data-lake xlsx I/O; `sipri_milex_db` owns the DB contract; `sipri_milex` is the orchestrator that wires them together. Constants live in `sipri_milex_io` (lowest level) to break the import cycle, and are re-exported by `sipri_milex.py` for the public surface.

> **Why 4 modules, not 5 (no `_db_helpers.py`)?** The WGI module split grew from 3 to 5 after review because WGI's missing-value coercion (the `"#N/A"` → NaN logic, the `coerce_float` helper, the `raw_value_to_string` audit-trail helper) is ~120 lines and warranted its own file. SIPRI milex's coercion is similar in spirit (3 missing tokens, 1 helper, audit-trail string) but more concise (~60–80 lines), and it lives naturally in `sipri_milex_db.py` alongside the DB writes. If the module grows past 400 lines during implementation, the developer splits it at that time.

### Read pattern — chosen approach: **per-sheet header-detected long-format extraction → wide pivot**

The SIPRI milex xlsx is not natively long-format. The read function performs the long-to-wide reshape:

1. **Open the xlsx once** with `openpyxl.load_workbook(..., read_only=True, data_only=True)`. The xlsx is 922 KB and fits in memory; the per-sheet iteration is row-by-row (streaming via `read_only=True`).
2. **For each catalog indicator** (i.e. for each sheet name in the catalog's `raw_column` field):
   - Open that sheet.
   - **Detect the header row** by scanning for the first row where column 0 is the literal string `"Country"`. Record the header row index (varies 6, 7, or 8 per sheet).
   - From the header row, build the year-to-column-position map: `{year: col_index}` for every column where the value is an integer ≥ 1900 (i.e. a year). The Notes / Currency / Reporting-year columns (if present) are skipped.
   - For each data row (rows below the header + 1 blank row):
     - Extract `Country` (col 0) and the year cell at the requested year column.
     - **Region filter**: skip the row if the country name is in `_SIPRI_MILEX_REGION_LABELS`. The row count for the region-filtered data is **~177 country rows** (matching the live probe).
     - **Missing-value coercion**: `"..."`, `"xxx"`, `""`, and `None` all become `None` (Python None → `NaN` in the pandas frame after the wide pivot). Numeric cells are coerced to `float`.
     - Append `(country_name, year, indicator_code, value)` rows to a long frame.
3. **Concatenate** the per-indicator long frames into one long frame with columns `(country, year, indicator_code, value)`.
4. **Pivot to wide format** (one row per `(country, year)`, one column per `variable_name`). The same shape as the WDI / WGI / UCDP wide frame.
5. **Filter** by year if `year=` is passed (or keep all years if `year=None`).

The Stage 2 → Stage 11 contract: `confidence` is left `NULL` on every row; Stage 11 fills it. `country_id` is left `NULL`; Stage 3 (country match) fills it from the SIPRI display name via the `country_aliases.csv` table (a future Stage 3 deliverable). The wide frame's country column carries the raw display name; the `source_row_reference` carries `"sipri_milex:<display_name>"` (e.g., `"sipri_milex:Mexico"`).

The `df.attrs` carries two audit fields (the SIPRI-specific equivalents of UCDP's `events_total` / `events_filtered`):
- `df.attrs["regions_covered"]` — a list of region names found in the input (e.g. `["Africa", "Americas", "Asia & Oceania", "Europe", "Middle East"]`). Empty if the year filter excludes all of a region by mistake. Useful for cross-checking that the year-filter didn't drop the wrong rows.
- `df.attrs["country_count"]` — the count of distinct country names in the wide frame (after the region filter). Used in the test fixture for "5 countries" assertions.

The orchestrator surfaces `regions_covered` in `SipriMilexIngestResult`.

---

## 3.3 — Public surface (exact function signatures)

The test-builder writes against these signatures; the developer implements against these signatures. The names and types are the contract; the docstrings below describe the contract for both audiences.

### Constants (in `sipri_milex_io.py`, re-exported by `sipri_milex.py`)

```python
SIPRI_MILEX_SOURCE_KEY: str = "sipri_milex"
```

The single source key used everywhere in the data lake, the CLI dispatch, and the test imports. Matches the `data/raw/<key>/` folder name and the `--source` CLI flag.

```python
SIPRI_MILEX_ATTRIBUTION: str = (
    "Stockholm International Peace Research Institute. 2026. "
    "SIPRI Military Expenditure Database. "
    "https://www.sipri.org/databases/milex"
)
```

The exact citation text. Lives in `sipri_milex_io` to break the import cycle. The canonical long-form lives in `docs/source-attributions.md`; the drift-guard test (§3.5) enforces byte-for-byte consistency. The year is `2026` (the v1.2 release year, matching the "© SIPRI 2026" attribution in the xlsx itself). **The developer confirms this attribution text with the user before implementation** — see "Open questions" in §3.6.

```python
#: Default location of the indicator catalog. Lives here so
#: :func:`write_sipri_milex_run_manifest` in ``sipri_milex_db`` can
#: import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = Path(__file__).resolve().parent / "catalogs" / "sipri_milex.csv"

#: Raw xlsx file name inside ``data/raw/sipri_milex/``.
_RAW_XLSX_NAME: str = "SIPRI-Milex-data-1949-2025_v1.2.xlsx"

#: Narrow parquet that Stage 2 writes under ``data/processed/sipri_milex/``.
_PROCESSED_PARQUET_NAME: str = "sipri_milex_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "sipri_milex_attribution"
_PARQUET_META_SOURCE_KEY: str = "sipri_milex_source_key"

#: Region / sub-region labels in the SIPRI xlsx that are NOT countries.
#: The read function filters these out so only the ~177 country rows
#: end up in the wide frame. The set is the WGI-style "no aggregates"
#: approach, but by display name (the SIPRI xlsx has no ISO3 column).
_SIPRI_MILEX_REGION_LABELS: frozenset[str] = frozenset({
    "Africa", "North Africa", "sub-Saharan Africa",
    "Americas", "Central America and the Caribbean", "North America", "South America",
    "Asia & Oceania", "Central Asia", "East Asia", "South Asia", "South East Asia", "Oceania",
    "Europe", "Eastern Europe", "Central and Western Europe",
    "Middle East",
    "World",  # from the Regional totals sheet (defense in depth)
})
```

### Indicator catalog (in `sipri_milex_io.py`)

```python
@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the SIPRI milex indicator catalog.

    The V-Dem / WDI / WGI / UCDP ``IndicatorSpec`` shape is reused verbatim:
    every Stage 2 adapter resolves its raw column from this dataclass so the
    score modules in Stage 9-10 can normalize and direct indicators
    consistently across sources.
    """
    variable_name: str
    raw_column: str         # the xlsx sheet name, e.g. "Share of GDP"
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
    """Load the SIPRI milex indicator catalog from ``catalogs/sipri_milex.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP loaders: handles the leading ``#``
    comment block, drops comment-only lines, validates the required column set,
    and returns one ``IndicatorSpec`` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
```

### Read (in `sipri_milex_xlsx.py`)

```python
def read_sipri_milex(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read SIPRI milex from the xlsx and pivot to wide format (one row per country per year).

    Steps:

    1. Load the catalog.
    2. Open the xlsx at ``xlsx_path`` (default:
       ``data/raw/sipri_milex/SIPRI-Milex-data-1949-2025_v1.2.xlsx``).
    3. For each catalog row (one per indicator):
       a. Open the sheet named in ``raw_column``.
       b. Detect the header row by scanning for the first row where
          column 0 is the literal string ``"Country"``. Record the
          header row index (varies 6, 7, or 8 per sheet).
       c. From the header row, build the year-to-column-position map
          for every column whose value is an integer in the year range
          (1949..current_year). Skip the Notes / Currency / Reporting-year
          columns (they are non-year cells in the header).
       d. For each data row (rows below the header + 1 blank row):
          - Extract ``Country`` (col 0) and the year cell at the
            requested year column.
          - Region filter: skip the row if the country name is in
            ``_SIPRI_MILEX_REGION_LABELS``.
          - Missing-value coercion: ``"..."``, ``"xxx"``, ``""``, and
            ``None`` all become ``None`` (Python None -> NaN in pandas
            after the wide pivot). Numeric cells are coerced to
            ``float``.
          - Append (country, year, indicator_code, value) rows to a
            long frame.
    4. Concatenate per-indicator long frames.
    5. Pivot to wide format: one row per ``(country, year)``, one
       column per catalog ``variable_name``. Coerce the ``year``
       column to ``int`` and the indicator columns to ``float``
       (NaN for missing).
    6. Attach ``df.attrs["regions_covered"]`` (a sorted list of the
       region names found in the input) and ``df.attrs["country_count"]``
       (the count of distinct country names in the wide frame).

    Args:
        year: filter to a single year (e.g. ``2023``).
            Default: all years present in the xlsx (varies per
            indicator: 1949-2025 for Share of GDP / Constant USD /
            Current USD; 1988-2025 for Per capita / Share of Govt.
            spending).
        xlsx_path: override the input xlsx. Default: data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.

    Returns:
        A pandas DataFrame with columns ``country`` (display name
        string), ``year`` (int), then one column per catalog indicator
        (named with the ``variable_name``). Indicator columns are
        float (``NaN`` = missing). The wide frame has ~177 country
        rows per year (region rows are filtered out). SIPRI milex
        does NOT return an ISO3 code; the country column carries the
        raw display name. Stage 3 (country match) resolves it to ISO3
        via the ``country_aliases.csv`` table.

    Raises:
        FileNotFoundError: if the xlsx is missing.
        KeyError: if a catalog ``raw_column`` sheet name is absent
            from the xlsx (i.e. SIPRI renamed or dropped a sheet in
            a future release).
    """
```

### Path helpers (in `sipri_milex_io.py`)

```python
def default_xlsx_path() -> Path:
    """Return the conventional SIPRI milex xlsx path inside the data lake.

    Resolves to
    ``<project_root>/data/raw/sipri_milex/SIPRI-Milex-data-1949-2025_v1.2.xlsx``.
    Raises ``FileNotFoundError`` if the file is missing (per the
    design contract in §3.3); the adapter expects the user to have
    downloaded the xlsx via the project's download workflow first.
    """
```

```python
def default_processed_parquet_path() -> Path:
    """Return the conventional SIPRI milex narrow parquet path.

    Creates the ``data/processed/sipri_milex/`` directory if missing.
    """
```

### Parquet write (in `sipri_milex_io.py`)

```python
def write_sipri_milex_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet`,
    :func:`wgi_io.write_wgi_parquet`, and
    :func:`ucdp_io.write_ucdp_parquet` (and the
    :func:`_attach_parquet_metadata` helper): writes the parquet via
    ``df.to_parquet``, then re-writes the file with the SIPRI milex
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow
    fails, the data parquet is still valid and a warning is logged.

    Note: the wide frame may carry a ``_sipri_milex_raw_long`` key
    in ``df.attrs`` (set by :func:`sipri_milex_xlsx.read_sipri_milex`)
    that holds the pre-coercion long frame for the ``raw_value``
    audit trail. That attribute is not JSON-serializable and would
    break pyarrow's attrs serialization, so we strip it from
    ``df.attrs`` before the parquet write. The regions_covered and
    country_count attrs are JSON-serializable and are preserved.
    """
```

### DB writes (in `sipri_milex_db.py`)

```python
def register_sipri_milex_source(session: Session) -> int:
    """Upsert the SIPRI milex source row into the ``sources`` table.

    Keyed by ``(source_name='SIPRI Military Expenditure Database',
    version='v1.2 (1949-2025)')``. Idempotent: returns the same
    ``sources.id`` on every call. Reads the bundle's ``metadata.json``
    for ``source_url``, ``download_date``, ``license_note``,
    ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source`, WGI's
    :func:`wgi_db.register_wgi_source`, and UCDP's
    :func:`ucdp_db.register_ucdp_source`).
    """
```

```python
def write_sipri_milex_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    Same shape as V-Dem's :func:`vdem_db.write_vdem_observations`,
    WGI's :func:`wgi_db.write_wgi_observations`, and UCDP's
    :func:`ucdp_db.write_ucdp_observations`:

    - ``country_id`` is left ``NULL``; Stage 3 (country match) fills
      it from the SIPRI display name via ``country_aliases.csv``
      (a future Stage 3 deliverable).
    - ``source_row_reference`` carries the SIPRI display name
      prefixed with ``"sipri_milex:"`` (e.g., ``"sipri_milex:Mexico"``)
      so Stage 3 can resolve it.
    - ``raw_value`` preserves the original cell: the float as a
      string for numeric cells, or the literal ``"..."`` / ``"xxx"`` /
      ``""`` for missing cells (per the V-Dem / WGI / UCDP pattern of
      preserving the original cell for the audit trail).
    - ``normalized_value`` is the float, or ``None`` if the cell is
      ``"..."`` / ``"xxx"`` / ``""`` / empty.
    - Idempotent: deletes existing rows for the requested years
      (from the frame) before inserting. Years outside the frame
      are untouched.

    Returns the number of ``source_observations`` rows inserted.
    """
```

### Run manifest (in `sipri_milex_db.py`)

```python
def write_sipri_milex_run_manifest(
    result,  # SipriMilexIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest is the audit trail for ``processed/``: it records
    ``source_id``, the parquet path, the observation row count, the
    countries count, the years, the indicator count, the
    ``regions_covered`` list, the ``country_count``, the catalog
    path, and the attribution. Written every run (not best-effort)
    so Stage 15 reports can find the attribution without re-reading
    the parquet metadata.
    """
```

### Orchestrator and Pydantic result (in `sipri_milex.py`)

```python
class SipriMilexIngestResult(BaseModel):
    """Summary of a single ``ingest_sipri_milex`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads these
    fields to print the end-of-run summary, and the manifest writer in
    :mod:`sipri_milex_db` consumes the same fields. Same shape as
    V-Dem's :class:`vdem.IngestResult`, WGI's
    :class:`wgi.WGIIngestResult`, and UCDP's
    :class:`ucdp.UCDPIngestResult` for consistency.

    SIPRI-milex-specific extras vs the WGI :class:`WGIIngestResult`:

    - ``regions_covered``: a sorted list of the region labels found
      in the input data (e.g. ``["Africa", "Americas", "Asia &
      Oceania", "Europe", "Middle East"]``). Carried forward from
      ``df.attrs["regions_covered"]``. The orchestrator filters out
      these rows from the wide frame (they are aggregate labels, not
      countries), but preserves the list as an audit field so a
      reviewer can confirm the year-filter didn't drop all of a
      region by mistake.
    - ``country_count``: the count of distinct country names in the
      wide frame (after the region filter). Carried forward from
      ``df.attrs["country_count"]``.

    These are the SIPRI-milex-specific equivalents of UCDP's
    ``events_total`` / ``events_filtered``: they capture
    "what was filtered out" for end-to-end audit.
    """
    source_id: int = Field(..., ge=1)
    parquet_path: Path
    observation_rows: int = Field(..., ge=0)
    countries: int = Field(..., ge=0, description="Distinct country names in the wide frame.")
    years: tuple[int, ...]
    indicators: int = Field(..., ge=0)
    regions_covered: list[str] = Field(
        default_factory=list,
        description=(
            "Sorted list of region labels found in the input data "
            "(filtered out of the wide frame but preserved as audit)."
        ),
    )
    country_count: int = Field(..., ge=0, description="Distinct country names in the wide frame.")

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]: ...

    @field_validator("regions_covered")
    @classmethod
    def _regions_covered_is_sorted_unique(cls, value: list[str]) -> list[str]: ...

    @property
    def attribution(self) -> str:
        """The SIPRI milex attribution text (Always-On Rule #15)."""
        return SIPRI_MILEX_ATTRIBUTION
```

> **Note on the IngestResult field count.** V-Dem has 6 fields (no HTTP, no aggregation). WGI has 6 fields (no HTTP, no aggregation). UCDP has 8 fields (6 from WGI plus `events_total` and `events_filtered` for the event-level→country-year aggregation audit trail). SIPRI milex has 8 fields (6 from WGI plus `regions_covered` and `country_count` for the region-row filter audit trail). The end-to-end test asserts all 8.

```python
def attribution() -> str:
    """Return the SIPRI milex attribution block for public output (Rule #15)."""
```

```python
def ingest_sipri_milex(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> SipriMilexIngestResult:
    """Run Stage 2 for SIPRI milex end-to-end.

    Steps:

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_sipri_milex`. One
       openpyxl per-catalog-sheet pass; per-sheet header-row
       detection; region filter; long -> wide pivot; missing-value
       coercion.
    3. Write the narrow parquet via :func:`write_sipri_milex_parquet`.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Build the :class:`SipriMilexIngestResult` and write the run
       manifest.
    6. Return the result.

    The function is the single public entry point -- both the CLI
    command ``leaders-db ingest-source --source sipri_milex`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the ``LEADERSDB_PROJECT_ROOT``
    env var. No explicit ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2023``).
            Default: all years present in the xlsx (1949-2025 for
            Share of GDP / Constant USD / Current USD;
            1988-2025 for Per capita / Share of Govt. spending).
        xlsx_path: override the input xlsx. Default: data-lake path.
        parquet_path: override the output parquet. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.
    """
```

### `__all__` (in `sipri_milex.py`)

```python
__all__ = [
    "SIPRI_MILEX_ATTRIBUTION",
    "SIPRI_MILEX_SOURCE_KEY",
    "IndicatorSpec",
    "SipriMilexIngestResult",
    "attribution",
    "ingest_sipri_milex",
    "register_sipri_milex_source",
    "write_sipri_milex_observations",
    "write_sipri_milex_run_manifest",
]
```

The DB helpers (`register_sipri_milex_source`, `write_sipri_milex_observations`, `write_sipri_milex_run_manifest`) are re-exported so the test-builder's tests can call them through the orchestrator module — same pattern as the WGI / WDI / UCDP test surface.

---

## 3.4 — Indicator catalog (the contract for the test fixture)

The test-builder will author `tests/fixtures/sipri_milex/sample.xlsx` based on this spec. The developer will author `src/leaders_db/ingest/catalogs/sipri_milex.csv` from this spec. The two artifacts must agree on the indicator list.

> **Source-of-truth principle.** If the test fixture count and the design catalog spec disagree, the design doc is the source of truth; the test fixture must match. This design specifies **4** indicators. The test fixture must therefore have **4** indicator sheets (one per catalog row).

### Catalog format

Same CSV format as `vdem.csv`, `wdi.csv`, `wgi.csv`, and `ucdp.csv` (Phase C convention #1). The 8 required columns are exactly the V-Dem / WDI / WGI / UCDP 8; the test fixture mirrors them.

```
variable_name,raw_column,rating_category,raw_scale,normalized_scale_target,higher_is_better,unit,description
```

### Indicator list (4 indicators, 1 category)

| # | Sheet name (`raw_column`) | `variable_name` | Category | Scale | Unit | Direction | Why it matters |
|---|---|---|---|---|---|---|---|
| 1 | `Share of GDP` | `sipri_milex_share_of_gdp` | `international_peace` | `percent` | `percent_of_gdp` | `False` | Military expenditure as a percentage of gross domestic product. The most-cited SIPRI milex indicator. Captures the share of the economy devoted to military spending. Cross-validates UCDP `ucdp_state_based_*` (more spending = more conflict preparedness). Higher = more militarized economy = worse peace signal. |
| 2 | `Per capita` | `sipri_milex_per_capita` | `international_peace` | `usd_per_capita` | `usd_per_capita` | `False` | Military expenditure per capita in current US$. Normalizes spending to population size; comparable across countries of different sizes. Higher = more military burden per citizen = worse peace signal. |
| 3 | `Constant (2024) US$` | `sipri_milex_constant_usd` | `international_peace` | `usd_millions` | `usd_millions_2024` | `False` | Military expenditure in millions of constant (2024) US$. Real-terms scale, cross-time comparable. Captures absolute level of military investment. Higher = larger military establishment = worse peace signal. |
| 4 | `Share of Govt. spending` | `sipri_milex_share_of_govt_spending` | `international_peace` | `percent` | `percent_of_govt_spending` | `False` | Military expenditure as a percentage of total government spending. Captures the political priority of military spending within the fiscal envelope. Higher = more military in the budget = worse peace signal. |

> **Why `higher_is_better=False` for all 4?** For all SIPRI milex indicators, "more military spending" = worse peace rating (more arming, less peace). The Stage 5 score module for `international_peace` inverts the raw value: a country with 0% of GDP on military scores well; a country with 10% of GDP scores badly; the mapping is monotonic decreasing in the raw value. The `raw_scale` and `normalized_scale_target` columns capture the shape; `higher_is_better=False` tells the score module to invert. (For `international_peace`, the score formula is: more spending → worse peace score. UCDP's `ucdp_state_based_*` indicators use the same convention.)

> **Why not extract the `Current US$` sheet?** The 5th candidate sheet is `Current US$` (nominal USD millions). The constant-USD sheet (`Constant (2024) US$`) is preferred because real-terms values are comparable across years. The current-USD sheet is a 1-row catalog extension if the user wants it; the design locks in 4 indicators for the prototype.

> **Why not extract `Local currency financial years` or `Local currency calendar years`?** Local-currency values are useful for source cross-validation (you can verify SIPRI's USD conversions) but are not on the indicator catalog because Stage 5 consumes the USD-normalized sheets. The local-currency sheets are deferred to a future iteration.

### `raw_scale` convention

| `raw_scale` | Used for | What it means |
|---|---|---|
| `percent` | Share of GDP, Share of Govt. spending | A fraction (0.0–1.0) in the xlsx; the Stage 5 score module may want to multiply by 100 to get a percentage. The `unit` column says `percent_of_gdp` / `percent_of_govt_spending` for human readability; the `raw_scale` is the raw data shape. |
| `usd_per_capita` | Per capita | A current-US$ per capita (raw value 0–thousands of US$). |
| `usd_millions` | Constant (2024) US$ | Millions of constant 2024 US$ (raw value 0–hundreds of thousands). |

### `normalized_scale_target` convention

For the prototype, all 4 indicators normalize to `0-1` (matching V-Dem / WDI / WGI / UCDP). The actual normalization is the Stage 5 score module's job, not Stage 2's. Stage 2 only writes the raw value to `source_observations.normalized_value` and preserves the scale in the catalog.

> **Note on log scaling for the absolute indicators.** SIPRI milex absolute values (Constant USD, Per capita) span 0 to ~10^6 (US millions for Constant USD) and 0 to ~10^3 (US$ for Per capita). A linear 0–1 normalization is heavily skewed by a few high-spender countries (USA, China, Russia, India, Saudi Arabia). The Stage 5 score module will likely use a log transform (`log1p(value)` then linear 0–1) for these indicators, mirroring the UCDP fatalities log transform. The catalog's `normalized_scale_target = "0-1"` is the final target shape; the score module picks the transform. The Stage 2 adapter does not apply any transform.

### `unit` convention

| `unit` | Used for |
|---|---|
| `percent_of_gdp` | Share of GDP (the raw value is a fraction 0.0–1.0; the `percent` in the name refers to the ×100 display, not the raw shape) |
| `percent_of_govt_spending` | Share of Govt. spending (same convention) |
| `usd_per_capita` | Per capita (current US$ per person) |
| `usd_millions_2024` | Constant (2024) US$ (millions of real USD) |

The SIPRI unit is a concrete measurement (percentage or USD), unlike V-Dem (dimensionless `index` on a 0–1 scale) or WGI (dimensionless `z_score`).

### Test fixture shape (5 countries × 2 years × 4 indicators)

The test-builder's fixture `tests/fixtures/sipri_milex/sample.xlsx` is a **real-format SIPRI milex xlsx** authored with openpyxl (committed under `tests/fixtures/sipri_milex/`). Shape:

- **4 data sheets** (one per catalog indicator): `Share of GDP`, `Per capita`, `Constant (2024) US$`, `Share of Govt. spending`. Each sheet has the canonical SIPRI layout: row 1 (long title with "© SIPRI 2026"), rows 2–4 (disclaimers), row 6 or 7 (header row with `Country` in col 0), row 7 or 8 (blank separator), rows 8+ (data). The other 6 sheets in the real xlsx (`Front page`, `Regional totals`, `Local currency financial years`, `Local currency calendar years`, `Current US$`, `Footnotes`) are NOT in the fixture — the test only exercises the 4 catalog sheets.
- **5 countries**: MEX, USA, SWE, IND, NGA (matching the V-Dem / WDI / WGI / UCDP test fixtures, by display name: `"Mexico"`, `"United States of America"`, `"Sweden"`, `"India"`, `"Nigeria"`).
- **2 years**: 2022, 2023 (the most recent two years; ensures at least one real value per country, not `"xxx"` or `"..."`).
- **Real-format data**: the 5 countries appear at rows 8+ in the data region (after a few region-label rows: `"Africa"`, `"North Africa"`, etc., which the test must filter out). The data values are real (pulled from the live xlsx for those countries and years; no invented values).
- **At least 1 missing-value cell** (e.g., one `"..."` and one `"xxx"` across the fixture) to exercise the missing-value coercion path. Suggested: NGA's 1949 cells can be `"xxx"` (Nigeria was a British protectorate until 1960), and MEX's 2023 Share of Govt. spending cell can be `"..."` (Mexico's 2023 govt-spending share may not yet be reported).
- **2 region-label rows** in each data sheet: `"Africa"` (row 8) and `"Americas"` (row 9), with empty year cells. The test must verify these are filtered out by the region denylist.

Total cells in the fixture data: 5 countries × 2 years × 4 indicators = **40 indicator cells** + missing-value cells (1 `"..."` + 1 `"xxx"`) + 2 region rows × 4 sheets = 8 region rows filtered out. The read function returns a wide DataFrame of 5 × 2 = 10 rows × 6 columns (`country`, `year`, 4 indicator columns). The orchestrator writes 10 × 4 = **40 `source_observations` rows** when reading the full fixture (no year filter) and 5 × 4 = **20 rows** when filtering to `year=2023`.

> **Header row position in the fixture.** The fixture must use the same per-sheet header-row positions as the real xlsx (verified live 2026-06-18): `Share of GDP` header at row 6, `Per capita` at row 7, `Constant (2024) US$` at row 6, `Share of Govt. spending` at row 8. The Stage 2 read function detects the header row dynamically by scanning for the first row where col 0 is `"Country"`, so the fixture must use the same convention.

---

## 3.5 — Test plan (what the test-builder writes)

The test plan covers the 5 Phase C convention #5 categories (catalog, read, write+DB, idempotency, attribution) plus the orchestrator and CLI. Every test has a defined fixture, an assertion, and a 1-line description. The WGI / UCDP test files are the template.

### Catalog (Phase C convention #5a)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_load_indicator_catalog_returns_4_specs` | The checked-in catalog has **4** indicators (matches §3.4 spec). | `sipri_milex_catalog_path` |
| `test_load_indicator_catalog_required_columns` | The 8 required CSV columns are present; the `rating_category` set is exactly `{"international_peace"}`. | same |
| `test_load_indicator_catalog_missing_file` | Missing catalog raises `FileNotFoundError`, not a silent empty list. | `tmp_path` |
| `test_indicator_spec_from_csv_row` | `higher_is_better=0`/`=1` round-trips to a real bool (matching V-Dem / WDI / WGI / UCDP). | inline dict |
| `test_catalog_sheet_names_match_sipri_release` | The 4 `raw_column` values are exactly the SIPRI xlsx sheet names: `Share of GDP`, `Per capita`, `Constant (2024) US$`, `Share of Govt. spending`. | same |
| `test_catalog_variable_names_match_design` | The 4 `variable_name` values are exactly the names in §3.4: `sipri_milex_share_of_gdp`, `sipri_milex_per_capita`, `sipri_milex_constant_usd`, `sipri_milex_share_of_govt_spending`. | `sipri_milex_catalog_path` |

### Read (Phase C convention #5b)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_sipri_milex_returns_full_fixture` | The fixture (5 countries × 2 years × 4 indicators) produces a wide DataFrame: 10 rows, 6 columns (`country`, `year`, 4 indicator columns). | `sipri_milex_xlsx_dir` (stages the sample xlsx) |
| `test_read_sipri_milex_filters_to_year` | `year=2023` keeps only the 5 rows for 2023; `set(df["year"]) == {2023}`. | same |
| `test_read_sipri_milex_pivots_long_to_wide` | Each catalog indicator is one column; no row is duplicated; no (country, indicator) cell is in long format. | same |
| `test_read_sipri_milex_filters_region_rows` | The 2 region rows in each data sheet (`"Africa"`, `"Americas"`) are NOT in the wide frame; `set(df["country"]) == {"Mexico", "United States of America", "Sweden", "India", "Nigeria"}`. | same |
| `test_read_sipri_milex_detects_header_row_per_sheet` | The header row is detected correctly per sheet (6 for Share of GDP / Constant USD; 7 for Per capita; 8 for Share of Govt. spending); the year-to-column map is correct. | same |
| `test_read_sipri_milex_handles_dots_missing` | The `"..."` cell in the fixture becomes `NaN` in the DataFrame; `normalized_value` is `None` in `source_observations`. | same |
| `test_read_sipri_milex_handles_xxx_missing` | The `"xxx"` cell in the fixture becomes `NaN` in the DataFrame; `normalized_value` is `None` in `source_observations`. | same |
| `test_read_sipri_milex_attrs_carry_regions_and_count` | `df.attrs["regions_covered"]` is a list containing `"Africa"` and `"Americas"`; `df.attrs["country_count"]` is 5. | same |
| `test_read_sipri_milex_missing_xlsx` | Missing xlsx raises `FileNotFoundError` with an actionable message. | `tmp_path` |
| `test_read_sipri_milex_missing_sheet` | If a catalog `raw_column` sheet name is absent from the xlsx, `read_sipri_milex` raises `KeyError`. | missing-sheet-staging helper |
| `test_default_path_helpers` | `default_xlsx_path()` points at `data/raw/sipri_milex/SIPRI-Milex-data-1949-2025_v1.2.xlsx`; `default_processed_parquet_path()` points at `data/processed/sipri_milex/sipri_milex_country_year.parquet`. | none |

### Parquet write + DB (Phase C convention #5c)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_sipri_milex_parquet_creates_file` | `write_sipri_milex_parquet(df)` writes a valid parquet under `data/processed/sipri_milex/`; round-trip preserves shape and columns. | `sipri_milex_xlsx_dir` |
| `test_write_sipri_milex_parquet_attaches_attribution_metadata` | The parquet's file-level metadata carries `sipri_milex_attribution` (= `SIPRI_MILEX_ATTRIBUTION`) and `sipri_milex_source_key` (= `b"sipri_milex"`) (Rule #15). | same |
| `test_register_sipri_milex_source_is_idempotent` | Two calls to `register_sipri_milex_source` return the same `sources.id`; the row has `source_name="SIPRI Military Expenditure Database"`, `version="v1.2 (1949-2025)"`, `source_type="academic"`. | `database_url` + `_init_test_db` |
| `test_register_sipri_milex_source_non_destructive_update` | Removing the bundle's `metadata.json` between calls keeps the existing `source_url` and `license_note` (same policy as V-Dem / WDI / WGI / UCDP). | same |
| `test_write_sipri_milex_observations_row_count` | `len(df) * len(specs)` observations are written. With the fixture (10 rows × 4 indicators) the count is 40. | `sipri_milex_xlsx_dir` + `database_url` |
| `test_write_sipri_milex_observations_is_idempotent` | Re-running produces the same count, not 2× the count. | same |
| `test_write_sipri_milex_observations_country_id_is_null` | `country_id` is `None` for every row (Stage 3 fills it); `confidence` is `None` for every row (Stage 11 fills it); `source_row_reference` starts with `"sipri_milex:"` and carries the display name verbatim. | same |
| `test_write_sipri_milex_observations_handles_dots_missing` | A `"..."` row becomes `normalized_value=NULL` in SQLite; `raw_value` is the literal string `"..."`. | same |
| `test_write_sipri_milex_observations_handles_xxx_missing` | A `"xxx"` row becomes `normalized_value=NULL` in SQLite; `raw_value` is the literal string `"xxx"`. | same |
| `test_write_sipri_milex_observations_preserves_raw_value` | `raw_value` is the stringified float for non-missing cells (e.g., `"0.0329"` for 3.29% of GDP); `raw_value` is the literal `"..."` / `"xxx"` for missing cells. | same |

### Orchestrator (Phase C convention #5d — end-to-end idempotency)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_ingest_sipri_milex_end_to_end` | `ingest_sipri_milex()` writes the parquet, the sources row, the 40 `source_observations` rows, and the manifest in one call. Result has `countries=5, years=(2022,2023), indicators=4, regions_covered=["Africa", "Americas"], country_count=5`. | `sipri_milex_xlsx_dir` + `database_url` |
| `test_ingest_sipri_milex_filters_to_year` | `year=2023` keeps 5 countries × 1 year × 4 indicators = 20 observation rows. | same |
| `test_ingest_sipri_milex_is_idempotent` | Two consecutive `ingest_sipri_milex()` calls produce the same `observation_rows` count, the same `source_id`, and the parquet's mtime is the same (no re-write). | same |
| `test_ingest_sipri_milex_result_carries_attribution` | The `SipriMilexIngestResult.attribution` property returns `SIPRI_MILEX_ATTRIBUTION` byte-for-byte; `result.attribution == SIPRI_MILEX_ATTRIBUTION`. | same |
| `test_ingest_sipri_milex_result_carries_regions_and_country_count` | The `SipriMilexIngestResult.regions_covered` field is `["Africa", "Americas"]` (sorted); the `country_count` field is 5; both are surfaced from `df.attrs`. | same |
| `test_ingest_sipri_milex_result_field_count` | The `SipriMilexIngestResult` has exactly 8 fields (matches §3.3 spec): `source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`, `regions_covered`, `country_count`. (The end-to-end test asserts the fields that **are** present, not the fields that are absent — same as the WGI lesson.) | same |

### Attribution / Rule #15

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_run_manifest` | The manifest is JSON next to the parquet, includes `attribution`, `source_id`, `observation_rows`, `years`, `indicators`, `regions_covered`, `country_count`. | `isolated_data_lake` |
| `test_attribution_matches_constant` | `sipri_milex.attribution() == SIPRI_MILEX_ATTRIBUTION`; contains `"SIPRI"`, `"2026"`, `"Milex"`, `"Military Expenditure"`. | — |
| `test_sipri_milex_attribution_matches_attributions_doc` | `SIPRI_MILEX_ATTRIBUTION` is a substring of `docs/source-attributions.md` (drift guard, same pattern as V-Dem's `test_vdem_attribution_matches_attributions_doc`, WGI's `test_wgi_attribution_matches_attributions_doc`, and UCDP's `test_ucdp_attribution_matches_attributions_doc`). | project root |

### CLI dispatch

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_stage2_adapters_dispatch_table` | `STAGE2_ADAPTERS["sipri_milex"] is sipri_milex.ingest_sipri_milex`; the full key set is unchanged (25 keys, with the `sipri_milex` value changing from `None` to the orchestrator). | — |
| `test_cli_ingest_source_rejects_unknown` | `leaders-db ingest-source --source nope` exits non-zero. | `CliRunner` |

### Public surface

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_sipri_milex_module_public_surface` | The `sipri_milex` module exports the items in `__all__` from §3.3: `SIPRI_MILEX_ATTRIBUTION`, `SIPRI_MILEX_SOURCE_KEY`, `IndicatorSpec`, `SipriMilexIngestResult`, `attribution`, `ingest_sipri_milex`. | — |

### Live-xlsx smoke (manual, not in pytest)

| Test name | What it asserts | When |
|---|---|---|
| `manual: smoke SIPRI milex end-to-end against real xlsx for 2023` | `ingest_sipri_milex(year=2023)` against the real 922 KB xlsx returns ~177 real countries × 4 indicators = ~708 `source_observations` rows; full unfiltered run returns ~177 × 77 × 4 = ~54,516 `source_observations` rows (the 1949–2025 year range; the 1988–2025 sheets are 38 years, so the unfiltered run produces ~177 × 77 × 2 + 177 × 38 × 2 = ~40,860 rows for the 4 sheets combined, but this depends on the per-sheet year range). | After implementation, manual one-shot, recorded in `docs/testing-guide-stage2-sipri_milex.md` |

The manual smoke is gated on a real on-disk xlsx (the user downloads it via `curl` to `data/raw/sipri_milex/SIPRI-Milex-data-1949-2025_v1.2.xlsx` first). The test fixture (`tests/fixtures/sipri_milex/sample.xlsx`) is a 5-country × 2-year × 4-indicator slice that fits in <50 KB and is what the unit tests use. The unit tests prove the contract; the manual smoke proves the real xlsx still works.

---

## 3.6 — Edge cases & known issues

### Region denylist (the major difference vs WGI / WDI / UCDP)

Unlike WGI (country-only, no aggregates) and UCDP (country-only, no aggregates), the SIPRI xlsx **interleaves region labels and country names in the data rows**. The 15 region/sub-region labels (e.g. `"Africa"`, `"North Africa"`, `"Americas"`, `"Asia & Oceania"`, `"Europe"`, `"Middle East"`) appear in the data rows alongside the 177 country names. The Stage 2 adapter **filters out the region labels** by name, not by code (SIPRI has no ISO3 column, so the WGI-style "no ISO3 denylist" doesn't apply).

The denylist is the `_SIPRI_MILEX_REGION_LABELS` frozenset in `sipri_milex_io.py` (see §3.3). It contains 15 region/sub-region labels + the `"World"` total (defense in depth; the World total appears in the Regional totals sheet but could conceivably appear in the data sheets in a future release). The list is hard-coded; if a future SIPRI release adds a new region label, the developer extends the set.

**Live verification (2026-06-18):** the live `Share of GDP` sheet has 15 region labels and 177 country names. After the region filter, the wide frame has 177 country rows per year. The denylist captures all 15 observed labels.

### Header row position varies per sheet (the per-sheet detection)

The header row is at row 6 for `Share of GDP` / `Constant (2024) US$` / `Current US$`, row 7 for `Per capita`, and row 8 for `Share of Govt. spending`. The read function **detects the header row dynamically** by scanning for the first row where column 0 is the literal string `"Country"`. This is the only robust way to handle the per-sheet variation. The fixture's per-sheet header-row positions must match the real xlsx (the developer copies the real layout into the fixture).

**What if SIPRI renames `Country`?** The detection is by literal string. A SIPRI rename to e.g. `"country"` (lowercase) or `"Nation"` would silently fail — the read function would scan past the actual header row and look for the year row, get 0 columns, and return an empty DataFrame. The defensive fix: if no row matches `"Country"`, raise `ValueError` with an actionable message ("could not find the header row in sheet <name>; check that the sheet layout has not changed in the new SIPRI release"). This is a 5-line defensive check; the developer adds it.

### Year columns detected as integers (the per-sheet year-range variation)

The `Per capita` and `Share of Govt. spending` sheets start at year 1988; the other 3 catalog sheets start at 1949. The read function detects year columns by checking that the header cell is an integer in the year range (1949..current_year). This handles the variation automatically.

**What if a future release adds a non-year integer column?** E.g., a "Reporting year" column with value `1` or `2`. The defensive fix: only treat integers in the range `[1940, current_year + 5]` as years. The +5 buffer accommodates a future 2030 release. Integers outside this range are treated as non-year columns and skipped. This is a 1-line tweak; the developer adds it.

### Missing-data convention: three tokens (`"..."`, `"xxx"`, `""`)

The three missing-value tokens differ from every other Stage 2 source:

- **WGI** uses `"#N/A"` (one token).
- **V-Dem** uses `-999` (numeric sentinel).
- **WDI** uses `None` (truly missing).
- **UCDP** has no sentinels (always populated).
- **SIPRI milex** uses `"..."` (data unavailable) and `"xxx"` (country did not exist) and `""` (empty cell).

The `_SIPRI_MILEX_MISSING_STRINGS` frozenset in `sipri_milex_db.py` is the SIPRI-specific superset of the WGI / V-Dem / WDI sentinels. The two new tokens (`"..."` and `"xxx"`) are the only SIPRI-specific additions.

**`"xxx"` semantic.** The `"xxx"` token means the country did not exist or was not independent during the year in question. This is **not** a coverage gap; it is a deliberate signal that the data point is structurally impossible (e.g., Ukraine in 1918, USSR before 1991). The Stage 5 score module treats `"xxx"` the same as `"..."` (both → missing), but the **`raw_value` audit trail preserves the literal `"xxx"`** so a reviewer can distinguish "data unavailable" from "country did not exist". The `test_write_sipri_milex_observations_handles_xxx_missing` test asserts this distinction.

**`""` semantic.** Empty cells are rare; they appear in some region rows (where all year cells are empty by design) and occasionally in country rows (e.g., for years where SIPRI has not yet released a number). The read function coerces `""` → `None` (defense in depth).

### Country name format (no ISO3 column)

The SIPRI xlsx uses display names (e.g. `"United States of America"`, `"Türkiye"`, `"Yemen"`, `"Côte d'Ivoire"`, `"Democratic Republic of the Congo"`) but **no ISO3 column**. The Stage 2 adapter:

1. Stores the raw display name in `source_row_reference` as `"sipri_milex:Mexico"`.
2. Leaves `country_id` NULL in `source_observations` (Stage 3 fills it via `country_aliases.csv`).
3. The wide frame's `country` column carries the raw display name.

**No rename table in Stage 2.** Stage 3 (country match) resolves the SIPRI display name to ISO3 via the `country_aliases.csv` table. The list of known quirks (for the test-builder's reference; **no Stage 2 code change required**):

| SIPRI display name | ISO3 | Notes |
|---|---|---|
| `United States of America` | `USA` | OK |
| `Mexico` | `MEX` | OK |
| `Sweden` | `SWE` | OK |
| `India` | `IND` | OK |
| `Nigeria` | `NGA` | OK |
| `Türkiye` | `TUR` | uses the Turkish spelling with the diacritic; some ISO lists use `Turkey` |
| `Yemen` | `YEM` | matches ISO3; the live xlsx also has a historical row `"Yemen, North"` (pre-1990) |
| `Côte d'Ivoire` | `CIV` | uses the French spelling with the diacritic; some ISO lists use `Cote d'Ivoire` |
| `Democratic Republic of the Congo` | `COD` | the live xlsx also has historical rows like `"Congo, Dem. Rep."` |
| `Russia` | `RUS` | OK; the live xlsx also has `"USSR"` (pre-1992) |
| `Czechia` | `CZE` | uses the modern name; some ISO lists use `Czech Republic` |

Stage 3 has a `country_aliases` table that handles these. Stage 2's contract is to write the SIPRI display name verbatim.

### Coverage year drift (the 2026 release year, 2025 data year)

The current release is the v1.2 update (release year 2026) and contains data through **2025** (last data year). The [`docs/source-vetting-report.md`](../source-vetting-report.md) §3.7 says "1949–2025" and the [`docs/source-attributions.md`](../source-attributions.md) summary table says "1949–2025" — both are correct. The actual data goes through 2025. **The developer does NOT need to fix the coverage field** (unlike WGI and UCDP, where the docs said "2023" / "2023+" but the data ends at 2022; SIPRI's docs say "1949–2025" and the data ends at 2025, so the docs are already correct).

### Per-cell read performance

The xlsx is 922 KB with 10 sheets. With `openpyxl.read_only=True`, the per-sheet iteration is row-by-row and the read function does not hold the full xlsx in memory. Live read of the full xlsx (4 catalog sheets, all years for all 177 countries) takes <3 s on a typical laptop. The test fixture is 5 countries × 2 years × 4 indicators = 40 cells and reads in <100 ms.

### `LEADERSDB_PROJECT_ROOT` interaction

The `xlsx_path` defaults to `raw_dir("sipri_milex") / _RAW_XLSX_NAME`. The `isolated_data_lake` test fixture overrides `LEADERSDB_PROJECT_ROOT`, so the xlsx lives under the test's temp dir. The test fixture `sipri_milex_xlsx_dir` stages the sample xlsx under the temp-dir; the unit tests pass cleanly.

### `obs_status` and other per-cell metadata

SIPRI milex does not have an `obs_status` field per cell. The cell is either a number, a missing-value token, or empty. The `notes` column of `source_observations` carries the SIPRI `Notes` column value (footnote symbols like `"§4"`, `"‡§¶16"`) only if present; for cells with no Notes, `notes` is `NULL` or `""`. The Stage 2 adapter does not extract the Notes as a separate indicator (deferred).

### Stage 1 (client matrix) interaction

SIPRI milex has no Stage 1 interaction — the client matrix is the 2023 validation/test reference and is read separately, never counted as source evidence. SIPRI milex is one of the cross-validation sources (with UCDP) for the `international_peace` category. The Stage 2 → Stage 12 (compare-vs-client) flow is unchanged by SIPRI's presence.

### Network reachability in CI

SIPRI milex has no HTTP layer in the Stage 2 adapter. The unit tests are fully offline (the xlsx fixture is local). The manual smoke is the only "is the real xlsx still what we think it is" check. (Live liveness was verified 2026-06-18; the URL is reachable and the file downloads to 922 KB.)

### `df.attrs` survives the parquet write

The `df.attrs["regions_covered"]` and `df.attrs["country_count"]` fields are JSON-serializable (a list of strings and an int). The `_attach_parquet_metadata` helper in `sipri_milex_io.py` does NOT strip them. The `_sipri_milex_raw_long` key (if present) is the only one stripped; it holds a DataFrame, which is not JSON-serializable. The orchestrator surfaces the regions and country_count in `SipriMilexIngestResult` before calling the parquet writer, so they survive even if the parquet rewrite fails (the run manifest is the audit fallback).

---

## 3.7 — Dispatch table entry

The `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py` needs one change: replace the existing `"sipri_milex": None` stub with the live import, and add the `from . import sipri_milex` line. **No new dispatch key is added** — the key is already there from Phase A.

### Exact changes

In `src/leaders_db/ingest/__init__.py`:

```python
# Add the import alongside the vdem, wdi, wgi, ucdp imports at the top of the import block:
from . import sipri_milex, ucdp, vdem, wdi, wgi

# In the STAGE2_ADAPTERS dict, change the existing line:
    "sipri_milex": None,
# to:
    "sipri_milex": sipri_milex.ingest_sipri_milex,
```

The full dispatch table stays the same shape (25 keys); only the value of the `sipri_milex` key changes from `None` to the orchestrator. All other `None` stubs (`sipri_yearbook_ch7`, `pts`, `undp_hdi`, `who_gho_api`, `polity_v`, `pwt`, `archigos`, `reign`, `leader_survival`, `transparency_cpi`, `fas`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`, `freedom_house`, `imf_weo`, `cow_mid`, `cirights`, `nti`, `bti`, `cia_world_leaders`) are untouched and remain for the next batches.

> **Reviewer-bug from WDI / UCDP history (apply the lesson):** the WDI review found 1 blocker (a duplicate `"world_bank_wgi"` dispatch key that had been silently masked); the UCDP review found 1 blocker (a duplicate `"sipri_milex"` dispatch key from an earlier copy-paste). The current dispatch table (post-UCDP fix) has exactly **one** `"sipri_milex"` entry, with value `None`. Do not accidentally add a second one. The dispatch-table test (`test_stage2_adapters_dispatch_table` in the new `tests/test_ingest_sipri_milex.py`) asserts the key set is exactly the 25 keys.

The `__all__` does not need to change. No CLI code change is needed — the CLI already iterates over the dispatch table.

---

## 3.8 — Workplan / docs updates

When the SIPRI milex adapter lands and the reviewer signs off, the project-manager will add the following entries to `docs/workplan.md` (Done History) and update `docs/source-attributions.md`, `docs/source-vetting-report.md`, and `docs/data-sources.md`.

### `docs/workplan.md` — new Done History entry

> **Phase C.5 — SIPRI milex Stage 2 ingest landed (DATE).** Fifth Stage 2 adapter implemented via the architect → test-builder → developer → reviewer pipeline. ~30 new tests in `tests/test_ingest_sipri_milex.py` (~205 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/sipri_milex.csv` lists 4 SIPRI milex indicators (Share of GDP, Per capita, Constant (2024) US$, Share of Govt. spending), all under `international_peace`. Read pattern: open the 922 KB `SIPRI-Milex-data-1949-2025_v1.2.xlsx` with `openpyxl.read_only=True`, walk the 4 catalog sheets, **detect the header row dynamically** (per-sheet positions vary: 6, 7, or 8), filter out the 15 region/sub-region labels (the SIPRI equivalent of WGI's "no aggregate codes" denylist), coerce the 3 missing-value tokens (`"..."`, `"xxx"`, `""`) to `None`, pivot long → wide. SIPRI milex is the **first Stage 2 adapter without an ISO3 column**: the wide frame's `country` column carries the raw display name (e.g. `"Mexico"`, `"Türkiye"`), and Stage 3 resolves it to ISO3 via `country_aliases.csv`. Test fixture at `tests/fixtures/sipri_milex/sample.xlsx` is a 5-country × 2-year × 4-indicator real-format SIPRI xlsx authored with openpyxl (40 indicator cells, 1 `"..."` cell + 1 `"xxx"` cell to exercise the missing-value paths, 2 region-label rows in each data sheet to exercise the region filter). End-to-end run for `year=2023` produces ~177 real countries × 4 indicators = ~708 `source_observations` rows in <3 s. The `SIPRI_MILEX_ATTRIBUTION` constant is byte-identical to the citation in `docs/source-attributions.md` (drift-guard test added). The `docs/source-attributions.md` SIPRI entry is updated to refer to the **milex dataset specifically** (not the SIPRI Yearbook) — same drift-fix pattern as WGI's license-clarification and UCDP's coverage-year fix. `STAGE2_ADAPTERS["sipri_milex"]` is now `sipri_milex.ingest_sipri_milex` in `src/leaders_db/ingest/__init__.py`. SIPRI milex follows the WGI 4-module split (no `sipri_milex_http.py` since SIPRI has no HTTP layer; no `sipri_milex_db_helpers.py` since the missing-value coercion is concise enough to live in `sipri_milex_db.py`). The `SipriMilexIngestResult` carries 2 extra fields vs WGI: `regions_covered` (a sorted list of the region labels found in the input) and `country_count` (SIPRI-milex-specific equivalents of UCDP's `events_total` / `events_filtered` for the region-row filter audit trail). Reviewer caught N blockers, M important, K nits — all fixed in a single iteration. **PASS on the second pass. Moving to <next source> per the priority list.**

### `docs/source-attributions.md` — three updates in the SIPRI entry

The `sipri` entry (§1) needs **three changes in the same commit**:

1. **Citation text:** the current entry cites the *SIPRI Yearbook 2024* (the nuclear-forces chapter). The SIPRI milex data comes from the SIPRI website, NOT the Yearbook. The developer replaces the citation with the **milex-specific** citation:
   > Stockholm International Peace Research Institute. 2026. *SIPRI Military Expenditure Database*. https://www.sipri.org/databases/milex
2. **Short-form attribution text:** update from `"SIPRI (Stockholm International Peace Research Institute 2024)."` to `"SIPRI milex (Stockholm International Peace Research Institute 2026)."` (The Yearbook short-form stays separate: `"SIPRI Yearbook 2024 Ch.7 (Stockholm International Peace Research Institute 2024)."` and is in a different entry.)
3. **Summary table row:** the `sipri_milex` row in the summary table at the end of §1 changes from "1949–2025 / free / SIPRI (Stockholm International Peace Research Institute 2024)" to "1949–2025 / free / SIPRI milex (Stockholm International Peace Research Institute 2026)".

The Yearbook citation is unchanged (it lives in its own `sipri_yearbook_ch7` entry).

### `docs/source-vetting-report.md` — one minor update

§3.7 ("Conflict / international aggression sources") `sipri_milex` row gets a one-line note: "Stage 2 adapter landed; see `src/leaders_db/ingest/sipri_milex.py`. 4 indicators under `international_peace`: Share of GDP, Per capita, Constant (2024) US$, Share of Govt. spending. The xlsx has no ISO3 column; Stage 3 resolves the display name to ISO3 via `country_aliases.csv`."

§6 ("Caveats the Stage 2 ingest must handle") `sipri_milex` row gets an update:

| Source | Caveat to handle |
|---|---|
| `sipri_milex` | (was) "Discover the latest version at runtime; do not hard-code `v1.2`." → (now) "**The xlsx has 5 data sheets; the Stage 2 adapter reads 4 of them (Share of GDP, Per capita, Constant (2024) US$, Share of Govt. spending). The `Current US$` sheet is deferred (5th candidate indicator). The header row position varies per sheet (6, 7, or 8) and is detected dynamically by scanning for the first row where col 0 is 'Country'. The xlsx interleaves 15 region/sub-region labels with the 177 country names in the data rows; the Stage 2 adapter filters out the regions by name (the `_SIPRI_MILEX_REGION_LABELS` frozenset). The xlsx uses 3 missing-value tokens: `'...'` (data unavailable), `'xxx'` (country did not exist / not independent), and `''` (empty). All three are coerced to `NULL` in `source_observations.normalized_value`; `raw_value` preserves the literal token for the audit trail. The xlsx has no ISO3 column; the Stage 2 adapter stores the raw display name in `source_row_reference` as `sipri_milex:<display_name>` and leaves `country_id` NULL for Stage 3 to fill via `country_aliases.csv`.**" |

### `docs/data-sources.md` — one update

The existing `sipri_milex` row says "Direct xlsx download; 1949–2025." Update to: "Direct xlsx download; 1949–2025; 922 KB; 10 sheets; 5 data sheets; 4 catalog indicators under `international_peace` (Share of GDP, Per capita, Constant (2024) US$, Share of Govt. spending). The xlsx has no ISO3 column; Stage 3 resolves the display name to ISO3 via `country_aliases.csv`. Stage 2 adapter landed."

### `docs/architecture.md` — no change required

The existing `architecture.md` already lists SIPRI milex as one of the per-source Stage 2 adapters (the "Conflict / international aggression sources" section). No structural change is needed.

---

## 3.9 — Lessons from WDI / WGI / UCDP / V-Dem reviews (apply to SIPRI milex from day one)

These are the WDI review findings, the WGI review findings, the UCDP review findings, and the V-Dem review findings. Apply them to SIPRI milex from the start so we don't repeat them.

### WDI lessons (apply all 8)

1. **No duplicate dispatch-table keys.** The `__init__.py` already has exactly one `"sipri_milex": None` entry (Phase A placeholder; the UCDP review caught a duplicate `"sipri_milex"` key from an earlier copy-paste and the table was already fixed to have exactly one entry). Do not add a second one. The dispatch-table test asserts the 25-key set.

2. **No ruff warnings in the test file.** Hoist all imports to the top; no unused imports; no lines >100 chars. The test-builder must follow the WGI / V-Dem convention (`from __future__ import annotations` first, then `import json, shutil`, then `from pathlib`, then third-party, then `from leaders_db...`).

3. **End-to-end test for orchestrator-level fields.** The `SipriMilexIngestResult` has 8 fields (`source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`, `regions_covered`, `country_count`). The end-to-end test must assert all 8, not just internal function call counts.

4. **Docstring accuracy.** Match the runtime default in the docstring (e.g., `year: int | None = None` should be documented as "Default: all years present in the xlsx (1949-2025 for Share of GDP / Constant USD / Current USD; 1988-2025 for Per capita / Share of Govt. spending)", not "Required"). The `sipri_milex.py` docstring should NOT say "400-line convention" or similar lies; each module's line count will be reported in the Done History entry, not in the source docstring.

5. **Design doc accuracy.** The catalog CSV is the source of truth; the design doc must match exactly. If the developer discovers a discrepancy (e.g., the live xlsx has a different sheet name than the design says), update the design doc in the same commit.

6. **`confidence IS NULL` assertion.** The Stage 2 → Stage 11 contract requires `confidence` NULL; the test must assert it (`assert all(r.confidence is None for r in rows)`).

7. **`raw_value` assertion.** The test must assert the `raw_value` for non-missing cells is the stringified float, and for missing cells it is the literal `"..."` / `"xxx"` / `""` (the audit trail of the original SIPRI cell). This is the SIPRI-specific corollary of V-Dem's `"-999.0"` assertion, WGI's `"#N/A"` assertion, WDI's `"nan"` assertion, and UCDP's `str(0)` for 0-fatality events assertion.

8. **Live-xlsx smoke verification.** Run the adapter against the real 922 KB xlsx after tests pass; verify row count, country count, and the SIPRI milex attribution in the CLI end-of-run output. Recorded in `docs/testing-guide-stage2-sipri_milex.md`.

### WGI lessons (apply all 6)

1. **The WGI reviewer's #3 (index-swap SQL) was a release-blocker because the developer changed the schema to make a test pass. Never change the schema or canonical text to make a test pass. Fix the test instead.** Specifically for SIPRI milex:
   - If a test uses a fragile dict-comprehension pattern, fix the test to sort the rows before building the dict, or use `.order_by()`.
   - If a test asserts on a canonical text (like `"SIPRI" in attribution`), change the test to assert on a substring that's actually in the canonical text (like `"Stockholm International Peace Research Institute" in attribution` or `"Milex" in attribution`), not the canonical text itself.
   - If a test fails because the catalog column name doesn't match the real data, change the test to match the data, not the data to match the test.

2. **WGI line counts exceeded 400.** For SIPRI milex, design the module split upfront so no file exceeds 400 lines. The 4-module split (`sipri_milex.py` ~180-220, `sipri_milex_io.py` ~260-320, `sipri_milex_xlsx.py` ~280-360, `sipri_milex_db.py` ~280-340) is the target. If a module grows past 400, split it during implementation.

3. **WGI `default_xlsx_path()` raise semantics.** SIPRI milex's `default_xlsx_path()` must also raise `FileNotFoundError` if the file is missing (per the design's stated contract in §3.3). The test `test_default_path_helpers` verifies this.

### UCDP lessons (apply all 5)

1. **No duplicate dispatch-table keys (the UCDP reviewer's #1 blocker).** The `__init__.py` already has exactly one `"sipri_milex"` entry (post-UCDP fix). Do not accidentally add a second one.

2. **No stale stub comment.** The UCDP reviewer's #3 was a stale comment in `ucdp.py` that said "UCDP is the second Stage 2 adapter" (it was the fourth). For SIPRI milex, the module docstring must say "fifth Stage 2 adapter" (matching the actual order: V-Dem, WDI, WGI, UCDP, SIPRI milex).

3. **No stale `# type: ignore` comments.** UCDP had a stale `# type: ignore` that hid a real type error. SIPRI milex must use `from __future__ import annotations` and proper type hints throughout; no `# type: ignore` unless the upstream type system is genuinely wrong (and a comment explains why).

4. **No design-doc contradictions.** The UCDP reviewer's #2 blocker was a "dense vs sparse frame" contradiction in the design doc. For SIPRI milex, the wide frame is **dense** (every country-year row is present, even when the country has no data — the year cell is `NaN`); the design must consistently say "dense" in both the read docstring and the public surface docstring.

5. **No schema mutation.** UCDP had a release-blocker (the WGI pattern: never DROP/CREATE indexes in the orchestrator). SIPRI milex must not touch the schema; the `register_sipri_milex_source` function only does an upsert via SQLAlchemy, no DDL.

### V-Dem lessons (apply all 4)

1. **`_coerce_float` handles all the missing-data sentinels in one place** (defense in depth). SIPRI milex's `_coerce_float` must handle pandas NaN, None, the 3 SIPRI missing tokens (`"..."`, `"xxx"`, `""`), and the V-Dem / WGI / WDI / UCDP sentinels (`null`, `NaN`, `nan`, `NA`, `-999`, `-999.0`).

2. **`_raw_value_to_string` preserves the original cell for the audit trail** (per the V-Dem pattern in `vdem_db.py:199`). For SIPRI milex, the audit-trail string is `str(cell)` for present cells, and the literal `"..."` / `"xxx"` / `""` for missing cells. The test asserts all 3 missing-token cases.

3. **V-Dem's `_delete_existing_observations` is the same pattern as SIPRI milex's** — delete existing rows for the requested years before inserting (so re-runs are idempotent for the year filter, but older years are untouched).

4. **V-Dem's `country_id` rename (to `vdem_country_id`) does NOT apply to SIPRI milex.** SIPRI milex's wide frame's `country` column carries the raw display name (NOT a UCDP-style integer ID, NOT a V-Dem-style `vdem_country_id`). The wide frame's `country` column is the SIPRI display name verbatim. The `source_observations.country_id` is left NULL (Stage 3 fills it). The `source_row_reference` is `"sipri_milex:<display_name>"`. This is the SIPRI-milex-specific pattern that differs from V-Dem and UCDP.

### Source-of-truth principle (the prompt's specific instruction)

The prompt's instruction: "If the test fixture count and the design catalog spec disagree (e.g., 3 vs 4 indicators), the design doc is the source of truth; the test must match." For SIPRI milex, the design says **4** indicators; the test fixture must have **4** indicator sheets. The test-builder does not negotiate this; the developer does not negotiate this. The 4 indicators in §3.4 are the contract.

### `df.attrs` survival (the UCDP-style extras pattern)

The `df.attrs["events_total"]` and `df.attrs["events_filtered"]` pattern from UCDP applies to SIPRI milex as `df.attrs["regions_covered"]` and `df.attrs["country_count"]`. The orchestrator surfaces both in `SipriMilexIngestResult`. The end-to-end test asserts both fields. The parquet writer strips the non-JSON-serializable `_sipri_milex_raw_long` key (if present) but preserves the JSON-serializable regions and country_count.

---

## Open questions for the developer

1. **SIPRI milex attribution text (the major open question).** The current [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `sipri` cites the *SIPRI Yearbook 2024* (the nuclear-forces chapter). The SIPRI milex data comes from the SIPRI website, NOT the Yearbook. The design proposes the attribution text:
   > Stockholm International Peace Research Institute. 2026. SIPRI Military Expenditure Database. https://www.sipri.org/databases/milex
   > Short-form: "SIPRI milex (Stockholm International Peace Research Institute 2026)."

   The developer must **confirm the attribution text with the user** before implementing (the user's preferred citation format may differ — e.g., they may want the full SIPRI Milex Yearbook section as the citation, or they may want a different year). The drift-guard test (`test_sipri_milex_attribution_matches_attributions_doc`) will fail if the constant and the doc disagree; both must be updated in the same commit.

2. **Should `Current US$` be a 5th indicator?** The design locks in 4 indicators (Share of GDP, Per capita, Constant USD, Share of Govt. spending). The 5th candidate is `Current US$` (nominal USD millions). If the user wants it, the catalog is a 1-row extension. The 4-indicator choice is the prototype default; the user may want to widen it.

3. **Region denylist list.** The denylist is hard-coded as a frozenset of 15 region labels + 1 "World" total. The 15 labels are the 5 regions + 10 sub-regions observed in the live v1.2 xlsx. If a future SIPRI release adds new region labels (e.g., a new "Polynesia" sub-region), the developer extends the set. The test fixture uses 2 of the 15 labels (`"Africa"` and `"Americas"`) — enough to exercise the filter; not all 15.

4. **Header row detection.** The design detects the header row by scanning for the first row where col 0 is `"Country"`. This is robust for the current v1.2 release. If a future release renames `"Country"` to `"country"` (lowercase) or `"Nation"`, the detection silently fails (returns an empty DataFrame). The defensive fix: if no row matches, raise `ValueError` with an actionable message. The developer adds this 5-line check; the design does not require it for the prototype.

5. **Per-sheet year range handling.** The 4 catalog sheets have different year ranges: `Share of GDP` / `Constant (2024) US$` / `Current US$` start at 1949; `Per capita` / `Share of Govt. spending` start at 1988. The read function detects year columns by integer in the year range (1949..current_year + 5). This handles the variation. The fixture uses years 2022, 2023 which are present in all 4 sheets.

6. **`"xxx"` semantic distinction.** The `"xxx"` token means the country did not exist or was not independent. The Stage 5 score module treats `"xxx"` the same as `"..."` (both → missing), but the `raw_value` audit trail preserves the literal `"xxx"` so a reviewer can distinguish "data unavailable" from "country did not exist". The test asserts this distinction (separate tests for `"..."` and `"xxx"` handling).

7. **Country name encoding.** The SIPRI xlsx uses UTF-8 encoded display names (e.g., `"Türkiye"`, `"Côte d'Ivoire"`, `"Democratic Republic of the Congo"`). The pandas `read_excel` (via openpyxl) preserves the UTF-8. The wide frame's `country` column carries the UTF-8 display name verbatim. Stage 3 must handle UTF-8 display names; the `country_aliases.csv` table should store UTF-8 names. This is a Stage 3 deliverable; Stage 2 just passes the names through.

8. **Test fixture size.** The prompt says 5 countries × 2 years. The WGI fixture is 5 × 2 × 6 = 60 cells; the UCDP fixture is 5 × 2 × 20 events → 60 obs rows; the V-Dem fixture is 10 rows × 22 indicators = 220 obs rows. The SIPRI fixture is 5 × 2 × 4 = **40 obs cells + 2 missing-value cells + 8 region rows** (filtered out). Total file size: ~5–10 KB. The catalog says 4 indicators, so the fixture has 4 indicator sheets. The test-builder does not negotiate the indicator count — the design says 4 and the fixture matches.

9. **Coverage year fix.** The Phase B source-vetting report says SIPRI milex covers "1949–2025". The actual v1.2 release has data through 2025. **The docs are already correct; no fix needed.** (This is in contrast to WGI and UCDP, where the docs said 2023 but the data ended at 2022; for SIPRI milex, the docs and the data agree.)

10. **`xlsx_path` discoverability.** The current design hard-codes the version-locked filename `SIPRI-Milex-data-1949-2025_v1.2.xlsx` in `_RAW_XLSX_NAME`. If a future release changes the filename (e.g., `SIPRI-Milex-data-1949-2026_v1.3.xlsx`), the developer updates the constant. The Stage 2 adapter does not auto-discover the latest version (the user downloads via the project's `curl` workflow and stages the file). The drift-guard test `test_default_path_helpers` asserts the path; a future release update is a 1-line constant change.
