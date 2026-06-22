# SIPRI Yearbook Ch.7 Architecture Design — Stage 2 Adapter for World Nuclear Forces

> **Status:** architecture design, ready for test-builder and developer.
> **Phase:** C.6 (data acquisition, sixth adapter, after V-Dem, WDI, WGI, UCDP, SIPRI milex).
> **Target source key:** `sipri_yearbook_ch7`.
> **Wiring in:** `src/leaders_db/ingest/__init__.py::STAGE2_ADAPTERS` (replace the existing `"sipri_yearbook_ch7": None` stub with `sipri_yearbook_ch7.ingest_sipri_yearbook_ch7`).
> **Source verdict:** ✅ `vetted_ok` per [`docs/source-vetting/report.md`](../source-vetting/report.md) §3.7.
> **Liveness verified:** 2026-06-18 — `https://www.sipri.org/sites/default/files/YB24%2007%20WNF.pdf` returns HTTP 200 (717,102 bytes, 717 KB, PDF version 1.6, 97 pages, Adobe InDesign 19.4 source, title metadata: *"SIPRI Yearbook 2024, World nuclear forces 2023"*, authors: *"Kristensen, H. M. and Korda, M./SIPRI"*). The data table (Table 7.1) is on PDF page 1 (the first content page after the chapter overview). It covers **9 nuclear-armed states** as of January 2024, with 5 data columns (Deployed, Stored, Stockpile total, Retired warheads, Total inventory).

This document is the design contract for the SIPRI Yearbook Ch.7 Stage 2 adapter. The test-builder writes tests against the public surface in §3.3; the developer implements against the same surface. The catalog spec in §3.4 is the only place where SIPRI Yearbook Ch.7's indicator list is decided.

> **First PDF source in the pipeline.** Every prior Stage 2 adapter reads xlsx / CSV / zip-CSV / API JSON. This is the first **PDF** source. The Stage 2 adapter therefore introduces a new module — `sipri_yearbook_ch7_pdf.py` — that wraps `pdfplumber` to extract the table and returns a list of dicts. The rest of the adapter is the same long→wide pivot pattern as WGI / UCDP / SIPRI milex. The PDF module is the only structurally new piece; everything else is reused.

---

## 3.1 — Source contract (what SIPRI Yearbook Ch.7 gives us, what we extract)

### Canonical URL and file format

| Field | Value |
|---|---|
| Canonical URL | `https://www.sipri.org/sites/default/files/YB24%2007%20WNF.pdf` (URL-encoded space: `%20`) |
| Format | PDF (PDF 1.6, 717 KB, 97 pages) |
| Auth | none (public, free, no API key) |
| Release cadence | annual; the current release is the SIPRI Yearbook 2024 (Ch.7 = "World Nuclear Forces"); data is the January 2024 snapshot |
| Local storage | `data/raw/sipri_yearbook_ch7/YB24 07 WNF.pdf`; `metadata.json` alongside |

> **Why PDF, not xlsx / API?** The SIPRI Yearbook is published as a PDF (Oxford University Press; the chapter is also distributed as a free PDF on sipri.org). The Milex database is xlsx, the Yearbook is PDF — different publication channels, different formats. The data is in **Table 7.1** on the first content page of the chapter. The Stage 2 adapter reads the PDF and extracts the table; it does not download. The download workflow uses `curl` to place the file at `data/raw/sipri_yearbook_ch7/`; the Stage 2 adapter does not download.
>
> **Version drift.** The filename `YB24 07 WNF.pdf` is version-locked to the Yearbook 2024 (data: January 2024). A future Yearbook 2025 release would be `YB25 07 WNF.pdf` (a different filename; the year `25` in `YB25` + the chapter number `07` + the `WNF` topic tag). The adapter's `_RAW_PDF_NAME` constant is the version-locked filename. The drift-guard test `test_default_path_helpers` (§3.5) catches filename drift at test time.

### PDF structure (verified live 2026-06-18)

The PDF is a **97-page chapter** with 14 tables (Table 7.1 through Table 7.14). The Stage 2 adapter reads only **Table 7.1** (the headline summary table). The other 13 tables (7.2–7.14) are per-country weapon-system breakdowns (7.2–7.10) and fissile-material stocks (7.11–7.14), which are not on the indicator catalog.

**Page 1 layout (the canonical Table 7.1):**

```
[Chapter title page] — "7. World nuclear forces / Overview" (text prose, no tables)
[Table 7.1 caption] — "Table 7.1. World nuclear forces, January 2024"
[Table 7.1 body] — the 9-country × 6-column data table
[Notes to Table 7.1] — footnotes a, b, c, d, e, f, g, h, i, j, k (multi-paragraph)
[Section I header] — "I. United States nuclear forces" (text prose; not part of the table)
```

**Table 7.1 structure (verified live 2026-06-18, page 1):**

| Column | Header (verbatim) | Type | Notes |
|---|---|---|---|
| 0 | `Country` | str | Display name, e.g. `"United States"`, `"Russia"`, `"North Korea"`, `"Israel"` |
| 1 | `Year of first nuclear test` | int or sentinel | `"1945"`–`"2006"` for the 9 states; `".."` for Israel (deliberate ambiguity) |
| 2 | `Military stockpile / Deployed` | int or sentinel | Footnote `b` reference; **the column header spans 2 visual rows** (`"Military stockpile"` over `"Deployed"`) |
| 3 | `Military stockpile / Stored` (footnote `c`) | int or sentinel | Central storage; **the column header spans 2 visual rows** |
| 4 | `Military stockpile / Total` | int | Sum of columns 2 and 3; a derived total — **we recompute it from columns 2 + 3 to avoid trusting the published value, then write the recomputed value to the wide frame** |
| 5 | `Retired warheads` (footnote `f`) | int or sentinel | Awaiting dismantlement; "–" (en-dash) means nil/negligible |
| 6 | `Total inventory` | int | Sum of columns 4 and 5; a derived total — **same recompute policy** |

**Data rows (verbatim from the live PDF, January 2024):**

| Country | Year of first test | Deployed | Stored | Stockpile total | Retired | Total inventory |
|---|---|---|---|---|---|---|
| United States | 1945 | 1 770 d | 1 938 e | 3 708 | 1 336 f | 5 044 |
| Russia | 1949 | 1 710 g | 2 670 h | 4 380 i | 1 200 f | 5 580 |
| United Kingdom | 1952 | 120 | 105 | 225 | – | 225 |
| France | 1960 | 280 | 10 | 290 | .. | 290 |
| China | 1964 | 24 j | 476 | 500 | – | 500 |
| India | 1974 | – | 172 | 172 | .. | 172 |
| Pakistan | 1998 | – | 170 | 170 | .. | 170 |
| North Korea | 2006 | – | 50 | 50 | .. | 50 k |
| Israel | .. | – | 90 | 90 | .. | 90 |
| **Total** |  | **3 904** | **5 681** | **9 585** | **2 536** | **12 121** |

The last row (`Total`) is an aggregate label; the Stage 2 adapter **filters it out** (the `_SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS` frozenset contains `"Total"` and `"World"`; the same denylist pattern as SIPRI milex's region filter).

**Missing-value tokens (3 sentinels, all in the live PDF):**

| Token | Unicode codepoint | Meaning | Stage 2 handling |
|---|---|---|---|
| `–` (en-dash) | U+2013 | Nil or a negligible value (per Table 7.1 legend) | → `0` in `normalized_value`; `raw_value` preserves the literal `"–"` (the U+2013 character) |
| `..` (two ASCII dots) | U+002E × 2 | Not applicable or not available (per Table 7.1 legend) | → `None` in `normalized_value`; `raw_value` preserves the literal `".."` |
| `c. <num>` (e.g. `"c. 24"`, `"c. 1370"`) | — | A footnote "approximately" annotation (e.g., China's deployed 24 warheads has a footnote `j`: "SIPRI assesses that, as of Jan. 2024, China might have started to deploy a small number of its warheads (c. 24) on their launchers.") | The PDF cell carries the annotated string `"c. 24"` (with the leading `c. ` and footnote letter `j`); the Stage 2 read function **strips the footnote letters** (`d`, `e`, `f`, `g`, `h`, `i`, `j`, `k`) from the cell, parses the integer, and writes the parsed integer to `normalized_value`; the `raw_value` preserves the original `"c. 24 j"` string (or the original `"c. 24"` if there is no footnote letter) |
| `"–"` for Israel's "Year of first nuclear test" cell | U+2013 | The PDF shows `..` for Israel's first-test year (not `–`); see notes above | The `Year of first nuclear test` column is **NOT** in the catalog (we don't extract it as an indicator). The catalog says "year=2024" and ignores the first-test year entirely. The "Year of first nuclear test" column is read past — see §3.2. |

> **The `"c. <num>"` annotation pattern is the SIPRI-Yearbook-specific data quirk.** The Milex xlsx has no such annotations; its cells are pure numerics. The PDF cells can carry a footnote letter suffix (`"1 770 d"`, `"24 j"`, `"50 k"`) which is part of the value (it refers the reader to the notes). The Stage 2 read function strips the footnote-letter suffix and the leading `"c. "` (if present) before parsing the integer. The audit-trail `raw_value` preserves the original cell verbatim. This is the PDF-specific equivalent of the SIPRI-milex `"..."` / `"xxx"` / `""` coercion.

**Country name format (display names, no ISO3):**

The PDF table uses **display names** (e.g. `"United States"`, `"Russia"`, `"United Kingdom"`, `"France"`, `"China"`, `"India"`, `"Pakistan"`, `"North Korea"`, `"Israel"`). No ISO3 column. The Stage 2 adapter stores the raw display name in `source_row_reference` as `"sipri_yearbook_ch7:United States"` and leaves `country_id` NULL in `source_observations`. Stage 3 (country match) resolves the display name to ISO3 via the `country_aliases.csv` table (a future Stage 3 deliverable). This is the same pattern as SIPRI milex's display-name passthrough.

**Why a single snapshot year (no time series)?**

The Yearbook Ch.7 data is a **point-in-time snapshot** (January 2024). It is NOT a time series; the table is the headline estimate for the Yearbook year. There is no per-year row in the table; the table has 9 country rows and 1 time stamp (the chapter year, embedded in the table caption: *"Table 7.1. World nuclear forces, January 2024"*). The Stage 2 wide frame is **9 rows × 1 year (2024) × 3 indicators**. If the user passes `year=2023`, the adapter returns an empty frame (no data for 2023 in the Yearbook 2024 PDF). This is the same point-in-time shape as the client validation matrix, but the client matrix is not a source of evidence.

> **No backward-compatibility concern for older years.** The Milex xlsx covers 1949–2025 (a 77-year time series). The Yearbook Ch.7 is a 1-year snapshot. The Stage 2 wide frame's `year` column carries the Yearbook year (2024 for the YB24 PDF). The score module in Stage 9–10 will use the 2024 number as the input for the 2024 (or 2023, by backward lookup) score. The wider implications of "the Yearbook is always one year ahead" are handled by Stage 5 (the score module applies a 1-year decay penalty if the score year != the source year), not by Stage 2. Stage 2 just writes the 2024 number for the 9 states.

### What we extract vs what we defer

**Extract (3 indicators across 1 category, from the 5-column Table 7.1):**

For each of the 9 nuclear-armed states, 3 indicator values (the catalog in §3.4 specifies which 3 of the 5 columns):

1. `sipri_yearbook_ch7_nuclear_warheads_total_inventory` — `Total inventory` column (col 6). The headline count of all warheads (deployed + reserve + retired awaiting dismantlement).
2. `sipri_yearbook_ch7_nuclear_warheads_deployed` — `Deployed` column (col 2). The count of warheads in operational deployment (on missiles or at operational bases).
3. `sipri_yearbook_ch7_nuclear_warheads_retired` — `Retired warheads` column (col 5). The count of warheads awaiting dismantlement (the disarmament pipeline).

**Defer to a future iteration (kept in the PDF but not written to `source_observations`):**

- The `Stored` column (col 3) — central storage; redundant with `Deployed` and `Stockpile total` for the scoring rubric. The Stage 5 score module can recompute it as `Stockpile total - Deployed` if needed.
- The `Stockpile total` column (col 4) — derived from `Deployed + Stored`; redundant for the scoring rubric. The Stage 5 score module can recompute it as `Deployed + Stored` if needed.
- The `Year of first nuclear test` column (col 1) — not an indicator; just a metadata field. Defer.
- Tables 7.2–7.10 (per-country weapon-system breakdowns) — useful for LLM rationale input and per-delivery-system analysis, but not on the indicator catalog. Defer.
- Tables 7.11–7.14 (fissile-material stocks) — useful for the "production capacity" signal, but not on the indicator catalog. Defer.

This narrowing is a **user decision** (see "Open questions" in §3.6). The 3-indicator choice is the prototype default; the user may want to widen it.

> **Why exactly 3, not 4?** The full Table 7.1 has 5 numeric columns. The prompt's instruction is to pick "2-3 of the 4" (deployed / stockpile / retired / total) to keep the catalog narrow. The recommended 3 are: **total inventory** (the headline), **deployed** (the operational signal), **retired** (the disarmament signal). The "stockpile" sub-totals (Stored and Stockpile total) are derived from the other 3 (Stored = Stockpile total - Deployed; Stockpile total = Deployed + Stored) and add no information. 3 indicators is the right balance for the prototype.

### Indicator catalog scope (this design)

For the prototype, all **3** catalog indicators are extracted, feeding the **1 rating category** SIPRI Yearbook Ch.7 serves per the source-vetting report:

1. **`nuclear`** — 3 indicators: `sipri_yearbook_ch7_nuclear_warheads_total_inventory`, `sipri_yearbook_ch7_nuclear_warheads_deployed`, `sipri_yearbook_ch7_nuclear_warheads_retired`. All three feed the `nuclear` category (which is **only** served by this source; the other nuclear-related source, FAS, is the cross-validation source per requirement §6/§9).

> **Why `nuclear` only, no other category?** Per [`docs/source-vetting/report.md`](../source-vetting/report.md) §3.7, SIPRI Yearbook Ch.7 is the **only** source for the `nuclear` category. The 3 indicators all measure aspects of nuclear arsenals (total count, operational count, retirement pipeline) — all proxies for the same underlying signal ("how big is this state's nuclear arsenal?"). The FAS Nuclear Notebook (the other nuclear-related source) is used for cross-validation in the manual-review queue, not as a Stage 2 indicator source.

The full per-indicator spec (raw column → canonical `variable_name`, scale, unit, category, one-line description) is in §3.4. The catalog CSV the developer will author lives at `src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv` (sibling to the adapter modules, per Phase C convention #1).

### Integration with downstream schema

None of the SIPRI Yearbook Ch.7 indicators populate the `country_years` table directly (those columns are reserved for WDI's `population`, `gdp_current_usd`, `gdp_per_capita` — see [`docs/architecture/wdi.md`](wdi.md) §2.1). All 3 indicators live in `source_observations` and are consumed by the Stage 5 score module for `nuclear`.

### License

The SIPRI Yearbook Ch.7 is distributed under a **free academic license with attribution**. The canonical long-form attribution text is the citation block in [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `sipri_yearbook_ch7` (and is the `SIPRI_YEARBOOK_CH7_ATTRIBUTION` constant — see §3.3). The drift-guard test `test_sipri_yearbook_ch7_attribution_matches_attributions_doc` (§3.5) enforces byte-for-byte consistency.

### Cited artifacts

- Indicator catalog: `src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv` (to be authored from §3.4).
- Per-source `metadata.json`: `data/raw/sipri_yearbook_ch7/metadata.json` (to be written when the first successful read happens).
- Attribution: `docs/source-attributions.md` §1 entry for `sipri_yearbook_ch7` (already present in the doc; the constant is byte-identical to the citation in §1).
- PDF parser module: `src/leaders_db/ingest/sipri_yearbook_ch7_pdf.py` (new — the first PDF parser in the pipeline).

---

## 3.2 — Module structure (V-Dem / WGI-style with a new PDF parser module)

SIPRI Yearbook Ch.7 is structurally closer to WGI / SIPRI milex (one local file, no network, no HTTP layer) than to WDI (per-indicator HTTP, JSON cache) or UCDP (event-level aggregation). The WGI 5-module split + SIPRI milex 5-module split are the template. The new piece is the PDF parser: a thin wrapper around `pdfplumber` that takes a PDF path and returns the canonical list-of-dicts (one dict per country row).

The SIPRI Yearbook Ch.7 module splits into **5 sibling files** under `src/leaders_db/ingest/`, each under the 400-line convention from `docs/coding-guidelines.md`:

| File | Responsibility | Approx LoC target |
|---|---|---|
| `sipri_yearbook_ch7.py` | Public orchestrator: `SipriYearbookCh7IngestResult` Pydantic model, `attribution()`, `ingest_sipri_yearbook_ch7()` entrypoint. Re-exports `SIPRI_YEARBOOK_CH7_ATTRIBUTION`, `SIPRI_YEARBOOK_CH7_SOURCE_KEY`, `IndicatorSpec` from the I/O module. | ~200–260 |
| `sipri_yearbook_ch7_io.py` | Catalog, path helpers, parquet write, parquet metadata attachment. Owns `SIPRI_YEARBOOK_CH7_ATTRIBUTION`, `SIPRI_YEARBOOK_CH7_SOURCE_KEY`, `IndicatorSpec`, the catalog loader, and the `_DEFAULT_CATALOG_PATH` constant. The non-country denylist (`_SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS`) also lives here as a private constant. | ~260–320 |
| `sipri_yearbook_ch7_pdf.py` | **New: PDF table extraction.** The thin wrapper around `pdfplumber` that opens the PDF, finds Table 7.1 on page 1, and returns a list of dicts (one per country row). The read function in `sipri_yearbook_ch7_io` calls into this module to get the table. Owns `read_table_7_1()`. | ~140–200 |
| `sipri_yearbook_ch7_db.py` | `sources` upsert, `source_observations` write, run manifest, missing-value coercion helpers (`_coerce_int`, `_raw_value_to_string`). The missing-value coercion is source-specific (3 tokens: `–`, `..`, `c. <num>` with footnote letters) and is not large enough to warrant a separate `sipri_yearbook_ch7_db_helpers.py` — it lives in `sipri_yearbook_ch7_db.py`. | ~280–340 |
| `sipri_yearbook_ch7_db_helpers.py` | Pure helpers: bundle metadata read, year-only parse, value coercion (counts → int), `raw_value_to_string` for the audit trail, footnote-letter stripping (the `"c. 24 j"` → `24` regex). | ~100–150 |

> **Why 5 modules, not 4 (or 6)?** The PDF parser is its own module because it has a distinct concern: it wraps a third-party library (`pdfplumber`) and has its own error modes (the PDF could be missing, the table could be on a different page in a future edition, the column boundaries could change). Separating `sipri_yearbook_ch7_pdf.py` from the orchestrator and the DB layer keeps the PDF concern isolated. The `sipri_yearbook_ch7_db_helpers.py` is small (~100–150 lines) but contains 4 distinct helpers (metadata, year parse, value coercion, footnote strip) — they share the "pure-function" pattern of `vdem_db_helpers.py` and `ucdp_db_helpers.py` and warrant their own file.

> **Why no `sipri_yearbook_ch7_xlsx.py`?** The source is a PDF, not an xlsx. The `sipri_yearbook_ch7_pdf.py` is the new "xlsx" equivalent (the file-format-specific reader).

> **Why no `sipri_yearbook_ch7_http.py`?** SIPRI Yearbook Ch.7 has no HTTP layer. The PDF is staged locally; the read orchestrator opens the PDF and walks the catalog columns. Same as WGI / SIPRI milex's pattern (no `_http.py`).

> **Why is `pdfplumber` not in `pyproject.toml`?** It is a new project dependency introduced by this adapter. The developer adds `pdfplumber>=0.11` to the `[project] dependencies` list in `pyproject.toml` in the same commit as the adapter lands. (This is a project-level change, not a per-source change; the dependency lives in the top-level deps so all future PDF sources can reuse it.)

The split rationale is identical to WGI / SIPRI milex: `sipri_yearbook_ch7_io` owns the constants and the catalog; `sipri_yearbook_ch7_pdf` owns the PDF I/O; `sipri_yearbook_ch7_db` owns the DB contract; `sipri_yearbook_ch7_db_helpers` owns the pure coercion helpers; `sipri_yearbook_ch7` is the orchestrator that wires them together. Constants live in `sipri_yearbook_ch7_io` (lowest level) to break the import cycle, and are re-exported by `sipri_yearbook_ch7.py` for the public surface.

### Read pattern — chosen approach: **PDF → list of dicts (Table 7.1) → long → wide pivot**

The PDF is not natively a table. The read function performs the table extraction + long→wide reshape:

1. **Open the PDF** with `pdfplumber.open(pdf_path)`. The PDF is 717 KB and 97 pages; the per-page iteration is fast (< 1 s on a typical laptop). The `pdfplumber` library handles the deflate-decoded PDF natively.
2. **Find Table 7.1.** The Stage 2 PDF parser scans the first 3 pages for the string `"Table 7.1."`. The caption appears on the same page as the table body (page 1, the first content page after the chapter overview). The parser extracts the table from that page using `pdfplumber.Page.extract_table()` with the `table_settings` argument:
   ```python
   table_settings = {
       "vertical_strategy": "lines",
       "horizontal_strategy": "lines",
       "snap_tolerance": 4,
   }
   ```
   The `lines` strategy uses the PDF's vector lines to find cell boundaries, which is the most robust approach for SIPRI's Adobe InDesign-rendered tables. The Stage 2 parser falls back to `text` strategy if `lines` returns 0 tables on the page.
3. **Parse the table** into a list of dicts. The parser:
   - Detects the header row (the row whose first cell is the literal string `"Country"`).
   - Builds the column-to-name map from the header row (mapping col 0 → `"Country"`, col 1 → `"year_first_test"`, col 2 → `"deployed"`, col 3 → `"stored"`, col 4 → `"stockpile_total"`, col 5 → `"retired"`, col 6 → `"total_inventory"`).
   - For each data row (rows below the header + 1 blank row):
     - Extract `Country` (col 0), the 5 numeric cells (cols 2–6). The `year_first_test` column (col 1) is read past — not extracted.
     - **Non-country filter**: skip the row if the country name is in `_SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS`. The denylist contains the 2 observed aggregate labels (`"Total"`, `"World"`).
     - **Missing-value coercion**: `–` → 0, `..` → None, `c. <num> [letter]` → int (the parsed integer, with the footnote letter stripped). The original cell (e.g., `"c. 24 j"`) is preserved in `raw_value` for the audit trail.
     - Append `{country_name, deployed, stored, stockpile_total, retired, total_inventory}` rows to a long-format list.
4. **Recompute the derived totals** (defense in depth):
   - `stockpile_total` is recomputed as `deployed + stored` and compared to the published value; if they differ by more than 1 (a single rounding error), the Stage 2 parser logs a warning. (Live probe of the 2024 PDF shows the published totals match the sum exactly for all 9 countries; the recompute is a sanity check, not a correction.)
   - `total_inventory` is recomputed as `stockpile_total + retired` and compared to the published value; same policy.
5. **Convert to a long-format DataFrame** with columns `(country, year, indicator_code, value)`. The `year` column is the snapshot year (2024 for the YB24 PDF). The `indicator_code` is one of `total_inventory`, `deployed`, `retired` (the 3 catalog indicators; the other 2 columns `stored` and `stockpile_total` are dropped from the long frame).
6. **Pivot to wide format** (one row per `(country, year)`, one column per `variable_name`). The wide frame has 9 country-year rows × 3 indicator columns. The same shape as the WGI / SIPRI milex wide frame.
7. **Attach `df.attrs` audit fields**:
   - `df.attrs["pdf_pages_total"]` — the count of pages in the PDF (97 for YB24).
   - `df.attrs["snapshot_year"]` — the Yearbook year parsed from the table caption (2024 for YB24). The Stage 2 PDF parser extracts this string from the caption and parses it as an int.

The Stage 2 → Stage 11 contract: `confidence` is left `NULL` on every row; Stage 11 fills it. `country_id` is left `NULL`; Stage 3 (country match) fills it from the SIPRI display name via the `country_aliases.csv` table (a future Stage 3 deliverable). The wide frame's country column carries the raw display name; the `source_row_reference` carries `"sipri_yearbook_ch7:<display_name>"` (e.g., `"sipri_yearbook_ch7:United States"`).

The orchestrator surfaces `pdf_pages_total` and `snapshot_year` in `SipriYearbookCh7IngestResult` (these are the SIPRI-Yearbook-Ch.7-specific equivalents of UCDP's `events_total` / `events_filtered` and SIPRI milex's `regions_covered` / `country_count`).

---

## 3.3 — Public surface (exact function signatures)

The test-builder writes against these signatures; the developer implements against these signatures. The names and types are the contract; the docstrings below describe the contract for both audiences.

### Constants (in `sipri_yearbook_ch7_io.py`, re-exported by `sipri_yearbook_ch7.py`)

```python
SIPRI_YEARBOOK_CH7_SOURCE_KEY: str = "sipri_yearbook_ch7"
```

The single source key used everywhere in the data lake, the CLI dispatch, and the test imports. Matches the `data/raw/<key>/` folder name and the `--source` CLI flag.

```python
SIPRI_YEARBOOK_CH7_ATTRIBUTION: str = (
    'Stockholm International Peace Research Institute. 2024. '
    '"World Nuclear Forces." In '
    'SIPRI Yearbook 2024: Armaments, Disarmament and International Security. '
    'Oxford University Press.'
)
```

The exact citation text. Lives in `sipri_yearbook_ch7_io` to break the import cycle. The canonical long-form lives in `docs/source-attributions.md` §1 entry for `sipri_yearbook_ch7`; the drift-guard test (§3.5) enforces byte-for-byte consistency. **The text above is byte-identical to the citation in the doc; the developer copies it verbatim into the constant.** The single quote / double quote convention: the doc uses double quotes around `"World Nuclear Forces."`; the Python string uses a single-quote outer wrapper and double-quote inner literal to match the doc's text exactly. (The doc's full citation text: `Stockholm International Peace Research Institute. 2024. "World Nuclear Forces." In SIPRI Yearbook 2024: Armaments, Disarmament and International Security. Oxford University Press.`)

```python
#: Default location of the indicator catalog. Lives here so
#: :func:`write_sipri_yearbook_ch7_run_manifest` in ``sipri_yearbook_ch7_db``
#: can import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = Path(__file__).resolve().parent / "catalogs" / "sipri_yearbook_ch7.csv"

#: Raw PDF file name inside ``data/raw/sipri_yearbook_ch7/``.
_RAW_PDF_NAME: str = "YB24 07 WNF.pdf"

#: Narrow parquet that Stage 2 writes under ``data/processed/sipri_yearbook_ch7/``.
_PROCESSED_PARQUET_NAME: str = "sipri_yearbook_ch7_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "sipri_yearbook_ch7_attribution"
_PARQUET_META_SOURCE_KEY: str = "sipri_yearbook_ch7_source_key"

#: Non-country / aggregate labels in the SIPRI Yearbook Ch.7 Table 7.1 that
#: are NOT countries. The read function filters these out so only the 9
#: nuclear-armed state rows end up in the wide frame. The set is the
#: WGI / SIPRI milex "no aggregates" approach adapted to Table 7.1 (which
#: has 1 aggregate row: "Total"). "World" is added for defense in depth
#: (no observed instance in YB24; added in case a future Yearbook edition
#: adds a "World" row).
_SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS: frozenset[str] = frozenset({
    "Total",
    "World",
})
```

### Indicator catalog (in `sipri_yearbook_ch7_io.py`)

```python
@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the SIPRI Yearbook Ch.7 indicator catalog.

    The V-Dem / WDI / WGI / UCDP / SIPRI milex ``IndicatorSpec`` shape is
    reused verbatim: every Stage 2 adapter resolves its raw column from
    this dataclass so the score modules in Stage 9-10 can normalize and
    direct indicators consistently across sources.
    """
    variable_name: str
    raw_column: str         # the PDF table column key, e.g. "total_inventory"
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
    """Load the SIPRI Yearbook Ch.7 indicator catalog from ``catalogs/sipri_yearbook_ch7.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex loaders: handles
    the leading ``#`` comment block, drops comment-only lines, validates
    the required column set, and returns one ``IndicatorSpec`` per data
    row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
```

### PDF read (in `sipri_yearbook_ch7_pdf.py`)

```python
def read_table_7_1(pdf_path: Path) -> list[dict[str, object]]:
    """Read Table 7.1 from the SIPRI Yearbook Ch.7 PDF.

    Returns a list of dicts, one per country row in Table 7.1 (9 dicts
    for the YB24 PDF, plus 1 aggregate row that the caller filters out
    via ``_SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS``). Each dict has the
    following keys:

    - ``country`` (str): the display name, e.g. ``"United States"``.
    - ``year_first_test`` (int | str): the year of first nuclear test
      (e.g., 1945 for the USA) or the literal ``".."`` for Israel
      (deliberate ambiguity). NOT extracted as an indicator; carried in
      the dict for the audit trail only.
    - ``deployed`` (int): warheads in operational deployment.
    - ``stored`` (int): warheads in central storage.
    - ``stockpile_total`` (int): deployed + stored (the published value;
      the reader also recomputes it from deployed + stored as a sanity
      check).
    - ``retired`` (int | None): warheads awaiting dismantlement. ``0``
      if the cell is the en-dash sentinel ``"–"``; ``None`` if the cell
      is the two-dot sentinel ``".."``.
    - ``total_inventory`` (int): stockpile_total + retired.
    - ``raw_value_<col>`` (str): the original PDF cell for each numeric
      column, preserving the footnote-letter suffix (e.g., ``"1 770 d"``)
      and the en-dash / two-dot sentinels verbatim. The reader writes
      5 raw_value keys: ``raw_value_deployed``, ``raw_value_stored``,
      ``raw_value_stockpile_total``, ``raw_value_retired``,
      ``raw_value_total_inventory``.

    Steps:

    1. Open the PDF with ``pdfplumber.open(pdf_path)``.
    2. Scan the first 3 pages for the string ``"Table 7.1."``. Record
       the page index.
    3. Extract the table from that page using
       ``page.extract_table(table_settings=...)`` with the ``lines``
       strategy (the most robust for Adobe InDesign-rendered tables).
       Fall back to the ``text`` strategy if ``lines`` returns 0 tables.
    4. Detect the header row (the row whose first cell is the literal
       string ``"Country"``).
    5. Build the column-to-key map from the header row.
    6. For each data row (rows below the header + 1 blank row):
       - Extract the 5 numeric cells and the country name.
       - Coerce each cell: en-dash ``"–"`` → ``0``, two-dot ``".."`` →
         ``None``, ``"c. <num> <letter>"`` → ``int(num)`` (strip the
         ``"c. "`` prefix and the footnote letter).
       - Preserve the original cell in ``raw_value_<col>``.
    7. Sanity-check the derived totals: ``stockpile_total`` ==
       ``deployed + stored`` and ``total_inventory`` ==
       ``stockpile_total + retired`` (within ±1 for rounding). Log a
       warning if they differ; do not correct the published value.

    Args:
        pdf_path: path to the SIPRI Yearbook Ch.7 PDF.

    Returns:
        A list of dicts (one per country row in Table 7.1; the caller
        filters out the aggregate row).

    Raises:
        FileNotFoundError: if the PDF is missing.
        ValueError: if Table 7.1 cannot be found in the first 3 pages.
        RuntimeError: if the table extraction returns 0 tables on the
            Table 7.1 page (i.e., the PDF layout has changed and the
            parser cannot recover).
    """
```

### Read (in `sipri_yearbook_ch7_io.py`)

```python
def read_sipri_yearbook_ch7(
    *,
    year: int | None = None,
    pdf_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read SIPRI Yearbook Ch.7 from the PDF and pivot to wide format (one row per country per year).

    Steps:

    1. Load the catalog.
    2. Open the PDF at ``pdf_path`` (default:
       ``data/raw/sipri_yearbook_ch7/YB24 07 WNF.pdf``) via
       :func:`sipri_yearbook_ch7_pdf.read_table_7_1`.
    3. Filter out the aggregate rows (the ``Total`` row and any
       ``World`` row that may appear in a future edition).
    4. For each catalog indicator (i.e., for each catalog row's
       ``raw_column`` key — one of ``"deployed"``, ``"retired"``,
       ``"total_inventory"``):
       a. Look up the corresponding ``raw_value_<col>`` in the
          per-country dict.
       b. Append ``(country, year, indicator_code, value)`` rows to a
          long frame. The ``year`` is the snapshot year parsed from
          the table caption (2024 for YB24); the value is the parsed
          integer (or ``None`` for the ``".."`` sentinel).
    5. Concatenate per-indicator long frames.
    6. Pivot to wide format: one row per ``(country, year)``, one
       column per catalog ``variable_name``. Coerce the ``year``
       column to ``int`` and the indicator columns to ``Int64``
       (nullable integer; missing cells are ``pd.NA`` for the
       ``".."`` sentinel).
    7. Filter by year if ``year=`` is passed (default: 2024 for
       YB24; the function returns the snapshot year only).
    8. Attach ``df.attrs["pdf_pages_total"]`` (the count of pages
       in the PDF) and ``df.attrs["snapshot_year"]`` (the Yearbook
       year parsed from the table caption).

    Args:
        year: filter to a single year (e.g., ``2023``). Default:
            the snapshot year of the PDF (2024 for YB24). The
            function returns the snapshot year only; if a different
            year is passed, the function returns an empty DataFrame
            (no data for that year in the Yearbook Ch.7 snapshot).
        pdf_path: override the input PDF. Default: data-lake path.
        catalog_path: override the indicator catalog. Default:
            checked-in.

    Returns:
        A pandas DataFrame with columns ``country`` (display name
        string), ``year`` (int, the snapshot year), then one
        column per catalog indicator (named with the
        ``variable_name``). Indicator columns are ``Int64``
        (nullable; ``pd.NA`` = missing for the ``".."`` sentinel).
        The wide frame has 9 country rows for the snapshot year
        (the aggregate row is filtered out). SIPRI Yearbook Ch.7
        does NOT return an ISO3 code; the country column carries
        the raw display name. Stage 3 (country match) resolves it
        to ISO3 via the ``country_aliases.csv`` table.

    Raises:
        FileNotFoundError: if the PDF is missing.
        ValueError: if Table 7.1 cannot be found in the first 3 pages.
    """
```

### Path helpers (in `sipri_yearbook_ch7_io.py`)

```python
def default_pdf_path() -> Path:
    """Return the conventional SIPRI Yearbook Ch.7 PDF path inside the data lake.

    Resolves to
    ``<project_root>/data/raw/sipri_yearbook_ch7/YB24 07 WNF.pdf``.
    Raises ``FileNotFoundError`` if the file is missing (per the
    design contract in §3.3); the adapter expects the user to have
    downloaded the PDF via the project's download workflow first.
    """


def default_processed_parquet_path() -> Path:
    """Return the conventional SIPRI Yearbook Ch.7 narrow parquet path.

    Creates the ``data/processed/sipri_yearbook_ch7/`` directory if missing.
    """
```

### Parquet write (in `sipri_yearbook_ch7_io.py`)

```python
def write_sipri_yearbook_ch7_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet`,
    :func:`wgi_io.write_wgi_parquet`, and
    :func:`sipri_milex_io.write_sipri_milex_parquet` (and the
    :func:`_attach_parquet_metadata` helper): writes the parquet via
    ``df.to_parquet``, then re-writes the file with the SIPRI Yearbook
    Ch.7 attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite — if pyarrow fails,
    the data parquet is still valid and a warning is logged.
    """
```

### DB writes (in `sipri_yearbook_ch7_db.py`)

```python
def register_sipri_yearbook_ch7_source(session: Session) -> int:
    """Upsert the SIPRI Yearbook Ch.7 source row into the ``sources`` table.

    Keyed by ``(source_name='SIPRI Yearbook Chapter 7 (World Nuclear Forces)',
    version='YB2024 (data: January 2024)')``. Idempotent: returns the
    same ``sources.id`` on every call. Reads the bundle's ``metadata.json``
    for ``source_url``, ``download_date``, ``license_note``,
    ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source`, WGI's
    :func:`wgi_db.register_wgi_source`, UCDP's
    :func:`ucdp_db.register_ucdp_source`, and SIPRI milex's
    :func:`sipri_milex_db.register_sipri_milex_source`).
    """


def write_sipri_yearbook_ch7_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    Same shape as V-Dem's :func:`vdem_db.write_vdem_observations`,
    WGI's :func:`wgi_db.write_wgi_observations`, UCDP's
    :func:`ucdp_db.write_ucdp_observations`, and SIPRI milex's
    :func:`sipri_milex_db.write_sipri_milex_observations`:

    - ``country_id`` is left ``NULL``; Stage 3 (country match) fills it
      from the SIPRI display name via ``country_aliases.csv`` (a future
      Stage 3 deliverable).
    - ``source_row_reference`` carries the SIPRI display name prefixed
      with ``"sipri_yearbook_ch7:"`` (e.g.,
      ``"sipri_yearbook_ch7:United States"``) so Stage 3 can resolve it.
    - ``raw_value`` preserves the original PDF cell: the integer as a
      string for numeric cells (e.g., ``"5044"`` for the USA's total
      inventory), or the literal ``"–"`` (U+2013, the en-dash sentinel)
      for nil values, or the literal ``".."`` (two-dot sentinel) for
      not-applicable values, or the original annotated string (e.g.,
      ``"c. 24 j"`` for China's deployed warheads) for cells with
      footnote letters. The en-dash / two-dot / c.-prefix patterns are
      preserved verbatim for the audit trail.
    - ``normalized_value`` is the int, or ``None`` if the cell is
      ``".."`` (the two-dot sentinel; per the legend: "not applicable
      or not available"). For the en-dash sentinel ``"–"`` (nil or
      negligible), the normalized_value is ``0`` (zero), not ``None``,
      per the SIPRI legend's "nil or negligible" semantic.
    - Idempotent: deletes existing rows for the requested years (from
      the frame) before inserting. Years outside the frame are
      untouched.

    Returns the number of ``source_observations`` rows inserted.
    """


def write_sipri_yearbook_ch7_run_manifest(
    result,  # SipriYearbookCh7IngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest is the audit trail for ``processed/``: it records
    ``source_id``, the parquet path, the observation row count, the
    countries count, the years, the indicator count, the
    ``pdf_pages_total``, the ``snapshot_year``, the catalog path, and
    the attribution. Written every run (not best-effort) so Stage 15
    reports can find the attribution without re-reading the parquet
    metadata.
    """
```

### Orchestrator and Pydantic result (in `sipri_yearbook_ch7.py`)

```python
class SipriYearbookCh7IngestResult(BaseModel):
    """Summary of a single ``ingest_sipri_yearbook_ch7`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads these
    fields to print the end-of-run summary, and the manifest writer in
    :mod:`sipri_yearbook_ch7_db` consumes the same fields. Same shape
    as V-Dem's :class:`vdem.IngestResult`, WGI's
    :class:`wgi.WGIIngestResult`, UCDP's :class:`ucdp.UCDPIngestResult`,
    and SIPRI milex's :class:`sipri_milex.SipriMilexIngestResult` for
    consistency.

    SIPRI-Yearbook-Ch.7-specific extras vs the WGI :class:`WGIIngestResult`:

    - ``pdf_pages_total``: the count of pages in the PDF (97 for YB24).
      Carried forward from ``df.attrs["pdf_pages_total"]``. Useful for
      the audit trail to confirm the PDF is the expected edition
      (a future YB25 PDF would have a different page count).
    - ``snapshot_year``: the Yearbook year parsed from the table caption
      (2024 for YB24). Carried forward from
      ``df.attrs["snapshot_year"]``. Useful for confirming the wide
      frame's ``year`` column matches the Yearbook year.

    These are the SIPRI-Yearbook-Ch.7-specific equivalents of UCDP's
    ``events_total`` / ``events_filtered`` and SIPRI milex's
    ``regions_covered`` / ``country_count``: they capture
    "what was filtered out" for end-to-end audit.
    """
    source_id: int = Field(..., ge=1)
    parquet_path: Path
    observation_rows: int = Field(..., ge=0)
    countries: int = Field(..., ge=0, description="Distinct country names in the wide frame.")
    years: tuple[int, ...]
    indicators: int = Field(..., ge=0)
    pdf_pages_total: int = Field(..., ge=1, description="Count of pages in the SIPRI Yearbook Ch.7 PDF.")
    snapshot_year: int = Field(..., ge=1900, description="Yearbook year parsed from the Table 7.1 caption.")

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]: ...

    @property
    def attribution(self) -> str:
        """The SIPRI Yearbook Ch.7 attribution text (Always-On Rule #15)."""
        return SIPRI_YEARBOOK_CH7_ATTRIBUTION
```

> **Note on the IngestResult field count.** V-Dem has 6 fields (no HTTP, no aggregation). WGI has 6 fields. UCDP has 8 fields (6 from WGI plus `events_total` and `events_filtered`). SIPRI milex has 8 fields (6 from WGI plus `regions_covered` and `country_count`). SIPRI Yearbook Ch.7 has **8 fields** (6 from WGI plus `pdf_pages_total` and `snapshot_year` for the PDF audit trail). The end-to-end test asserts all 8.

```python
def attribution() -> str:
    """Return the SIPRI Yearbook Ch.7 attribution block for public output (Rule #15)."""


def ingest_sipri_yearbook_ch7(
    *,
    year: int | None = None,
    pdf_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> SipriYearbookCh7IngestResult:
    """Run Stage 2 for SIPRI Yearbook Ch.7 end-to-end.

    Steps:

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_sipri_yearbook_ch7`.
       Open the PDF with ``pdfplumber``, find Table 7.1 on the first
       content page, extract the table, filter the aggregate row, pivot
       long → wide.
    3. Write the narrow parquet via
       :func:`write_sipri_yearbook_ch7_parquet`.
    4. Open a DB session, upsert the ``sources`` row, and write the
       ``source_observations`` rows.
    5. Build the :class:`SipriYearbookCh7IngestResult` and write the
       run manifest.
    6. Return the result.

    The function is the single public entry point — both the CLI
    command ``leaders-db ingest-source --source sipri_yearbook_ch7``
    and the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the ``LEADERSDB_PROJECT_ROOT``
    env var. No explicit ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g., ``2023``). Default: the
            snapshot year of the PDF (2024 for YB24). The function
            returns the snapshot year only; if a different year is
            passed, the function returns an empty DataFrame (no data
            for that year in the Yearbook Ch.7 snapshot).
        pdf_path: override the input PDF. Default: data-lake path.
        parquet_path: override the output parquet. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.
    """
```

### `__all__` (in `sipri_yearbook_ch7.py`)

```python
__all__ = [
    "SIPRI_YEARBOOK_CH7_ATTRIBUTION",
    "SIPRI_YEARBOOK_CH7_SOURCE_KEY",
    "IndicatorSpec",
    "SipriYearbookCh7IngestResult",
    "attribution",
    "ingest_sipri_yearbook_ch7",
    "register_sipri_yearbook_ch7_source",
    "write_sipri_yearbook_ch7_observations",
    "write_sipri_yearbook_ch7_run_manifest",
]
```

The DB helpers (`register_sipri_yearbook_ch7_source`, `write_sipri_yearbook_ch7_observations`, `write_sipri_yearbook_ch7_run_manifest`) are re-exported so the test-builder's tests can call them through the orchestrator module — same pattern as the WGI / WDI / UCDP / SIPRI milex test surface.

---

## 3.4 — Indicator catalog (the contract for the test fixture)

The test-builder will author `tests/fixtures/sipri_yearbook_ch7/sample.pdf` based on this spec. The developer will author `src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv` from this spec. The two artifacts must agree on the indicator list.

> **Source-of-truth principle.** If the test fixture count and the design catalog spec disagree, the design doc is the source of truth; the test fixture must match. This design specifies **3** indicators. The test fixture must therefore cover **3** indicators (one per catalog row).

### Catalog format

Same CSV format as `vdem.csv`, `wdi.csv`, `wgi.csv`, `ucdp.csv`, and `sipri_milex.csv` (Phase C convention #1). The 8 required columns are exactly the V-Dem / WDI / WGI / UCDP / SIPRI milex 8; the test fixture mirrors them.

```
variable_name,raw_column,rating_category,raw_scale,normalized_scale_target,higher_is_better,unit,description
```

### Indicator list (3 indicators, 1 category)

| # | Table col key (`raw_column`) | `variable_name` | Category | Scale | Unit | Direction | Why it matters |
|---|---|---|---|---|---|---|---|
| 1 | `total_inventory` | `sipri_yearbook_ch7_nuclear_warheads_total_inventory` | `nuclear` | `count` | `warheads` | `True` | The **headline count** of all warheads (deployed + reserve + retired awaiting dismantlement). The most-cited SIPRI Yearbook Ch.7 figure. Captures the absolute size of a state's nuclear arsenal. Higher = bigger arsenal = more nuclear capability. The score module normalizes this to a 0–1 scale (log1p transform expected, given the wide range 50–12,121). |
| 2 | `deployed` | `sipri_yearbook_ch7_nuclear_warheads_deployed` | `nuclear` | `count` | `warheads` | `True` | The count of warheads in **operational deployment** (on missiles or at operational bases). The "ready to use" count. Higher = more operationally alert warheads = more nuclear readiness. The score module normalizes this to a 0–1 scale. |
| 3 | `retired` | `sipri_yearbook_ch7_nuclear_warheads_retired` | `nuclear` | `count` | `warheads` | `False` | The count of warheads **awaiting dismantlement** (the disarmament pipeline). Higher = more warheads in the retirement pipeline = more disarmament activity (in the long run, this means the arsenal is shrinking). For the score module: more retired warheads = better disarmament signal = higher peace score. The score module inverts the raw value (the convention is the same as SIPRI milex's "more spending = worse peace" inversion). |

> **Why `higher_is_better=True` for `total_inventory` and `deployed`, but `False` for `retired`?** The scoring rubric treats the nuclear category as a "does this ruler have nuclear weapons" signal: more deployed warheads = more nuclear capability (which the rubric records as a fact, not as a positive or negative judgment — the manual review queue decides the political judgment). The retired count is different: more retired warheads = more disarmament activity, which is a positive peace signal (per requirement §9 "manual review queue" guidance). The `higher_is_better=False` for `retired` tells the score module to invert: more retired = better peace score. This is the SIPRI-Yearbook-Ch.7-specific calibration; the Stage 5 score module handles the inversion.
>
> **Calibration is the Stage 5 score module's job, not Stage 2's.** Stage 2 only writes the raw value to `source_observations.normalized_value` and preserves the scale + direction in the catalog. The `higher_is_better` column is documentation for Stage 5, not a transformation. The Stage 2 adapter does not apply any transform.

> **Why exactly 3, not 4 or 5?** The full Table 7.1 has 5 numeric columns: Deployed, Stored, Stockpile total, Retired, Total inventory. The "Stockpile total" (col 4) is derived from `Deployed + Stored`; the "Total inventory" (col 6) is derived from `Stockpile total + Retired`. The "Stored" column (col 3) is the central-storage subset of the stockpile; it is redundant with `Deployed` and `Stockpile total` for the scoring rubric (the score module can recompute it as `Stockpile total - Deployed` if needed). The 3 chosen indicators — `total_inventory`, `deployed`, `retired` — are the **non-derived, non-redundant** measures. The user can widen the catalog in a future iteration by adding `stored` or `stockpile_total` as 1-row extensions. The 3-indicator choice is the prototype default; the user may want to widen it.

> **Why not extract the `Year of first nuclear test` column?** The `Year of first nuclear test` column is metadata (when the state first demonstrated nuclear capability), not an indicator of current arsenal size. It is carried in the per-country dict (returned by `read_table_7_1`) for the audit trail (the `year_first_test` key) but NOT extracted as a `source_observations` indicator. The Stage 5 score module does not consume it. The user may want to add it as a derived indicator in a future iteration (e.g., `years_since_first_test` as a measure of arsenal maturity); the catalog is a 1-row extension if needed.

### `raw_scale` convention

| `raw_scale` | Used for | What it means |
|---|---|---|
| `count` | All 3 indicators | A non-negative integer count of warheads. The `source_observations.normalized_value` column shape is `int` (or `NULL` for the `".."` two-dot sentinel; `0` for the `"–"` en-dash sentinel). |

### `normalized_scale_target` convention

For the prototype, all 3 indicators normalize to `0-1` (matching V-Dem / WDI / WGI / UCDP / SIPRI milex). The actual normalization is the Stage 5 score module's job, not Stage 2's. Stage 2 only writes the raw value to `source_observations.normalized_value` and preserves the scale in the catalog.

> **Note on log scaling for the absolute counts.** The `total_inventory` count spans 50 (North Korea) to 12,121 (the published Total row, summing all 9 states). The per-country `total_inventory` spans 50 (North Korea) to 5,580 (Russia). A linear 0–1 normalization is heavily skewed by a few high-arsenal countries (USA, Russia). The Stage 5 score module will likely use a log transform (`log1p(value)` then linear 0–1) for the `total_inventory` and `deployed` indicators, mirroring UCDP's fatalities log transform and SIPRI milex's USD-millions log transform. The catalog's `normalized_scale_target = "0-1"` is the final target shape; the score module picks the transform. The Stage 2 adapter does not apply any transform.

### `unit` convention

| `unit` | Used for |
|---|---|
| `warheads` | All 3 indicators |

The SIPRI Yearbook Ch.7 unit is a concrete count (number of warheads), like UCDP's `events` / `deaths` units, unlike V-Dem's dimensionless `index` or WGI's dimensionless `z_score`.

### Test fixture shape (5 countries × 1 year × 3 indicators)

The test-builder's fixture `tests/fixtures/sipri_yearbook_ch7/sample.pdf` is a **real-format SIPRI Yearbook Ch.7 PDF** authored with `pdfplumber` + `reportlab` (committed under `tests/fixtures/sipri_yearbook_ch7/`). The PDF contains Table 7.1 with 5 country rows (a subset of the 9 real countries; chosen to match the V-Dem / WDI / WGI / UCDP / SIPRI milex test fixtures by display name: USA, Russia, UK, France, China — the 5 permanent UN Security Council members, which are the canonical "nuclear-armed" sample). Shape:

- **1 page** (the minimal page that contains the chapter title + Table 7.1).
- **Table 7.1** with the canonical column structure: `Country` (col 0), `Year of first nuclear test` (col 1), `Deployed` (col 2), `Stored` (col 3), `Stockpile total` (col 4), `Retired warheads` (col 5), `Total inventory` (col 6).
- **5 country rows** (USA, Russia, UK, France, China) + 1 aggregate row (`Total`) + 1 blank row separator. The test must verify the aggregate row is filtered out by the non-country denylist.
- **Real-format data**: the 5 countries' data values are pulled from the live YB24 PDF (USA: deployed 1770, stored 1938, stockpile total 3708, retired 1336, total inventory 5044; etc.). No invented values beyond the missing-value tokens.
- **At least 1 missing-value cell** for each of the 3 sentinels: `–` (en-dash), `..` (two-dot), `c. <num> <letter>` (the "approximately" annotation with a footnote letter). Suggested: UK's `Retired` cell is `–` (en-dash; per the live PDF), France's `Retired` cell is `..` (two-dot; per the live PDF), China's `Deployed` cell is `c. 24 j` (the live PDF's annotated form with footnote letter `j`).
- **No "Total" filter test data is needed for the footnote letters** beyond the 1 cell above. The footnote-letter-stripping path is exercised by the `c. 24 j` cell.

Total cells in the fixture data: 5 countries × 1 year × 3 catalog indicators = **15 indicator cells** + 2 missing-value cells (`".."` in France's retired, `"c. 24 j"` in China's deployed) + 1 en-dash cell (UK's retired, which becomes `0` in `normalized_value`) + 1 aggregate row (`Total`) filtered out. The read function returns a wide DataFrame of 5 × 1 = 5 rows × 5 columns (`country`, `year`, 3 indicator columns). The orchestrator writes 5 × 3 = **15 `source_observations` rows** when reading the full fixture (no year filter) and 0 rows when filtering to `year=2023` (the snapshot year is 2024; the year filter is an out-of-snapshot year; the function returns an empty frame).

> **Footnote-letter handling in the fixture.** The fixture uses the **literal** `c. 24 j` for China's deployed cell (with the footnote letter `j`). The Stage 2 PDF parser must strip the `c. ` prefix and the ` j` footnote letter, parse the integer `24`, and write `24` to `normalized_value`. The `raw_value` for that cell preserves the literal `c. 24 j` (or `c. 24` if the footnote letter is on a separate line; the test fixture uses the inline form to keep the parser simple). The test `test_read_sipri_yearbook_ch7_handles_c_prefix_missing` asserts this.

> **Total inventory column as derived (defense in depth).** The fixture's `Stockpile total` and `Total inventory` columns are **derived** (Stockpile total = Deployed + Stored; Total inventory = Stockpile total + Retired). The fixture must compute these correctly so the Stage 2 sanity check (the recompute in `read_table_7_1`) does not log a warning. The test `test_read_sipri_yearbook_ch7_recomputed_totals_match_published` asserts this.

> **PDF fixture generation tool.** The test-builder uses `reportlab` (or a similar Python PDF library) to write the test fixture. `reportlab` is NOT a project dependency; the test fixture-generation helper in `tests/fixtures/sipri_yearbook_ch7/build_sample_pdf.py` (a checked-in helper script) adds it as a `dev` extra in `pyproject.toml` (the developer updates `pyproject.toml` to add `reportlab>=4.0` to `[project.optional-dependencies] dev`). The fixture script is idempotent: re-running it overwrites the fixture. The committed fixture (`sample.pdf`) is what the tests use; the script is the source of truth for the fixture's contents.

---

## 3.5 — Test plan (what the test-builder writes)

The test plan covers the 5 Phase C convention #5 categories (catalog, read, write+DB, idempotency, attribution) plus the orchestrator and CLI. Every test has a defined fixture, an assertion, and a 1-line description. The WGI / UCDP / SIPRI milex test files are the template.

### Catalog (Phase C convention #5a)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_load_indicator_catalog_returns_3_specs` | The checked-in catalog has **3** indicators (matches §3.4 spec). | `sipri_yearbook_ch7_catalog_path` |
| `test_load_indicator_catalog_required_columns` | The 8 required CSV columns are present; the `rating_category` set is exactly `{"nuclear"}`. | same |
| `test_load_indicator_catalog_missing_file` | Missing catalog raises `FileNotFoundError`, not a silent empty list. | `tmp_path` |
| `test_indicator_spec_from_csv_row` | `higher_is_better=0`/`=1` round-trips to a real bool (matching V-Dem / WDI / WGI / UCDP / SIPRI milex). | inline dict |
| `test_catalog_variable_names_match_design` | The 3 `variable_name` values are exactly the names in §3.4: `sipri_yearbook_ch7_nuclear_warheads_total_inventory`, `sipri_yearbook_ch7_nuclear_warheads_deployed`, `sipri_yearbook_ch7_nuclear_warheads_retired`. | `sipri_yearbook_ch7_catalog_path` |
| `test_catalog_raw_columns_match_table_keys` | The 3 `raw_column` values are exactly the Table 7.1 column keys: `total_inventory`, `deployed`, `retired`. | same |
| `test_catalog_retired_is_higher_is_better_false` | The `retired` indicator's `higher_is_better` is `False` (the disarmament-pipeline inversion); the other 2 are `True`. | same |

### PDF read (Phase C convention #5b — new for this source)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_table_7_1_returns_5_country_rows` | The fixture PDF (5 countries) produces 5 country dicts (the aggregate `Total` row is returned in the list but the test counts the dicts that the I/O module filters out via the denylist; the test asserts the read_table_7_1 function returns 6 dicts and 1 of them has `country == "Total"`). | `sipri_yearbook_ch7_pdf_dir` (stages the sample PDF) |
| `test_read_table_7_1_handles_dash_sentinel` | The `–` (en-dash) cell in UK's `retired` becomes `0` in the dict's `retired` field; the `raw_value_retired` preserves the literal `"–"` (U+2013). | same |
| `test_read_table_7_1_handles_dots_sentinel` | The `..` (two-dot) cell in France's `retired` becomes `None` in the dict's `retired` field; the `raw_value_retired` preserves the literal `".."`. | same |
| `test_read_table_7_1_handles_c_prefix` | The `c. 24 j` cell in China's `deployed` becomes `24` in the dict's `deployed` field; the `raw_value_deployed` preserves the literal `"c. 24 j"`. | same |
| `test_read_table_7_1_strips_footnote_letter` | The footnote letter (`j` in `c. 24 j`) is stripped from the parsed integer; the parsed value is `24`, not `24 j`. | same |
| `test_read_table_7_1_recomputed_totals_match` | The recomputed `stockpile_total` (= `deployed + stored`) and `total_inventory` (= `stockpile_total + retired`) match the published values for all 5 countries (no warning logged). | same |
| `test_read_table_7_1_preserves_raw_values` | The 5 `raw_value_<col>` keys are present in each dict and preserve the original PDF cell verbatim. | same |
| `test_read_table_7_1_missing_pdf` | Missing PDF raises `FileNotFoundError` with an actionable message. | `tmp_path` |
| `test_read_table_7_1_table_not_found` | A PDF without Table 7.1 (e.g., a 1-page PDF with no tables) raises `ValueError` with an actionable message. | `tmp_path` (a stub PDF built with `reportlab` containing only a single line of text) |

### Read (Phase C convention #5b)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_sipri_yearbook_ch7_returns_full_fixture` | The fixture (5 countries × 1 year × 3 indicators) produces a wide DataFrame: 5 rows, 5 columns (`country`, `year`, 3 indicator columns). | `sipri_yearbook_ch7_pdf_dir` + `sipri_yearbook_ch7_catalog_path` |
| `test_read_sipri_yearbook_ch7_filters_to_year` | `year=2024` keeps only the 5 rows for 2024; `set(df["year"]) == {2024}`. | same |
| `test_read_sipri_yearbook_ch7_filters_to_other_year_returns_empty` | `year=2023` (an out-of-snapshot year) returns an empty DataFrame; `len(df) == 0`. | same |
| `test_read_sipri_yearbook_ch7_filters_total_row` | The `Total` aggregate row is NOT in the wide frame; `set(df["country"]) == {"United States", "Russia", "United Kingdom", "France", "China"}`. | same |
| `test_read_sipri_yearbook_ch7_pivots_long_to_wide` | Each catalog indicator is one column; no row is duplicated; no (country, indicator) cell is in long format. | same |
| `test_read_sipri_yearbook_ch7_handles_dash_sentinel` | The `–` cell in UK's `retired` becomes `0` in the DataFrame's `sipri_yearbook_ch7_nuclear_warheads_retired` column. | same |
| `test_read_sipri_yearbook_ch7_handles_dots_sentinel` | The `..` cell in France's `retired` becomes `pd.NA` (nullable Int64) in the DataFrame's `sipri_yearbook_ch7_nuclear_warheads_retired` column. | same |
| `test_read_sipri_yearbook_ch7_handles_c_prefix` | The `c. 24 j` cell in China's `deployed` becomes `24` in the DataFrame's `sipri_yearbook_ch7_nuclear_warheads_deployed` column. | same |
| `test_read_sipri_yearbook_ch7_attrs_carry_pdf_pages_and_snapshot_year` | `df.attrs["pdf_pages_total"] == 1` (the fixture is 1 page); `df.attrs["snapshot_year"] == 2024`. | same |
| `test_read_sipri_yearbook_ch7_missing_pdf` | Missing PDF raises `FileNotFoundError` with an actionable message. | `tmp_path` |
| `test_default_path_helpers` | `default_pdf_path()` points at `data/raw/sipri_yearbook_ch7/YB24 07 WNF.pdf`; raises `FileNotFoundError` if missing. `default_processed_parquet_path()` points at `data/processed/sipri_yearbook_ch7/sipri_yearbook_ch7_country_year.parquet`. | none |

### Parquet write + DB (Phase C convention #5c)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_sipri_yearbook_ch7_parquet_creates_file` | `write_sipri_yearbook_ch7_parquet(df)` writes a valid parquet under `data/processed/sipri_yearbook_ch7/`; round-trip preserves shape and columns. | `sipri_yearbook_ch7_pdf_dir` |
| `test_write_sipri_yearbook_ch7_parquet_attaches_attribution_metadata` | The parquet's file-level metadata carries `sipri_yearbook_ch7_attribution` (= `SIPRI_YEARBOOK_CH7_ATTRIBUTION`) and `sipri_yearbook_ch7_source_key` (= `b"sipri_yearbook_ch7"`) (Rule #15). | same |
| `test_register_sipri_yearbook_ch7_source_is_idempotent` | Two calls to `register_sipri_yearbook_ch7_source` return the same `sources.id`; the row has `source_name="SIPRI Yearbook Chapter 7 (World Nuclear Forces)"`, `version="YB2024 (data: January 2024)"`, `source_type="academic"`. | `database_url` + `_init_test_db` |
| `test_register_sipri_yearbook_ch7_source_non_destructive_update` | Removing the bundle's `metadata.json` between calls keeps the existing `source_url` and `license_note` (same policy as V-Dem / WDI / WGI / UCDP / SIPRI milex). | same |
| `test_write_sipri_yearbook_ch7_observations_row_count` | `len(df) * len(specs)` observations are written. With the fixture (5 rows × 3 indicators) the count is 15. | `sipri_yearbook_ch7_pdf_dir` + `database_url` |
| `test_write_sipri_yearbook_ch7_observations_is_idempotent` | Re-running produces the same count, not 2× the count. | same |
| `test_write_sipri_yearbook_ch7_observations_country_id_is_null` | `country_id` is `None` for every row (Stage 3 fills it); `confidence` is `None` for every row (Stage 11 fills it); `source_row_reference` starts with `"sipri_yearbook_ch7:"` and carries the display name verbatim. | same |
| `test_write_sipri_yearbook_ch7_observations_handles_dash_sentinel` | A `"–"` row (UK's retired) becomes `normalized_value=0` in SQLite; `raw_value` is the literal `"–"` (U+2013). | same |
| `test_write_sipri_yearbook_ch7_observations_handles_dots_sentinel` | A `".."` row (France's retired) becomes `normalized_value=NULL` in SQLite; `raw_value` is the literal `".."`. | same |
| `test_write_sipri_yearbook_ch7_observations_handles_c_prefix` | A `"c. 24 j"` row (China's deployed) becomes `normalized_value=24` in SQLite; `raw_value` is the literal `"c. 24 j"`. | same |
| `test_write_sipri_yearbook_ch7_observations_preserves_raw_value` | `raw_value` is the stringified int for non-missing cells (e.g., `"5044"` for the USA's total inventory); `raw_value` is the literal `"–"` / `".."` / `"c. 24 j"` for cells with the corresponding sentinels. | same |

### Orchestrator (Phase C convention #5d — end-to-end idempotency)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_ingest_sipri_yearbook_ch7_end_to_end` | `ingest_sipri_yearbook_ch7()` writes the parquet, the sources row, the 15 `source_observations` rows, and the manifest in one call. Result has `countries=5, years=(2024,), indicators=3, pdf_pages_total=1, snapshot_year=2024`. | `sipri_yearbook_ch7_pdf_dir` + `database_url` |
| `test_ingest_sipri_yearbook_ch7_filters_to_year` | `year=2024` keeps 5 countries × 1 year × 3 indicators = 15 observation rows. | same |
| `test_ingest_sipri_yearbook_ch7_filters_to_other_year_returns_empty` | `year=2023` produces 0 observation rows and an empty wide frame; the orchestrator still writes the sources row and the manifest. | same |
| `test_ingest_sipri_yearbook_ch7_is_idempotent` | Two consecutive `ingest_sipri_yearbook_ch7()` calls produce the same `observation_rows` count, the same `source_id`, and the parquet's mtime is the same (no re-write). | same |
| `test_ingest_sipri_yearbook_ch7_result_carries_attribution` | The `SipriYearbookCh7IngestResult.attribution` property returns `SIPRI_YEARBOOK_CH7_ATTRIBUTION` byte-for-byte; `result.attribution == SIPRI_YEARBOOK_CH7_ATTRIBUTION`. | same |
| `test_ingest_sipri_yearbook_ch7_result_carries_pdf_pages_and_snapshot_year` | The `SipriYearbookCh7IngestResult.pdf_pages_total` field is `1`; the `snapshot_year` field is `2024`; both are surfaced from `df.attrs`. | same |
| `test_ingest_sipri_yearbook_ch7_result_field_count` | The `SipriYearbookCh7IngestResult` has exactly 8 fields (matches §3.3 spec): `source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`, `pdf_pages_total`, `snapshot_year`. (The end-to-end test asserts the fields that **are** present, not the fields that are absent — same as the WGI / SIPRI milex lesson.) | same |

### Attribution / Rule #15

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_run_manifest` | The manifest is JSON next to the parquet, includes `attribution`, `source_id`, `observation_rows`, `years`, `indicators`, `pdf_pages_total`, `snapshot_year`. | `isolated_data_lake` |
| `test_attribution_matches_constant` | `sipri_yearbook_ch7.attribution() == SIPRI_YEARBOOK_CH7_ATTRIBUTION`; contains `"SIPRI"`, `"2024"`, `"World Nuclear Forces"`, `"Yearbook 2024"`, `"Oxford University Press"`. | — |
| `test_sipri_yearbook_ch7_attribution_matches_attributions_doc` | `SIPRI_YEARBOOK_CH7_ATTRIBUTION` is a substring of `docs/source-attributions.md` (drift guard, same pattern as V-Dem's `test_vdem_attribution_matches_attributions_doc`, WGI's `test_wgi_attribution_matches_attributions_doc`, UCDP's `test_ucdp_attribution_matches_attributions_doc`, and SIPRI milex's `test_sipri_milex_attribution_matches_attributions_doc`). | project root |

### CLI dispatch

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_stage2_adapters_dispatch_table` | `STAGE2_ADAPTERS["sipri_yearbook_ch7"] is sipri_yearbook_ch7.ingest_sipri_yearbook_ch7`; the full key set is unchanged (25 keys, with the `sipri_yearbook_ch7` value changing from `None` to the orchestrator). The existing `"sipri_yearbook_ch7": None,` line in `__init__.py` is REPLACED, not duplicated. | — |
| `test_cli_ingest_source_rejects_unknown` | `leaders-db ingest-source --source nope` exits non-zero. | `CliRunner` |

### Public surface

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_sipri_yearbook_ch7_module_public_surface` | The `sipri_yearbook_ch7` module exports the items in `__all__` from §3.3: `SIPRI_YEARBOOK_CH7_ATTRIBUTION`, `SIPRI_YEARBOOK_CH7_SOURCE_KEY`, `IndicatorSpec`, `SipriYearbookCh7IngestResult`, `attribution`, `ingest_sipri_yearbook_ch7`. | — |

### Live-PDF smoke (manual, not in pytest)

| Test name | What it asserts | When |
|---|---|---|
| `manual: smoke SIPRI Yearbook Ch.7 end-to-end against real PDF` | `ingest_sipri_yearbook_ch7()` against the real 717 KB PDF returns 9 real countries × 3 indicators = **27 `source_observations` rows**; the `pdf_pages_total == 97`; the `snapshot_year == 2024`. | After implementation, manual one-shot, recorded in `docs/testing-guide-stage2-sipri_yearbook_ch7.md` |

The manual smoke is gated on a real on-disk PDF (the user downloads it via `curl` to `data/raw/sipri_yearbook_ch7/YB24 07 WNF.pdf` first). The test fixture (`tests/fixtures/sipri_yearbook_ch7/sample.pdf`) is a 5-country × 1-year × 3-indicator slice that fits in <10 KB and is what the unit tests use. The unit tests prove the contract; the manual smoke proves the real PDF still works.

---

## 3.6 — Edge cases & known issues

### PDF parsing brittleness (the new edge case for this source)

PDF table extraction is inherently brittle: the same logical table can be rendered with different line widths, font metrics, and cell boundaries in different editions. The Stage 2 PDF parser uses `pdfplumber` with the `lines` strategy (which relies on the PDF's vector lines to find cell boundaries). Live probe of YB24 with the `lines` strategy extracts Table 7.1 with 7 columns × 11 rows (header + 9 country rows + 1 Total row) — exactly the expected shape. The test fixture uses the same `lines` strategy, so the parser's behavior is identical for the fixture and the real PDF.

> **What if a future Yearbook edition changes the table layout?** The drift-guard test `test_default_path_helpers` catches filename changes (e.g., `YB25 07 WNF.pdf` instead of `YB24 07 WNF.pdf`). A layout change (e.g., adding a new column) would be caught by `test_read_sipri_yearbook_ch7_returns_full_fixture` (which asserts 3 indicator columns). The defensive fix: if `extract_table` returns 0 tables on the Table 7.1 page, the parser falls back to the `text` strategy (which uses font positions to find cell boundaries). If the `text` strategy also returns 0 tables, the parser raises `RuntimeError` with an actionable message ("Table 7.1 not found in the PDF; check that the table layout has not changed in the new Yearbook edition"). This is a 5-line defensive check; the developer adds it.

### Missing-value convention: three tokens (`–`, `..`, `c. <num> <letter>`)

The three missing-value / annotation tokens differ from every other Stage 2 source:

| Token | Meaning | Stage 2 handling |
|---|---|---|
| `–` (en-dash, U+2013) | Nil or a negligible value (per Table 7.1 legend) | → `0` in `normalized_value`; `raw_value` preserves the literal `"–"` |
| `..` (two ASCII dots) | Not applicable or not available (per Table 7.1 legend) | → `None` in `normalized_value`; `raw_value` preserves the literal `".."` |
| `c. <num> [letter]` (e.g., `"c. 24 j"`) | A footnote "approximately" annotation | → `int(num)` in `normalized_value`; `raw_value` preserves the literal annotated string |

> **Why is `–` coerced to `0` and `..` to `None`?** Per the Table 7.1 legend, `–` means "nil or a negligible value" (the data point is 0, by definition), while `..` means "not applicable or not available" (the data point is missing). The semantic distinction is important: the UK has 0 retired warheads (the `–` sentinel), but France has no retired warheads **for the purposes of this report** (the `..` sentinel — France's retired warheads are unknown or not applicable, not zero). Coercing both to `0` would conflate the two; coercing both to `None` would lose the UK's `0` retired count. The Stage 2 adapter preserves the distinction in `normalized_value` (0 vs None) and the audit trail in `raw_value` (`"–"` vs `".."`). The Stage 5 score module can decide whether to treat `0` and `None` differently (e.g., apply a confidence penalty to `None` per requirement §13 "older years degrade gracefully").

The `_SIPRI_YEARBOOK_CH7_MISSING_STRINGS` frozenset in `sipri_yearbook_ch7_db.py` is the SIPRI-Yearbook-Ch.7-specific superset of the WGI / V-Dem / WDI / UCDP / SIPRI milex sentinels:

```python
_SIPRI_YEARBOOK_CH7_MISSING_STRINGS: frozenset[str] = frozenset(
    {"–", "..", "N/A", "NA", "NaN", "nan", "null", "None", "-999", "-999.0", ""}
)
```

The two new tokens (`"–"` and `".."`) are the only SIPRI-Yearbook-Ch.7-specific additions (the `"c. <num> [letter]"` pattern is a separate annotation, not a missing-value sentinel — see below).

> **Why is `"c. <num> [letter]"` not a missing-value sentinel?** The `"c. 24"` pattern means "approximately 24" (the leading `c.` is short for "circa"). It is a numerical annotation, not a missing value. The PDF parser strips the `c. ` prefix and the footnote letter, parses the integer, and writes the parsed integer to `normalized_value`. The `raw_value` preserves the literal annotated string for the audit trail. The Stage 2 adapter does NOT treat `"c. 24 j"` as a missing value; it treats it as a numerical value with a footnote.

### Footnote-letter stripping (the PDF-specific data quirk)

The PDF cells can carry a footnote-letter suffix (`"1 770 d"`, `"24 j"`, `"50 k"`) which is part of the value (it refers the reader to the notes section). The Stage 2 PDF parser uses a regex to strip the footnote letter:

```python
import re
_FOOTNOTE_LETTER_RE = re.compile(r"^[cC]\.\s*(\d[\d\s]*)\s*([a-z])?$|^\s*(\d[\d\s]*)\s*([a-z])\s*$")
```

The regex matches three patterns:
1. `"c. 24 j"` (with leading `c.` and footnote letter)
2. `"24 j"` (with footnote letter, no `c.` prefix)
3. `"24"` (no footnote letter, no `c.` prefix — pure numeric)

The regex extracts the digit group and (optionally) the footnote letter; the parsed integer is the digit group; the footnote letter is dropped. The `raw_value` preserves the original cell verbatim (including the footnote letter, the `c. ` prefix, and any whitespace).

> **Why preserve the footnote letter in `raw_value`?** The footnote letter is part of the original cell; preserving it in `raw_value` lets a reviewer trace the value back to the notes section. The Stage 2 adapter does not extract the notes; the audit trail is the only place where the footnote letter survives.

### Country name format (no ISO3 column, like SIPRI milex)

The PDF uses display names (e.g. `"United States"`, `"Russia"`, `"United Kingdom"`, `"France"`, `"China"`, `"India"`, `"Pakistan"`, `"North Korea"`, `"Israel"`) but **no ISO3 column**. The Stage 2 adapter:

1. Stores the raw display name in `source_row_reference` as `"sipri_yearbook_ch7:United States"`.
2. Leaves `country_id` NULL in `source_observations` (Stage 3 fills it via `country_aliases.csv`).
3. The wide frame's `country` column carries the raw display name.

**No rename table in Stage 2.** Stage 3 (country match) resolves the SIPRI display name to ISO3 via the `country_aliases.csv` table. The list of known quirks (for the test-builder's reference; **no Stage 2 code change required**):

| SIPRI display name | ISO3 | Notes |
|---|---|---|
| `United States` | `USA` | OK |
| `Russia` | `RUS` | OK; the live PDF does NOT have `"USSR"` (pre-1992) or `"Russian Federation"` |
| `United Kingdom` | `GBR` | uses the "United Kingdom" form; some ISO lists use "UK" or "Britain" |
| `France` | `FRA` | OK |
| `China` | `CHN` | OK; the live PDF does NOT have `"People's Republic of China"` |
| `India` | `IND` | OK |
| `Pakistan` | `PAK` | OK |
| `North Korea` | `PRK` | uses the short form; the PDF text body uses "DPRK" and "Democratic People's Republic of Korea" but the table cell is `"North Korea"` |
| `Israel` | `ISR` | OK; the live PDF has `".."` for the "Year of first nuclear test" cell (deliberate ambiguity policy) |

Stage 3 has a `country_aliases` table that handles these. Stage 2's contract is to write the SIPRI display name verbatim.

### Snapshot year (no time series)

The Yearbook Ch.7 data is a **point-in-time snapshot** (January 2024). The Stage 2 wide frame's `year` column is the snapshot year (2024 for the YB24 PDF). If the user passes `year=2023`, the function returns an empty DataFrame. The Stage 5 score module will use the 2024 number as the input for the 2024 score; for the 2023 score, the module will need to look up the 2023 YB23 PDF (a future iteration) or apply a 1-year decay penalty (per requirement §13 "older years degrade gracefully").

> **No backward-compatibility concern for older years.** The Stage 2 adapter is "Yearbook year = score year" by design. A future iteration that supports multi-year nuclear tracking would need to ingest multiple Yearbook PDFs (YB23, YB24, YB25) and pivot the time series. That is a future iteration; the prototype locks in 1 year.

### Coverage year drift (the 2024 release year, 2024 data year)

The current release is the SIPRI Yearbook 2024 (Ch.7), and the data is the January 2024 snapshot. The [`docs/source-attributions.md`](../source-attributions.md) summary table says "annual" for the coverage — which is correct (the Yearbook is annual, but each Yearbook is a 1-year snapshot). **The developer does NOT need to fix the coverage field** (the doc is already correct). The catalog's `_RAW_PDF_NAME = "YB24 07 WNF.pdf"` and the `version="YB2024 (data: January 2024)"` in `register_sipri_yearbook_ch7_source` are the version-locked identifiers.

### Per-cell read performance

The PDF is 717 KB with 97 pages. With `pdfplumber`, the per-page iteration is fast; the Table 7.1 extraction is on page 1, so the read function opens the PDF, scans pages 1–3 for the `"Table 7.1."` string, and extracts the table from the matching page. The whole read takes < 1 s on a typical laptop. The test fixture is 1 page and reads in < 100 ms.

### `LEADERSDB_PROJECT_ROOT` interaction

The `pdf_path` defaults to `raw_dir("sipri_yearbook_ch7") / _RAW_PDF_NAME`. The `isolated_data_lake` test fixture overrides `LEADERSDB_PROJECT_ROOT`, so the PDF lives under the test's temp dir. The test fixture `sipri_yearbook_ch7_pdf_dir` stages the sample PDF under the temp-dir; the unit tests pass cleanly.

### `obs_status` and other per-cell metadata

SIPRI Yearbook Ch.7 does not have an `obs_status` field per cell. The cell is either a number (with optional `c.` prefix and footnote letter), a missing-value token (`–` or `..`), or a footnote-letter annotation. The `notes` column of `source_observations` carries the footnote letter only if present; for cells with no footnote letter, `notes` is `NULL` or `""`. The Stage 2 adapter does not extract the notes as a separate indicator (deferred; the notes are useful for the LLM rationale in Stage 9–10, not for the prototype's indicator values).

### Stage 1 (client matrix) interaction

SIPRI Yearbook Ch.7 has no Stage 1 interaction — the client matrix is the 2023 validation/test reference and is read separately, never counted as source evidence. SIPRI Yearbook Ch.7 is the **only** implemented source for the `nuclear` category; the FAS Nuclear Notebook is the planned cross-validation source for the manual-review queue. The Stage 2 → Stage 12 (compare-vs-client) flow is unchanged by SIPRI Yearbook Ch.7's presence (the client matrix has its own `nuclear` column that the adapter does not overwrite).

### Network reachability in CI

SIPRI Yearbook Ch.7 has no HTTP layer in the Stage 2 adapter. The unit tests are fully offline (the PDF fixture is local). The manual smoke is the only "is the real PDF still what we think it is" check. (Live liveness was verified 2026-06-18; the URL is reachable and the file downloads to 717 KB.)

### `df.attrs` survives the parquet write

The `df.attrs["pdf_pages_total"]` and `df.attrs["snapshot_year"]` fields are JSON-serializable (an int and an int). The `_attach_parquet_metadata` helper in `sipri_yearbook_ch7_io.py` does NOT strip them. The orchestrator surfaces `pdf_pages_total` and `snapshot_year` in `SipriYearbookCh7IngestResult` before calling the parquet writer, so they survive even if the parquet rewrite fails (the run manifest is the audit fallback).

### `pdfplumber` as a new project dependency

`pdfplumber` is a new project dependency introduced by this adapter. The developer adds `pdfplumber>=0.11` to the `[project] dependencies` list in `pyproject.toml` in the same commit as the adapter lands. This is a project-level change, not a per-source change; the dependency lives in the top-level deps so all future PDF sources can reuse it. (The `reportlab` test fixture-generation library is a `[project.optional-dependencies] dev` extra, not a runtime dep.)

---

## 3.7 — Dispatch table entry

The `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py` needs one change: replace the existing `"sipri_yearbook_ch7": None` stub with the live import, and add the `from . import sipri_yearbook_ch7, sipri_milex, ucdp, vdem, wdi, wgi` line. **No new dispatch key is added** — the key is already there from Phase A.

### Exact changes

In `src/leaders_db/ingest/__init__.py`:

```python
# Add the import alongside the vdem, wdi, wgi, ucdp, sipri_milex imports at the top of the import block:
from . import sipri_milex, sipri_yearbook_ch7, ucdp, vdem, wdi, wgi

# In the STAGE2_ADAPTERS dict, change the existing line:
    "sipri_yearbook_ch7": None,
# to:
    "sipri_yearbook_ch7": sipri_yearbook_ch7.ingest_sipri_yearbook_ch7,
```

The full dispatch table stays the same shape (25 keys); only the value of the `sipri_yearbook_ch7` key changes from `None` to the orchestrator. All other `None` stubs (`pts`, `undp_hdi`, `who_gho_api`, `polity_v`, `pwt`, `archigos`, `reign`, `leader_survival`, `transparency_cpi`, `fas`, `wikidata_heads_of_state_government`, `wikipedia_search_extract`, `freedom_house`, `imf_weo`, `cow_mid`, `cirights`, `nti`, `bti`, `cia_world_leaders`) are untouched and remain for the next batches.

> **Reviewer-bug from WDI / UCDP history (apply the lesson):** the WDI review found 1 blocker (a duplicate `"world_bank_wgi"` dispatch key that had been silently masked); the UCDP review found 1 blocker (a duplicate `"sipri_milex"` dispatch key from an earlier copy-paste). The current dispatch table (post-UCDP fix) has exactly **one** `"sipri_yearbook_ch7"` entry, with value `None`. Do not accidentally add a second one. The dispatch-table test (`test_stage2_adapters_dispatch_table` in the new `tests/test_ingest_sipri_yearbook_ch7.py`) asserts the key set is exactly the 25 keys.

The `__all__` does not need to change. No CLI code change is needed — the CLI already iterates over the dispatch table.

---

## 3.8 — Workplan / docs updates

When the SIPRI Yearbook Ch.7 adapter lands and the reviewer signs off, the project-manager will add the following entries to `docs/workplan.md` (Done History) and update `docs/source-attributions.md` (if needed), `docs/source-vetting/report.md`, and `docs/data-sources.md`.

### `docs/workplan.md` — new Done History entry

> **Phase C.6 — SIPRI Yearbook Ch.7 Stage 2 ingest landed (DATE).** Sixth Stage 2 adapter implemented via the architect → test-builder → developer → reviewer pipeline. ~35 new tests in `tests/test_ingest_sipri_yearbook_ch7.py` (~252 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/sipri_yearbook_ch7.csv` lists 3 SIPRI Yearbook Ch.7 indicators (total_inventory, deployed, retired), all under `nuclear`. **First PDF source in the pipeline** — the adapter uses `pdfplumber` to extract Table 7.1 from the 717 KB `YB24 07 WNF.pdf` (97-page PDF). The PDF parser lives in a new module `sipri_yearbook_ch7_pdf.py` (the only structurally new piece vs the WGI / UCDP / SIPRI milex pattern). The read function extracts the table from the first content page, filters the 1 aggregate row (`Total`), coerces 3 sentinels (`–` for nil, `..` for not-applicable, `c. <num> [letter]` for annotated numerics with footnote letters), strips the footnote letter suffix, recomputes the derived totals (`stockpile_total = deployed + stored`, `total_inventory = stockpile_total + retired`) as a sanity check, and pivots long → wide. The wide frame is 9 country-year rows × 3 indicator columns for the real PDF (1 snapshot year, 2024). SIPRI Yearbook Ch.7 is the **only source for the `nuclear` category** (per the source-vetting report §3.7). Test fixture at `tests/fixtures/sipri_yearbook_ch7/sample.pdf` is a 1-page real-format SIPRI Yearbook Ch.7 PDF authored with `reportlab` (5 countries × 1 year × 3 indicators = 15 indicator cells, 1 `–` cell, 1 `..` cell, 1 `c. 24 j` cell, 1 aggregate `Total` row filtered out). End-to-end run against the real 717 KB PDF produces 9 real countries × 3 indicators = 27 `source_observations` rows in < 1 s. The `SIPRI_YEARBOOK_CH7_ATTRIBUTION` constant is byte-identical to the citation in `docs/source-attributions.md` (drift-guard test added). The `pdfplumber>=0.11` dependency is added to `[project] dependencies` in `pyproject.toml`; the `reportlab>=4.0` test fixture helper dep is added to `[project.optional-dependencies] dev`. `STAGE2_ADAPTERS["sipri_yearbook_ch7"]` is now `sipri_yearbook_ch7.ingest_sipri_yearbook_ch7` in `src/leaders_db/ingest/__init__.py`. SIPRI Yearbook Ch.7 follows the WGI / SIPRI milex 5-module split with the new `sipri_yearbook_ch7_pdf.py` module for the PDF parser. **Moving to PTS next per the priority list.**

### `docs/source-attributions.md` — no change required

The `sipri_yearbook_ch7` entry in `docs/source-attributions.md` §1 is already correct and matches the `SIPRI_YEARBOOK_CH7_ATTRIBUTION` constant byte-for-byte. The developer does NOT update the doc; the drift-guard test confirms consistency.

> **Cross-check the doc citation text before the test-builder writes `test_sipri_yearbook_ch7_attribution_matches_attributions_doc`.** The doc citation text is: `Stockholm International Peace Research Institute. 2024. "World Nuclear Forces." In SIPRI Yearbook 2024: Armaments, Disarmament and International Security. Oxford University Press.` The constant's text in §3.3 matches this verbatim. If the doc is updated in the future (e.g., a new Yearbook edition is released), the developer updates the constant in the same commit (the drift-guard test fails otherwise).

### `docs/source-vetting/report.md` — one minor update

§3.7 ("Conflict / international aggression sources") `sipri_yearbook_ch7` row gets a one-line note: "Stage 2 adapter landed; see `src/leaders_db/ingest/sipri_yearbook_ch7.py`. 3 indicators under `nuclear`: total_inventory, deployed, retired. The PDF has no ISO3 column; Stage 3 resolves the display name to ISO3 via `country_aliases.csv`. The PDF parser uses `pdfplumber`."

§6 ("Caveats the Stage 2 ingest must handle") `sipri_yearbook_ch7` row gets an update:

| Source | Caveat to handle |
|---|---|
| `sipri_yearbook_ch7` | (was) "Discover the latest version at runtime; do not hard-code `YB24 07 WNF.pdf`." → (now) "**The PDF is 97 pages; the Stage 2 adapter reads only Table 7.1 on the first content page. The PDF parser uses `pdfplumber.extract_table()` with the `lines` strategy (most robust for Adobe InDesign-rendered tables); it falls back to the `text` strategy if `lines` returns 0 tables. The Table 7.1 has 3 missing-value tokens: `'–'` (U+2013, en-dash; nil or negligible value, coerced to `0`), `'..'` (two ASCII dots; not applicable or not available, coerced to `None`), and the `'c. <num> [letter]'` annotation pattern (e.g., `'c. 24 j'` for China's deployed warheads; the `c.` prefix and footnote letter are stripped, the integer is parsed). The `raw_value` audit trail preserves the literal original cell (including the `c.` prefix and footnote letter). The 1 aggregate row (`Total`) is filtered out by the `_SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS` denylist. The PDF has no ISO3 column; the Stage 2 adapter stores the raw display name in `source_row_reference` as `sipri_yearbook_ch7:<display_name>` and leaves `country_id` NULL for Stage 3 to fill via `country_aliases.csv`.**" |

### `docs/data-sources.md` — one update

The existing `sipri_yearbook_ch7` row says "PDF; 717 KB; 1 chapter; 9 countries." Update to: "PDF download; 717 KB; 97 pages; 14 tables (Table 7.1 is the only one extracted); 9 nuclear-armed states; 3 catalog indicators under `nuclear` (total_inventory, deployed, retired). The PDF has no ISO3 column; Stage 3 resolves the display name to ISO3 via `country_aliases.csv`. Stage 2 adapter landed."

### `docs/architecture.md` — no change required

The existing `architecture.md` already lists SIPRI Yearbook Ch.7 as one of the per-source Stage 2 adapters (the "Conflict / international aggression sources" section). No structural change is needed.

### `pyproject.toml` — two new dependencies

The developer adds `pdfplumber>=0.11` to `[project] dependencies` (a runtime dep, since the Stage 2 adapter needs it to read the PDF) and `reportlab>=4.0` to `[project.optional-dependencies] dev` (a test-only dep, since the test fixture-generation helper needs it). Both additions are in the same commit as the adapter lands.

### `docs/req/requirements-core.md` — no change required

The existing `nuclear` category in `docs/req/requirements-core.md` already lists SIPRI Yearbook Ch.7 as the source; the new adapter does not change the requirement set, only the implementation.

---

## 3.9 — Lessons from WDI / WGI / UCDP / SIPRI milex / V-Dem reviews (apply to SIPRI Yearbook Ch.7 from day one)

These are the WDI review findings, the WGI review findings, the UCDP review findings, the V-Dem review findings, and the SIPRI milex review findings. Apply them to SIPRI Yearbook Ch.7 from the start so we don't repeat them.

### WDI lessons (apply all 8)

1. **No duplicate dispatch-table keys.** The `__init__.py` already has exactly one `"sipri_yearbook_ch7": None` entry (Phase A placeholder). Do not add a second one. The dispatch-table test asserts the 25-key set.

2. **No ruff warnings in the test file.** Hoist all imports to the top; no unused imports; no lines >100 chars. The test-builder must follow the WGI / V-Dem convention (`from __future__ import annotations` first, then `import json, shutil`, then `from pathlib`, then third-party, then `from leaders_db...`).

3. **End-to-end test for orchestrator-level fields.** The `SipriYearbookCh7IngestResult` has 8 fields (`source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`, `pdf_pages_total`, `snapshot_year`). The end-to-end test must assert all 8, not just internal function call counts.

4. **Docstring accuracy.** Match the runtime default in the docstring (e.g., `year: int | None = None` should be documented as "Default: the snapshot year of the PDF (2024 for YB24)", not "Required"). The `sipri_yearbook_ch7.py` docstring should NOT say "400-line convention" or similar lies; each module's line count will be reported in the Done History entry, not in the source docstring.

5. **Design doc accuracy.** The catalog CSV is the source of truth; the design doc must match exactly. If the developer discovers a discrepancy (e.g., the live PDF has a different table column name than the design says), update the design doc in the same commit.

6. **`confidence IS NULL` assertion.** The Stage 2 → Stage 11 contract requires `confidence` NULL; the test must assert it (`assert all(r.confidence is None for r in rows)`).

7. **`raw_value` assertion.** The test must assert the `raw_value` for non-missing cells is the stringified int, and for missing cells it is the literal `"–"` / `".."` / `"c. <num> [letter]"` (the audit trail of the original PDF cell). This is the SIPRI-Yearbook-Ch.7-specific corollary of V-Dem's `"-999.0"` assertion, WGI's `"#N/A"` assertion, WDI's `"nan"` assertion, UCDP's `str(0)` for 0-fatality events assertion, and SIPRI milex's `"..."` / `"xxx"` assertions.

8. **Live-PDF smoke verification.** Run the adapter against the real 717 KB PDF after tests pass; verify row count (9 countries × 3 indicators = 27 `source_observations` rows), the `pdf_pages_total` (97), the `snapshot_year` (2024), and the SIPRI Yearbook Ch.7 attribution in the CLI end-of-run output. Recorded in `docs/testing-guide-stage2-sipri_yearbook_ch7.md`.

### WGI lessons (apply all 6)

1. **The WGI reviewer's #3 (index-swap SQL) was a release-blocker because the developer changed the schema to make a test pass. Never change the schema or canonical text to make a test pass. Fix the test instead.** Specifically for SIPRI Yearbook Ch.7:
   - If a test uses a fragile dict-comprehension pattern, fix the test to sort the rows before building the dict, or use `.order_by()`.
   - If a test asserts on a canonical text (like `"SIPRI" in attribution`), change the test to assert on a substring that's actually in the canonical text (like `"Stockholm International Peace Research Institute" in attribution` or `"World Nuclear Forces" in attribution`), not the canonical text itself.
   - If a test fails because the catalog column name doesn't match the real data, change the test to match the data, not the data to match the test.

2. **WGI line counts exceeded 400.** For SIPRI Yearbook Ch.7, design the module split upfront so no file exceeds 400 lines. The 5-module split (`sipri_yearbook_ch7.py` ~200-260, `sipri_yearbook_ch7_io.py` ~260-320, `sipri_yearbook_ch7_pdf.py` ~140-200, `sipri_yearbook_ch7_db.py` ~280-340, `sipri_yearbook_ch7_db_helpers.py` ~100-150) is the target. If a module grows past 400, split it during implementation.

3. **WGI `default_xlsx_path()` raise semantics.** SIPRI Yearbook Ch.7's `default_pdf_path()` must also raise `FileNotFoundError` if the file is missing (per the design's stated contract in §3.3). The test `test_default_path_helpers` verifies this.

### UCDP lessons (apply all 5)

1. **No duplicate dispatch-table keys (the UCDP reviewer's #1 blocker).** The `__init__.py` already has exactly one `"sipri_yearbook_ch7"` entry. Do not accidentally add a second one.

2. **No stale stub comment.** The UCDP reviewer's #3 was a stale comment in `ucdp.py` that said "UCDP is the second Stage 2 adapter" (it was the fourth). For SIPRI Yearbook Ch.7, the module docstring must say "sixth Stage 2 adapter" (matching the actual order: V-Dem, WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7).

3. **No stale `# type: ignore` comments.** UCDP had a stale `# type: ignore` that hid a real type error. SIPRI Yearbook Ch.7 must use `from __future__ import annotations` and proper type hints throughout; no `# type: ignore` unless the upstream type system is genuinely wrong (and a comment explains why). The `pdfplumber` library has clean type stubs; no `# type: ignore` should be needed.

4. **No design-doc contradictions.** The UCDP reviewer's #2 blocker was a "dense vs sparse frame" contradiction in the design doc. For SIPRI Yearbook Ch.7, the wide frame is **dense** (every country-year row is present, even when the country has no data — the year cell is `pd.NA`); the design must consistently say "dense" in both the read docstring and the public surface docstring.

5. **No schema mutation.** UCDP had a release-blocker (the WGI pattern: never DROP/CREATE indexes in the orchestrator). SIPRI Yearbook Ch.7 must not touch the schema; the `register_sipri_yearbook_ch7_source` function only does an upsert via SQLAlchemy, no DDL.

### V-Dem lessons (apply all 4)

1. **`_coerce_int` handles all the missing-data sentinels in one place** (defense in depth). SIPRI Yearbook Ch.7's `_coerce_int` must handle the 3 SIPRI-Yearbook-Ch.7-specific sentinels (`"–"`, `".."`, the `"c. <num> [letter]"` pattern), the V-Dem / WGI / WDI / UCDP / SIPRI milex sentinels (`"..."`, `"xxx"`, `"#N/A"`, `null`, `NaN`, `nan`, `NA`, `-999`, `-999.0`), and the PDF-specific sentinels (`""`, `None`).

2. **`_raw_value_to_string` preserves the original cell for the audit trail** (per the V-Dem pattern in `vdem_db.py:199`). For SIPRI Yearbook Ch.7, the audit-trail string is `str(cell)` for present cells (preserving the `c.` prefix and footnote letter if present), and the literal `"–"` / `".."` / `""` for missing cells. The test asserts all 3 missing-token cases.

3. **V-Dem's `_delete_existing_observations` is the same pattern as SIPRI Yearbook Ch.7's** — delete existing rows for the requested years before inserting (so re-runs are idempotent for the year filter, but older years are untouched).

4. **V-Dem's `country_id` rename (to `vdem_country_id`) does NOT apply to SIPRI Yearbook Ch.7.** SIPRI Yearbook Ch.7's wide frame's `country` column carries the raw display name (NOT a UCDP-style integer ID, NOT a V-Dem-style `vdem_country_id`). The wide frame's `country` column is the SIPRI display name verbatim. The `source_observations.country_id` is left NULL (Stage 3 fills it). The `source_row_reference` is `"sipri_yearbook_ch7:<display_name>"`. This is the SIPRI-Yearbook-Ch.7-specific pattern that differs from V-Dem and UCDP.

### SIPRI milex lessons (apply all)

The SIPRI milex adapter is the closest analog. The lessons are:

1. **No ISO3 column in the source data.** SIPRI milex's display-name passthrough pattern is the template: store the raw display name in `source_row_reference`, leave `country_id` NULL for Stage 3. SIPRI Yearbook Ch.7 uses the same pattern.

2. **The missing-value convention differs from the V-Dem / WGI / UCDP / WDI sentinels.** SIPRI milex's `"..."` / `"xxx"` / `""` are the SIPRI-specific sentinels. SIPRI Yearbook Ch.7's `"–"` / `".."` / `"c. <num> [letter]"` are the SIPRI-Yearbook-Ch.7-specific sentinels. Both adapters have a `_SOURCE_MISSING_STRINGS` frozenset that is a superset of the WGI / V-Dem / WDI / UCDP sentinels.

3. **The `_coerce_*` helper pattern.** SIPRI milex's `_coerce_float` (in `sipri_milex_db.py`) is the model for SIPRI Yearbook Ch.7's `_coerce_int` (in `sipri_yearbook_ch7_db.py`). Both helpers handle the source-specific sentinels in one place and return `None` for the "not available" case (and `0` for the "nil/negligible" case, in SIPRI Yearbook Ch.7's case).

4. **The `df.attrs` audit pattern.** SIPRI milex's `df.attrs["regions_covered"]` and `df.attrs["country_count"]` are surfaced in `SipriMilexIngestResult`. SIPRI Yearbook Ch.7's `df.attrs["pdf_pages_total"]` and `df.attrs["snapshot_year"]` are surfaced in `SipriYearbookCh7IngestResult` (same pattern, different fields).

5. **No cross-validate-with-other-source output.** SIPRI milex is the 2nd source for the `international_peace` category (cross-validating UCDP). SIPRI Yearbook Ch.7 is the **only** source for the `nuclear` category (FAS is a cross-validation source for the manual-review queue, not a Stage 2 indicator source). The Stage 5 score module's confidence formula will have a "no cross-validation available" penalty for the `nuclear` category — handled in Stage 5, not Stage 2.

### Source-of-truth principle (the prompt's specific instruction)

The prompt's instruction: "If the test fixture count and the design catalog spec disagree (e.g., 3 vs 4 indicators), the design doc is the source of truth; the test must match." For SIPRI Yearbook Ch.7, the design says **3** indicators; the test fixture must have **3** indicator columns. The test-builder does not negotiate this; the developer does not negotiate this. The 3 indicators in §3.4 are the contract.

### `df.attrs` survival (the UCDP-style extras pattern)

The `df.attrs["events_total"]` and `df.attrs["events_filtered"]` pattern from UCDP applies to SIPRI Yearbook Ch.7 as `df.attrs["pdf_pages_total"]` and `df.attrs["snapshot_year"]`. The orchestrator surfaces both in `SipriYearbookCh7IngestResult`. The end-to-end test asserts both fields. The parquet writer strips any non-JSON-serializable keys (if present) but preserves the JSON-serializable pdf_pages_total and snapshot_year.

### PDF-specific lesson: test fixture is the source of truth for the parser

The PDF parser is the first PDF source in the pipeline. The test fixture (`tests/fixtures/sipri_yearbook_ch7/sample.pdf`) is the canonical example of "what the parser must accept". If the test-builder writes the fixture with `reportlab` and the parser fails to extract it, the developer **fixes the parser**, not the fixture. The fixture is the contract; the parser is the implementation. This is the same source-of-truth principle as the V-Dem / WGI fixture convention, applied to the new PDF medium.

---

## Open questions for the developer

1. **SIPRI Yearbook Ch.7 attribution text (the major open question).** The current [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `sipri_yearbook_ch7` cites the Yearbook 2024. The design proposes the attribution text:
   > Stockholm International Peace Research Institute. 2024. "World Nuclear Forces." In SIPRI Yearbook 2024: Armaments, Disarmament and International Security. Oxford University Press.
   > Short-form: "SIPRI Yearbook 2024 Ch.7 (Stockholm International Peace Research Institute 2024)."

   The doc text matches the constant in §3.3 byte-for-byte. The developer should **verify the doc text matches the constant** before implementing; if there is any drift (e.g., the doc was updated since the design was written), the developer updates either the doc or the constant to make them match, in the same commit. The drift-guard test (`test_sipri_yearbook_ch7_attribution_matches_attributions_doc`) will fail if the constant and the doc disagree.

2. **Should the indicator count be 2, 3, or 4?** The design locks in 3 indicators (total_inventory, deployed, retired). The 4th and 5th candidates are `stored` (central storage) and `stockpile_total` (deployed + stored). If the user wants all 5, the catalog is a 2-row extension. The 3-indicator choice is the prototype default; the user may want to widen it. The 2-indicator minimum (total_inventory and deployed) is a possible narrowing if the user wants an even smaller catalog.

3. **PDF parser library choice.** The design uses `pdfplumber`. Alternatives are `pypdf` (lower-level, less robust for table extraction), `PyMuPDF` (faster but requires a native dependency), and `tabula-py` (wraps the Java `tabula` library, not pure Python). `pdfplumber` is the recommended choice (pure Python, robust for Adobe InDesign-rendered tables, no native dependency). The developer confirms the choice with the user before adding the dependency.

4. **Test fixture generation tool.** The design uses `reportlab` to write the test fixture. Alternative is `fpdf2` (a simpler alternative). `reportlab` is the recommended choice (more mature, better table support). The developer confirms the choice with the user before adding the dependency.

5. **PDF fixture granularity.** The design says 5 countries × 1 year × 3 indicators. The WGI fixture is 5 × 2 × 6 = 60 cells; the UCDP fixture is 5 × 2 × 20 events → 60 obs rows; the V-Dem fixture is 10 rows × 22 indicators = 220 obs rows; the SIPRI milex fixture is 5 × 2 × 4 = 40 obs cells. The SIPRI Yearbook Ch.7 fixture is 5 × 1 × 3 = **15 obs cells + 3 sentinel cells (1 `–` + 1 `..` + 1 `c. <num> [letter]`) + 1 aggregate row (filtered out)**. Total file size: ~5–10 KB. The catalog says 3 indicators, so the fixture covers 3 indicators. The test-builder does not negotiate the indicator count — the design says 3 and the fixture matches.

6. **`c. <num> [letter]` annotation format.** The design assumes the annotation is **inline** in the cell (e.g., `"c. 24 j"` on a single line). The live YB24 PDF has the annotation in the cell text. The developer should verify the live PDF's annotation format matches the design's assumption; if a future Yearbook edition moves the annotation to a separate line (e.g., `"c. 24"` on one line, `"j"` on the next), the parser's regex may need to handle multi-line cells. The test fixture uses the inline form to keep the parser simple.

7. **Year of first nuclear test column.** The design says the `Year of first nuclear test` column is **NOT** extracted as an indicator. The user may want to add it as a derived indicator (e.g., `years_since_first_test` as a measure of arsenal maturity). The catalog is a 1-row extension if needed. The 3-indicator choice is the prototype default.

8. **Coverage year fix.** The doc says "annual" for the Yearbook Ch.7 coverage. The actual data is the January 2024 snapshot. **The doc is already correct; no fix needed.** The `_RAW_PDF_NAME = "YB24 07 WNF.pdf"` and the `version="YB2024 (data: January 2024)"` are the version-locked identifiers.

9. **`pdf_path` discoverability.** The current design hard-codes the version-locked filename `YB24 07 WNF.pdf` in `_RAW_PDF_NAME`. If a future release changes the filename (e.g., `YB25 07 WNF.pdf`), the developer updates the constant. The Stage 2 adapter does not auto-discover the latest version (the user downloads via the project's `curl` workflow and stages the file). The drift-guard test `test_default_path_helpers` asserts the path; a future release update is a 1-line constant change.

10. **Country name encoding.** The PDF uses UTF-8 encoded display names (e.g., the live PDF includes "Türkiye" in the per-country text, but the Table 7.1 itself uses ASCII names like "United States", "Russia", "United Kingdom", "France", "China", "India", "Pakistan", "North Korea", "Israel"). The `pdfplumber` library preserves the UTF-8. The wide frame's `country` column carries the UTF-8 display name verbatim. Stage 3 must handle UTF-8 display names; the `country_aliases.csv` table should store UTF-8 names. This is a Stage 3 deliverable; Stage 2 just passes the names through.

11. **PDF metadata preservation.** The PDF's metadata (`Author: Kristensen, H. M. and Korda, M./SIPRI`, `Title: SIPRI Yearbook 2024, World nuclear forces 2023`) is preserved in the PDF's XMP stream. The Stage 2 PDF parser does NOT extract the metadata as a separate indicator; the metadata is for the LLM rationale (Stage 9–10) and the manual-review context, not for the prototype's indicator values. The `pdf_pages_total` and `snapshot_year` are the only metadata fields surfaced in the result.
