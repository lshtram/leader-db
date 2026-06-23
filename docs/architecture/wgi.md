# WGI Architecture Design — Stage 2 Adapter for World Bank Worldwide Governance Indicators

> **Status:** architecture design, ready for test-builder and developer.
> **Phase:** C.3 (data acquisition, third adapter, after V-Dem and WDI).
> **Target source key:** `world_bank_wgi`.
> **Wiring in:** `src/leaders_db/ingest/__init__.py::STAGE2_ADAPTERS`.
> **Source verdict:** ✅ `vetted_ok` per [`docs/sources/vetting/report.md`](../sources/vetting/report.md) §3.5.
> **Liveness verified:** 2026-06-17 — `https://www.worldbank.org/content/dam/sites/govindicators/doc/wgidataset.xlsx` returns HTTP 200 with `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `Last-Modified: Tue, 14 Nov 2023 19:05:37 GMT`, downloaded xlsx is 2,106,620 bytes (2.1 MB).

This document is the design contract for the WGI Stage 2 adapter. The test-builder writes tests against the public surface in §2.3; the developer implements against the same surface. The catalog spec in §2.4 is the only place where WGI's indicator list is decided.

---

## 2.1 — Source contract (what WGI gives us, what we extract)

### Canonical URL and file format

| Field | Value |
|---|---|
| Canonical URL | `https://www.worldbank.org/content/dam/sites/govindicators/doc/wgidataset.xlsx` |
| Format | Excel xlsx (one file, multi-sheet) |
| Size | ~2.1 MB (last verified 2026-06-17) |
| Auth | none (public, free, no API key) |
| Release cadence | annual; the current release is "The Worldwide Governance Indicators, 2023 Update" (per the xlsx's `Introduction` sheet cell F2) |
| Local storage | `data/raw/world_bank_wgi/wgidataset.xlsx`; `metadata.json` alongside |

> **Why xlsx, not API?** WGI also exposes a JSON API at `https://api.worldbank.org/v2/sources/3/` (per [`docs/sources/vetting/report.md`](../sources/vetting/report.md) §6 caveats). For the prototype, the xlsx is the canonical input: the read pattern is "download one xlsx once a year, slice it by indicator × year" — no per-indicator HTTP API, no pagination, no rate limiting. The WGI xlsx is **structurally closer to V-Dem** (one local file, no network) than to WDI (per-indicator HTTP, JSON cache). This is the reason the WGI module splits into 3 files (V-Dem pattern), not 4 (WDI pattern).
>
> The WGI API is left as a fallback for users who want a live single-cell query without downloading the whole bundle. The Stage 2 adapter does not need it.

### xlsx structure (verified live 2026-06-17)

The xlsx is a **multi-sheet workbook with 7 sheets**:

| Sheet name | Purpose | Rows | Cols |
|---|---|---|---|
| `Introduction` | Title page ("The Worldwide Governance Indicators, 2023 Update" / "Aggregate Governance Indicators 1996-2022") | 4 | 6 |
| `VoiceandAccountability` | One row per country; 6 stats × 24 years | 229 | 146 |
| `Political StabilityNoViolence` | (same shape) | 229 | 146 |
| `GovernmentEffectiveness` | (same shape) | 229 | 146 |
| `RegulatoryQuality` | (same shape) | 229 | 146 |
| `RuleofLaw` | (same shape) | 229 | 146 |
| `ControlofCorruption` | (same shape) | 229 | 146 |

**Per-indicator sheet layout** (e.g. `VoiceandAccountability`):

```
Row  1: <indicator name>            e.g. "Voice and Accountability"
Row  2: <long description sentence> e.g. "Reflects perceptions of the extent to which a country's citizens are able to participate in selecting their government, as well as freedom of expression, freedom of association, and a free media."
Row  3: (blank)
Row  4: "Legend"
Row  5: "Estimate" | "Estimate of governance (ranges from approximately -2.5 (weak) to 2.5 (strong) governance performance)"
Row  6: "StdErr"    | "Standard error reflects variability around the point estimate of governance."
Row  7: "NumSrc"    | "Number of data sources on which estimate is based"
Row  8: "Rank"      | "Percentile rank among all countries (ranges from 0 (lowest) to 100 (highest) rank)"
Row  9: "Lower"     | "Lower bound of 90% confidence interval for governance, in percentile rank terms"
Row 10: "Upper"     | "Upper bound of 90% confidence interval for governance, in percentile rank terms"
Row 11: (blank)
Row 12: <disclaimer paragraph>
Row 13: (blank)
Row 14: <year for each col, repeated 6 times per year>  e.g. 1996,1996,...,1998,1998,...,2022,2022
Row 15: <stat type for each col>  e.g. "Country/Territory","Code","Estimate","StdErr","NumSrc","Rank","Lower","Upper","Estimate","StdErr",...
Row 16..229: country data — 214 countries
```

**Column layout per country row:**

- Col 1: `Country/Territory` (country name string, e.g. `"Mexico"`)
- Col 2: `Code` (3-letter ISO3-like code, e.g. `"MEX"`)
- Cols 3..146: **6 stats × 24 years = 144 columns**, in the repeating pattern `Estimate, StdErr, NumSrc, Rank, Lower, Upper` for each year.

**Years present** (24 distinct years, verified live):

```
1996, 1998, 2000, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009,
2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020,
2021, 2022
```

Note: **biennial 1996–2002 (5 measurements), annual 2003–2022 (20 measurements) = 24 years total.** The data ends at **2022** in the current release ("2023 Update"), not 2023 — the year in the title is the release year, not the data year. This is a slight drift from the `1996–2023` listed in [`docs/sources/vetting/report.md`](../sources/vetting/report.md) §3.5 and [`docs/sources/attributions.md`](../sources/attributions.md) §1; the developer will correct the Coverage field to "1996–2022" in the same commit as the adapter lands.

**Missing-data convention:** WGI uses the Excel literal string **`"#N/A"`** (with the slash, no spaces) in cells where the country-year is not measured. Live probe found 966 `#N/A` cells in just the `VoiceandAccountability` sheet (out of 214 countries × 144 stats × 6 indicator sheets = ~185,000 cells; ~0.5% are missing). There are **no empty cells, no `-999` sentinels, no pandas NaN** in the WGI xlsx. The Stage 2 adapter must coerce `#N/A` to `None` for the `source_observations.normalized_value` column. The `raw_value` audit trail preserves the literal `"#N/A"` string per the V-Dem/WDI convention.

**Country code conventions:**

- **214 country rows** (rows 16–229 of each indicator sheet).
- The codes are mostly ISO3 (`MEX`, `USA`, `SWE`, `IND`, `NGA`, `CHN`, `GBR`, `DEU`, `FRA`, `JPN`, `BRA`, `RUS`, `CAN`, `AUS`, etc.) with a few exceptions:
  - `XKX` for Kosovo (UN-assigned code; treated as a real country).
  - `ADO` for Andorra (not a real ISO3; Andorra's real ISO3 is `AND` — but WGI uses `ADO`).
  - `ANT` for "Netherlands Antilles (former)" (historical, pre-2010 entity — kept for backward compatibility).
  - `WBG` for West Bank and Gaza.
  - `ZAR` for "Congo, Dem. Rep." (real ISO3 is `COD`).
  - `YEM` for "Yemen, Rep." (matches ISO3).
- **No aggregate codes.** Unlike WDI (which returns ~79 region aggregates like `AFE`, `ARB`, `WLD`), the WGI xlsx is **country-only** — no denylist needed. The WGI adapter does **not** maintain an aggregate-code denylist (the WDI constant `_WDI_AGGREGATE_ISO3_CODES` is WDI-specific and does not apply to WGI).
- The country name column uses display names (e.g. `"Congo, Dem. Rep."`, `"Yemen, Rep."`, `"West Bank and Gaza"`) which are Stage 3's problem to normalize to the canonical `countries.country_name` field. The Stage 2 adapter only writes the raw ISO3 to `source_row_reference` and lets Stage 3 resolve it.

### What we extract vs what we defer

**Extract (6 indicators × 1 stat × 24 years = 144 cells per country):**

- The 6 governance indicators, **Estimate column only**.
- All 24 years (1996–2022) are kept in the wide frame; the year filter is applied at the orchestrator level.
- All 214 country rows (no filter).

**Defer to a future iteration (kept in the xlsx but not written to `source_observations`):**

- The 5 non-Estimate statistics per year (`StdErr`, `NumSrc`, `Rank`, `Lower`, `Upper`) — these support confidence intervals for the WGI Estimate, but the prototype's confidence formula (REQ-CONF-001) does not need per-source confidence intervals at Stage 2; the per-source authority score is already captured in `data/metadata/source_authority_table.csv`. The Stage 11 confidence module can read the WGI `StdErr` directly from the xlsx if it ever needs to widen to confidence intervals.
- Percentile ranks (`Rank`, `Lower`, `Upper`) — these are derived from the Estimate by the World Bank and can be reconstructed.
- Indicator-by-indicator sheet `Description` (row 2) and `Legend` (rows 4–10) — metadata for the report, not for scoring.

This narrowing is **user decision needed** (see §"Open questions" below): the user may want `StdErr` extracted to support a future "WGI confidence interval" feature. The catalog is the single source of truth; adding `StdErr` later is a 6-row addition.

### Indicator catalog scope (this design)

For the prototype, all 6 WGI indicators are extracted, feeding the **2 rating categories** WGI serves per the source-vetting report:

1. **`effectiveness`** (governance) — 5 indicators: Voice and Accountability, Political Stability, Government Effectiveness, Regulatory Quality, Rule of Law.
2. **`integrity`** (corruption cross-validation) — 1 indicator: Control of Corruption. WGI's `Control of Corruption` is also listed in [`docs/sources/vetting/report.md`](../sources/vetting/report.md) §3.6 as a cross-validation source for the integrity / corruption category (alongside TI CPI and V-Dem corruption).

The full per-indicator spec (sheet name → canonical `variable_name`, scale, unit, category, one-line description) is in §2.4. The catalog CSV the developer will author lives at `src/leaders_db/ingest/catalogs/wgi.csv` (sibling to the adapter modules, per Phase C convention #1).

### Integration with downstream schema

None of the WGI indicators populate the `country_years` table directly (those columns are reserved for WDI's `population`, `gdp_current_usd`, `gdp_per_capita` — see [`docs/architecture/wdi.md`](wdi.md) §2.1). All 6 WGI indicators live in `source_observations` and are consumed by the Stage 5 score modules for `effectiveness` and `integrity`.

### License

The World Bank distributes its datasets (including WGI) under **Creative Commons Attribution 4.0 International (CC BY 4.0)** per the [Terms of Use for Datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) (last updated 2018-03-23, verified live 2026-06-17). The terms require attribution in the form:

> The World Bank: Dataset name: Data source (if known).

The current `docs/sources/attributions.md` entry for `world_bank_wgi` says "World Bank Open Data license" — a slight drift from the canonical CC BY 4.0 wording. The developer updates the License field in the same commit as the adapter lands (mirroring the WDI license clarification that was done at WDI implementation time; see [`docs/architecture/wdi.md`](wdi.md) §2.1 "Note for the developer" and §2.8).

The short-form attribution text that goes into the Stage 15 report is unchanged: `"World Bank WGI (World Bank 2023)."` The long-form citation that the code carries (per the V-Dem pattern in `VDEM_ATTRIBUTION` and the WDI pattern in `WDI_ATTRIBUTION`) is the full bibliographic citation. See §2.3 for the constant.

### Cited artifacts

- Indicator catalog: `src/leaders_db/ingest/catalogs/wgi.csv` (to be authored from §2.4).
- Per-source `metadata.json`: `data/raw/world_bank_wgi/metadata.json` (to be written when the first successful read happens).
- Attribution: `docs/sources/attributions.md` §1 entry for `world_bank_wgi`.

---

## 2.2 — Module structure (V-Dem-style, 3 modules)

WGI is structurally closer to V-Dem (one local file, no network) than to WDI (per-indicator HTTP, JSON cache). The WGI module splits into **3 sibling files** under `src/leaders_db/ingest/`, each under the 400-line convention from `docs/process/coding-guidelines.md`:

| File | Responsibility | Approx LoC target |
|---|---|---|
| `wgi.py` | Public orchestrator: `WGIIngestResult` Pydantic model, `attribution()`, `ingest_wgi()` entrypoint. Re-exports `WGI_ATTRIBUTION`, `WGI_SOURCE_KEY`, `IndicatorSpec` from the I/O module. | ~180–220 |
| `wgi_io.py` | Catalog, xlsx read, long-to-wide pivot, parquet write, parquet metadata attachment. Owns `WGI_ATTRIBUTION`, `WGI_SOURCE_KEY`, `IndicatorSpec`, and the `_DEFAULT_CATALOG_PATH` constant. | ~280–340 |
| `wgi_db.py` | `sources` upsert, `source_observations` write, missing-value coercion, run manifest. | ~280–340 |

**No `wgi_http.py` because WGI has no HTTP layer.** The WGI read is purely local-file → pandas. The WDI 4-module split is WDI-specific; WGI follows the V-Dem 3-module split.

The split rationale is identical to V-Dem: `wgi_io` owns the data-lake and the I/O contract; `wgi_db` owns the DB contract; `wgi` is the orchestrator that wires them together. Constants live in `wgi_io` (lowest level) to break the import cycle, and are re-exported by `wgi.py` for the public surface.

### Read pattern — chosen approach: **per-sheet, per-year long-format extraction → wide pivot**

The WGI xlsx is not natively long-format. The read function performs the long-to-wide reshape:

1. **Open the xlsx once** with `openpyxl.load_workbook(..., read_only=True, data_only=True)`. The xlsx is 2.1 MB and fits in memory; the read orchestrator never holds the whole xlsx at once because the per-sheet iteration is row-by-row (streaming via `read_only=True`).
2. **For each catalog indicator** (i.e. for each sheet name in the catalog's `raw_column` field):
   - Open that sheet.
   - Read **row 14** to get the year-to-column-position mapping (`{year: [list of 6 col indices]}`).
   - Read **row 15** to get the stat-type-to-column-position mapping (`{stat_name: col_index}`).
   - For each country row (rows 16..229):
     - Extract `Country/Territory` (col 1), `Code` (col 2), and the `Estimate` cell at the year column for the requested year.
     - Coerce the cell: `float` if numeric, `None` if `"#N/A"`.
3. **Concatenate** the per-indicator long frames into one long frame with columns `(iso3, year, indicator_code, value)`.
4. **Pivot** to wide format (one row per `(iso3, year)`, one column per `variable_name`). The same shape as the WDI/V-Dem wide frame.
5. **Filter** by year if `year=` is passed (or keep all years if `year=None`).

The Stage 2 → Stage 11 contract: `confidence` is left `NULL` on every row; Stage 11 fills it.

---

## 2.3 — Public surface (exact function signatures)

The test-builder writes against these signatures; the developer implements against these signatures. The names and types are the contract; the docstrings below describe the contract for both audiences.

### Constants (in `wgi_io.py`, re-exported by `wgi.py`)

```python
WGI_SOURCE_KEY: str = "world_bank_wgi"
```

The single source key used everywhere in the data lake, the CLI dispatch, and the test imports. Matches the `data/raw/<key>/` folder name and the `--source` CLI flag.

```python
WGI_ATTRIBUTION: str = (
    "World Bank. 2023. Worldwide Governance Indicators. "
    "Washington, D.C.: The World Bank. https://info.worldbank.org/governance/wgi/ "
    "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
)
```

The exact citation text. Lives in `wgi_io` to break the import cycle. The canonical long-form lives in `docs/sources/attributions.md`; the drift-guard test (§2.5) enforces byte-for-byte consistency. The year is `2023` (the release year) to match the existing short-form attribution `"World Bank WGI (World Bank 2023)."` in [`docs/sources/attributions.md`](../sources/attributions.md) §1; the data covers 1996–2022 but the citation's `2023` refers to the World Bank's release year, not the latest data year.

```python
#: Map of variable_name -> xlsx sheet name. The catalog's
#: ``raw_column`` column holds these sheet names verbatim. The read
#: function looks up the sheet name from the catalog row, not from
#: the variable_name, so the catalog remains the source of truth.
_INDICATOR_SHEET_NAMES: dict[str, str] = {
    "wgi_voice_and_accountability": "VoiceandAccountability",
    "wgi_political_stability": "Political StabilityNoViolence",
    "wgi_government_effectiveness": "GovernmentEffectiveness",
    "wgi_regulatory_quality": "RegulatoryQuality",
    "wgi_rule_of_law": "RuleofLaw",
    "wgi_control_of_corruption": "ControlofCorruption",
}
```

This is a private constant (single underscore). The catalog CSV is the public source of truth; this dict is the in-code mirror for fast lookup.

### Indicator catalog (in `wgi_io.py`)

```python
@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the WGI indicator catalog.

    The V-Dem / WDI ``IndicatorSpec`` shape is reused verbatim: every
    Stage 2 adapter resolves its raw column from this dataclass so the
    score modules in Stage 9-10 can normalize and direct indicators
    consistently across sources.
    """
    variable_name: str         # canonical, e.g. "wgi_voice_and_accountability"
    raw_column: str            # the xlsx sheet name, e.g. "VoiceandAccountability"
    rating_category: str       # "effectiveness" or "integrity"
    raw_scale: str             # "z_score" (WGI Estimate is a std-normal-like z-score)
    normalized_scale_target: str  # "0-1" per the catalog convention
    higher_is_better: bool     # True for all 6 WGI indicators
    unit: str                  # "z_score" (or "std_normal") — see §2.4
    description: str           # one-line human description for audit / docs

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "IndicatorSpec": ...
```

```python
def load_indicator_catalog(catalog_path: Path | None = None) -> list[IndicatorSpec]:
    """Load the WGI indicator catalog from ``catalogs/wgi.csv``.

    Mirrors the V-Dem / WDI loaders: handles the leading ``#`` comment
    block, drops comment-only lines, validates the required column set,
    and returns one ``IndicatorSpec`` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing.
    """
```

### Read (in `wgi_io.py`)

```python
def read_wgi(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read WGI from the xlsx and pivot to wide format (one row per country per year).

    Steps:

    1. Load the catalog.
    2. Open the xlsx at ``xlsx_path`` (default: ``data/raw/world_bank_wgi/wgidataset.xlsx``).
    3. For each catalog row (one per indicator):
       a. Open the sheet named in ``raw_column``.
       b. Read row 14 (year row) and row 15 (stat row) to build the
          year-to-column-position map. Identify the column position of
          the ``Estimate`` cell for each year.
       c. For each country row (rows 16..229): extract ``Code`` (col 2)
          and the ``Estimate`` cell for the requested year(s). Coerce
          ``"#N/A"`` -> ``None``; coerce numeric cells to ``float``.
       d. Append (iso3, year, indicator_code, value) rows to a long frame.
    4. Concatenate per-indicator long frames.
    5. Pivot to wide format (one row per (iso3, year), one column per
       catalog ``variable_name``).
    6. Coerce the ``year`` column to ``int`` and the indicator columns
       to ``float`` (NaN for absent values; see §2.6 for the missing-value
       story).

    Args:
        year: filter to a single year (e.g. ``2022``). Default: all years
            present in the xlsx (1996–2022, 24 distinct years).
        xlsx_path: override the input xlsx. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.

    Returns:
        A pandas DataFrame with columns ``iso3``, ``year``, then one
        column per catalog indicator (named with the ``variable_name``).
        ``year`` is integer. Indicator columns are float (``NaN`` = missing).
        WGI does not return aggregate codes, so the returned DataFrame
        contains **all 214 country rows** (no denylist needed).

    Raises:
        FileNotFoundError: if the xlsx is missing.
        KeyError: if a catalog ``raw_column`` sheet name is absent from
            the xlsx (i.e. the WGI release dropped or renamed a sheet).
    """
```

### Path helpers (in `wgi_io.py`)

```python
def default_xlsx_path() -> Path:
    """Return the conventional WGI xlsx path inside the data lake.

    Resolves to ``<project_root>/data/raw/world_bank_wgi/wgidataset.xlsx``.
    Raises ``FileNotFoundError`` if the file is missing (the adapter
    expects the user to have downloaded the xlsx via the project's
    download workflow first).
    """
```

```python
def default_processed_parquet_path() -> Path:
    """Return the conventional WGI narrow parquet path.

    Creates the ``data/processed/world_bank_wgi/`` directory if missing.
    """
```

### Parquet write (in `wgi_io.py`)

```python
def write_wgi_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet` and
    :func:`wdi_io.write_wdi_parquet` (and the
    :func:`vdem_io._attach_parquet_metadata` helper): writes the parquet
    via ``df.to_parquet``, then re-writes the file with the WGI
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite — if pyarrow fails,
    the data parquet is still valid and a warning is logged.
    """
```

### DB writes (in `wgi_db.py`)

```python
def register_wgi_source(session: Session) -> int:
    """Upsert the WGI source row into the ``sources`` table.

    Keyed by ``(source_name='World Bank WGI', version='2023')``.
    Idempotent: returns the same ``sources.id`` on every call. Reads
    the bundle's ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source` and WDI's
    :func:`wdi_db.register_wdi_source`).
    """
```

```python
def write_wgi_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    Same shape as V-Dem's :func:`vdem_db.write_vdem_observations` and
    WDI's :func:`wdi_db.write_wdi_observations`:

    - ``country_id`` is left ``NULL``; Stage 3 (country match) fills it.
    - ``source_row_reference`` carries the ISO3 prefixed with
      ``"wgi:"`` (e.g. ``"wgi:MEX"``) so Stage 3 can resolve it.
    - ``raw_value`` preserves the original cell: the float as a
      string for numeric cells, or the literal ``"#N/A"`` for missing
      cells (per the V-Dem-style audit trail).
    - ``normalized_value`` is the float, or ``None`` if the cell is
      ``"#N/A"`` or empty.
    - Idempotent: deletes existing rows for the requested years
      (from the frame) before inserting. Years outside the frame are
      untouched.

    Returns the number of ``source_observations`` rows inserted.
    """
```

### Run manifest (in `wgi_db.py`)

```python
def write_wgi_run_manifest(
    result,  # WGIIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest is the audit trail for ``processed/``: it records
    ``source_id``, the parquet path, the observation row count, the
    countries count, the years, the indicator count, the catalog path,
    and the attribution. Written every run (not best-effort) so Stage
    15 reports can find the attribution without re-reading the
    parquet metadata.
    """
```

### Orchestrator and Pydantic result (in `wgi.py`)

```python
class WGIIngestResult(BaseModel):
    """Summary of a single ``ingest_wgi`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads these
    fields to print the end-of-run summary, and the manifest writer in
    :mod:`wgi_db` consumes the same fields. Same shape as V-Dem's
    :class:`vdem.IngestResult` and WDI's :class:`wdi.WDIIngestResult`
    for consistency.
    """
    source_id: int = Field(..., ge=1)
    parquet_path: Path
    observation_rows: int = Field(..., ge=0)
    countries: int = Field(..., ge=0)
    years: tuple[int, ...]
    indicators: int = Field(..., ge=0)

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]: ...

    @property
    def attribution(self) -> str:
        """The WGI attribution text (Always-On Rule #15)."""
        return WGI_ATTRIBUTION
```

> **Note on the WDI IngestResult's extra fields.** The WDI result carries
> ``indicators_cached`` and ``indicators_fetched`` because WDI has an HTTP
> layer with a per-indicator cache. WGI has no HTTP layer — the xlsx is
> the cache, and the read is a single local-file read. The WGI result
> does **not** carry those fields; this is intentional and matches the
> V-Dem result shape. The end-to-end test (§2.5) asserts the fields
> that **are** present, not the fields that are absent.

```python
def attribution() -> str:
    """Return the WGI attribution block for public output (Rule #15)."""
```

```python
def ingest_wgi(
    *,
    year: int | None = None,
    xlsx_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> WGIIngestResult:
    """Run Stage 2 for WGI end-to-end.

    Steps:

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_wgi`.
    3. Write the narrow parquet via :func:`write_wgi_parquet`.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Build the :class:`WGIIngestResult` and write the run manifest.
    6. Return the result.

    The function is the single public entry point — both the CLI
    command ``leaders-db ingest-source --source world_bank_wgi`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the ``LEADERSDB_PROJECT_ROOT``
    env var. No explicit ``database_url`` kwarg is needed.
    """
```

### `__all__` (in `wgi.py`)

```python
__all__ = [
    "WGI_ATTRIBUTION",
    "WGI_SOURCE_KEY",
    "IndicatorSpec",
    "WGIIngestResult",
    "attribution",
    "ingest_wgi",
    "register_wgi_source",
    "write_wgi_observations",
    "write_wgi_run_manifest",
]
```

The DB helpers (`register_wgi_source`, `write_wgi_observations`, `write_wgi_run_manifest`) are re-exported so the test-builder's tests can call them through the orchestrator module — same pattern as the WDI test surface (`from leaders_db.ingest import wdi; wdi.register_wdi_source(...)`).

---

## 2.4 — Indicator catalog (the contract for the test fixture)

The test-builder will author `tests/fixtures/world_bank_wgi/sample.xlsx` based on this spec. The developer will author `src/leaders_db/ingest/catalogs/wgi.csv` from this spec. The two artifacts must agree on the indicator list.

### Catalog format

Same CSV format as `vdem.csv` and `wdi.csv` (Phase C convention #1). The 8 required columns are exactly the V-Dem/WDI 8; the test fixture mirrors them.

```
variable_name,raw_column,rating_category,raw_scale,normalized_scale_target,higher_is_better,unit,description
```

### Indicator list (6 indicators across 2 categories)

| # | Sheet name (`raw_column`) | `variable_name` | Category | Scale | Unit | Direction | Why it matters |
|---|---|---|---|---|---|---|---|
| 1 | `VoiceandAccountability` | `wgi_voice_and_accountability` | `effectiveness` | `z_score` | `z_score` | `True` | Extent to which citizens can participate in selecting their government, plus freedom of expression, association, and free media. |
| 2 | `Political StabilityNoViolence` | `wgi_political_stability` | `effectiveness` | `z_score` | `z_score` | `True` | Perceptions of the likelihood of political instability and/or politically-motivated violence, including terrorism. |
| 3 | `GovernmentEffectiveness` | `wgi_government_effectiveness` | `effectiveness` | `z_score` | `z_score` | `True` | Quality of public services, civil service, policy formulation and implementation, and credibility of government commitment. |
| 4 | `RegulatoryQuality` | `wgi_regulatory_quality` | `effectiveness` | `z_score` | `z_score` | `True` | Ability of government to formulate and implement sound policies and regulations that permit and promote private-sector development. |
| 5 | `RuleofLaw` | `wgi_rule_of_law` | `effectiveness` | `z_score` | `z_score` | `True` | Extent to which agents have confidence in and abide by the rules of society (property rights, police, courts). |
| 6 | `ControlofCorruption` | `wgi_control_of_corruption` | `integrity` | `z_score` | `z_score` | `True` | Extent to which public power is exercised for private gain, including petty and grand corruption. Cross-validates TI CPI for the integrity category. |

> **Why `integrity` for `Control of Corruption` only?** Per [`docs/sources/vetting/report.md`](../sources/vetting/report.md) §3.5–§3.6, the WGI bundle as a whole is classified under "Effectiveness / governance", but the `Control of Corruption` indicator is also listed separately as a cross-validation source for the "Integrity / corruption" category (alongside TI CPI and V-Dem corruption). One indicator → one category in the catalog (matching the V-Dem convention), so `Control of Corruption` lives under `integrity`; the Stage 5 score module for `effectiveness` can still consult the indicator via the `variable_name` if it wants to use the corruption signal as an inverse proxy for governance quality. The other 5 indicators stay in `effectiveness`.

> **Why `higher_is_better=True` for all 6?** WGI scores are z-score-like governance performance estimates on an approximately -2.5 (weak) to 2.5 (strong) scale. Higher Estimate = better governance. The `raw_scale = "z_score"` tag captures the scale; `unit = "z_score"` is documentation for Stage 5 normalization. The `normalized_scale_target = "0-1"` is the Stage 5 contract (linear remap of the z-score to 0–1).

> **Why not extract `StdErr`?** Deferred. The Stage 2 → Stage 11 contract puts `confidence` in the score module, not in the raw data. Adding `StdErr` is a 6-row catalog extension (one row per indicator with `raw_column = "StdErr"` and a different sheet-cell lookup). The developer does not need to wire it now.

### `normalized_scale_target`

For the prototype, all 6 indicators normalize to `0-1` (matching V-Dem and WDI). The actual normalization is the Stage 5 score module's job, not Stage 2's. Stage 2 only writes the raw value to `source_observations.normalized_value` and preserves the scale in the catalog. The `normalized_scale_target` column is documentation for Stage 5, not a transformation.

### `unit` convention

`unit = "z_score"` for all 6 indicators. The WGI Estimate is a z-score-like number on the standard normal scale; it is **not** literally a z-score (WGI uses Bayesian aggregation, not a sample mean) but the interpretation is the same. Alternative: `"std_normal"`. The developer picks one and uses it consistently; the WDI catalog uses neither (it uses `persons`, `USD`, etc. — concrete units), but the WGI catalog has no concrete unit since the Estimate is dimensionless. `"z_score"` is the recommended default.

### Test fixture shape (5 countries × 2 years × 6 indicators)

The test-builder's fixture `tests/fixtures/world_bank_wgi/sample.xlsx` is a **real-format WGI xlsx** authored with openpyxl (committed under `tests/fixtures/world_bank_wgi/`). Shape:

- 7 sheets: `Introduction` (4-row text), plus the 6 indicator sheets.
- Each indicator sheet has the canonical WGI layout: row 1 (indicator name), row 2 (description), row 4 ("Legend"), rows 5–10 (legend), row 12 (disclaimer), row 14 (years), row 15 (stat types), row 16+ (country data).
- 5 countries: MEX, USA, SWE, IND, NGA (matching the V-Dem / WDI test fixtures).
- 2 years: 2021, 2022 (the most recent two years; ensures at least one WGI Estimate is real, not `#N/A`).
- For 1 of the 5 countries (e.g. MEX), include a `#N/A` cell in one of the 12 (year, indicator) cells to exercise the missing-value coercion. The other 4 countries have all 12 cells filled.
- Real WGI data for the non-`#N/A` cells (no invented values). The developer pulls these from the live xlsx at `data/raw/world_bank_wgi/wgidataset.xlsx` if the file is on disk; otherwise the test-builder can use any plausible real value from the WGI 2023 Update release.

Total cells in the fixture data: 5 countries × 2 years × 6 indicators = **60 Estimate cells** + 4 country rows × 12 non-`#N/A` cells + 1 `#N/A` cell. The read function returns a wide DataFrame of 5 × 2 = 10 rows × 8 columns (`iso3`, `year`, 6 indicator columns). The orchestrator writes 10 × 6 = **60 `source_observations` rows** when reading the full fixture (no year filter) and 5 × 6 = **30 rows** when filtering to `year=2022`.

---

## 2.5 — Test plan (what the test-builder writes)

The test plan covers the 5 Phase C convention #5 categories (catalog, read, write+DB, idempotency, attribution) plus the orchestrator and CLI. Every test has a defined fixture, an assertion, and a 1-line description. The V-Dem / WDI test files are the template.

### Catalog (Phase C convention #5a)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_load_indicator_catalog_returns_6_specs` | The checked-in catalog has 6 indicators (matches §2.4 spec). | `wgi_catalog_path` |
| `test_load_indicator_catalog_required_columns` | The 8 required CSV columns are present; the `rating_category` set is exactly `{effectiveness, integrity}`. | same |
| `test_load_indicator_catalog_missing_file` | Missing catalog raises `FileNotFoundError`, not a silent empty list. | `tmp_path` |
| `test_indicator_spec_from_csv_row` | `higher_is_better=0`/`=1` round-trips to a real bool (matching V-Dem / WDI). | inline dict |
| `test_catalog_sheet_names_match_wgi_release` | The 6 `raw_column` values are exactly the WGI xlsx sheet names: `VoiceandAccountability`, `Political StabilityNoViolence`, `GovernmentEffectiveness`, `RegulatoryQuality`, `RuleofLaw`, `ControlofCorruption`. | same |

### Read (Phase C convention #5b)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_wgi_returns_full_fixture` | The fixture (5 countries × 2 years × 6 indicators) produces a wide DataFrame: 10 rows, 8 columns (`iso3`, `year`, 6 indicator columns). | `wgi_xlsx_dir` (stages the sample xlsx) |
| `test_read_wgi_filters_to_year` | `year=2022` keeps only the 5 rows for 2022; `set(df["year"]) == {2022}`. | same |
| `test_read_wgi_pivots_long_to_wide` | Each catalog indicator is one column; no row is duplicated; no (country, indicator) cell is in long format. | same |
| `test_read_wgi_handles_na_cells` | The single `#N/A` cell in the fixture becomes `NaN` in the DataFrame; `normalized_value` is `None` in `source_observations`. | same |
| `test_read_wgi_preserves_all_24_years_when_no_filter` | With `year=None` and the real xlsx, the frame contains rows for at least years 1996, 2002, 2010, 2022 (smoke check; full assertion is the live smoke below). | live xlsx |
| `test_read_wgi_missing_xlsx` | Missing xlsx raises `FileNotFoundError` with an actionable message. | `tmp_path` |
| `test_read_wgi_missing_sheet` | If a catalog `raw_column` sheet name is absent from the xlsx, `read_wgi` raises `KeyError`. | missing-sheet-staging helper |
| `test_default_path_helpers` | `default_xlsx_path()` points at `data/raw/world_bank_wgi/wgidataset.xlsx`; `default_processed_parquet_path()` points at `data/processed/world_bank_wgi/wgi_country_year.parquet`. | none |

### Parquet write + DB (Phase C convention #5c)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_wgi_parquet_creates_file` | `write_wgi_parquet(df)` writes a valid parquet under `data/processed/world_bank_wgi/`; round-trip preserves shape and columns. | `wgi_xlsx_dir` |
| `test_write_wgi_parquet_attaches_attribution_metadata` | The parquet's file-level metadata carries `wgi_attribution` (= `WGI_ATTRIBUTION`) and `wgi_source_key` (= `b"world_bank_wgi"`) (Rule #15). | same |
| `test_register_wgi_source_is_idempotent` | Two calls to `register_wgi_source` return the same `sources.id`; the row has `source_name="World Bank WGI"`, `version="2023"`, `source_type="official"`. | `database_url` + `_init_test_db` |
| `test_register_wgi_source_non_destructive_update` | Removing the bundle's `metadata.json` between calls keeps the existing `source_url` and `license_note` (same policy as V-Dem / WDI). | same |
| `test_write_wgi_observations_row_count` | `len(df) * len(specs)` observations are written. With the fixture (10 rows × 6 indicators) the count is 60. | `wgi_xlsx_dir` + `database_url` |
| `test_write_wgi_observations_is_idempotent` | Re-running produces the same count, not 2× the count. | same |
| `test_write_wgi_observations_country_id_is_null` | `country_id` is `None` for every row (Stage 3 fills it); `confidence` is `None` for every row (Stage 11 fills it); `source_row_reference` starts with `"wgi:"`. | same |
| `test_write_wgi_observations_handles_na_cells` | A `#N/A` row becomes `normalized_value=NULL` in SQLite; `raw_value` is the literal string `"#N/A"`. | same |
| `test_default_path_helpers` | (See Read section above — same test, also belongs here.) | — |

### Orchestrator (Phase C convention #5d — end-to-end idempotency)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_ingest_wgi_end_to_end` | `ingest_wgi()` writes the parquet, the sources row, the 60 `source_observations` rows, and the manifest in one call. Result has `countries=5, years=(2021,2022), indicators=6`. | `wgi_xlsx_dir` + `database_url` |
| `test_ingest_wgi_filters_to_year` | `year=2022` keeps 5 countries × 1 year × 6 indicators = 30 observation rows. | same |
| `test_ingest_wgi_is_idempotent` | Two consecutive `ingest_wgi()` calls produce the same `observation_rows` count, the same `source_id`, and the parquet's mtime is the same (no re-write). | same |
| `test_ingest_wgi_result_carries_attribution` | The `WGIIngestResult.attribution` property returns `WGI_ATTRIBUTION` byte-for-byte; `result.attribution == WGI_ATTRIBUTION`. | same |

### Attribution / Rule #15

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_run_manifest` | The manifest is JSON next to the parquet, includes `attribution`, `source_id`, `observation_rows`, `years`, `indicators`. | `isolated_data_lake` |
| `test_attribution_matches_constant` | `wgi.attribution() == WGI_ATTRIBUTION`; contains `"World Bank"`, `"2023"`, `"WGI"`, `"CC BY 4.0"`. | — |
| `test_wgi_attribution_matches_attributions_doc` | `WGI_ATTRIBUTION` is a substring of `docs/sources/attributions.md` (drift guard, same pattern as V-Dem's `test_vdem_attribution_matches_attributions_doc` and WDI's `test_wdi_attribution_matches_attributions_doc`). | project root |

### CLI dispatch

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_stage2_adapters_dispatch_table` | `STAGE2_ADAPTERS["world_bank_wgi"] is wgi.ingest_wgi`; the full key set is unchanged (25 keys including WGI). | — |
| `test_cli_ingest_source_rejects_unknown` | `leaders-db ingest-source --source nope` exits non-zero. | `CliRunner` |

### Live-xlsx smoke (manual, not in pytest)

| Test name | What it asserts | When |
|---|---|---|
| `manual: smoke WGI end-to-end against real xlsx for 2022` | `ingest_wgi(year=2022)` against the real 2.1 MB xlsx returns 214 real countries × 6 indicators = **1,284 `source_observations` rows**; full unfiltered run (year=None) returns 214 × 24 × 6 = **30,816 `source_observations` rows**. | After implementation, manual one-shot, recorded in `docs/testing-guide-stage2-wgi.md` |

The manual smoke is gated on a real on-disk xlsx (already downloaded to `data/raw/world_bank_wgi/wgidataset.xlsx` in Phase B). It is **not** part of `pytest -q` because the read function requires the 2.1 MB xlsx on disk; the test fixture (`tests/fixtures/world_bank_wgi/sample.xlsx`) is a 5-country × 2-year × 6-indicator slice that fits in <50 KB and is what the unit tests use. The unit tests prove the contract; the manual smoke proves the real xlsx still works.

---

## 2.6 — Edge cases & known issues

### No aggregate codes

Unlike WDI (which has 79 aggregate ISO3 codes), the WGI xlsx is **country-only** — no `WLD`, no `AFE`, no `ARB`. The WGI adapter does **not** maintain an aggregate-code denylist. The `_WDI_AGGREGATE_ISO3_CODES` constant from `wdi_io.py` is WDI-specific and is **not** mirrored in `wgi_io.py`. (If a future WGI release adds aggregates, the developer adds a denylist at that time.)

### Missing-data convention: `#N/A` string (NOT -999, NOT NaN, NOT empty)

Live probe of `VoiceandAccountability` found **966 `#N/A` cells** (out of 30,816 = 0.5%). The WGI xlsx is the only one of our Stage 2 inputs that uses a **literal string** for missing data (V-Dem uses `-999`, WDI uses `null`). The `_coerce_float` rule in `wgi_db.py` must:

1. Treat `"#N/A"` (case-sensitive) as missing → `None`.
2. Treat pandas `NaN` (which may appear after a wide pivot) as missing → `None`.
3. Treat `""` (empty string) as missing → `None` (defense in depth).
4. Treat the WDI / V-Dem sentinels (`null`, `NaN`, `nan`, `NA`, `-999`) as missing too (so the same helper works for any future multi-source ingest).
5. Preserve the literal `"#N/A"` string in `raw_value` for the audit trail (per the V-Dem/WDI pattern of preserving the original cell).

The WGI missing-strings set is therefore:
```python
_WGI_MISSING_STRINGS: frozenset[str] = frozenset(
    {"#N/A", "NA", "NaN", "nan", "null", "None", "-999", "-999.0", ""}
)
```

This is the WGI-specific superset of V-Dem's and WDI's missing-string sets. It is the only missing-strings set in `wgi_db.py`; the function `_coerce_float` is the single coercion helper.

### Country code quirks (no denylist, just rename mapping)

The WGI xlsx uses 3-letter codes that are mostly ISO3 but include a few non-standard codes. The Stage 2 adapter **does not** rename them — it stores the raw code in `source_row_reference` and lets Stage 3 (country match) resolve. The list of known quirks (for the test-builder's reference; **no code change required**):

| WGI code | Display name | ISO3 | Notes |
|---|---|---|---|
| `XKX` | Kosovo | (UN-assigned; treat as real country) | |
| `ADO` | Andorra | `AND` | non-standard WGI code |
| `ANT` | Netherlands Antilles (former) | (dissolved 2010) | historical, kept for back-compat |
| `WBG` | West Bank and Gaza | `PSE` | non-standard |
| `ZAR` | Congo, Dem. Rep. | `COD` | non-standard; matches old ISO3 |
| `ROM` | (not present) | `ROU` | n/a |

Stage 3 has a `country_aliases` table that handles these. Stage 2's contract is to write the WGI code verbatim.

### Year coverage drift (2023 in docs, 2022 in xlsx)

The current xlsx release is the "2023 Update" (release year) and contains data through **2022** (last data year). The [`docs/sources/vetting/report.md`](../sources/vetting/report.md) §3.5 says "1996–2023" and the [`docs/sources/attributions.md`](../sources/attributions.md) summary table says "1996–2023" — both refer to the **release year**, not the last data year. The actual data goes through 2022. **The developer updates the docs to "1996–2022" in the same commit as the adapter lands** (similar to the WDI license clarification that was done at WDI implementation time; see §2.8). The Stage 2 `WGIIngestResult.years` for a `year=None` run will be the 24 distinct years 1996, 1998, ..., 2022.

### Biennial then annual

The WGI xlsx is biennial for 1996–2002 (5 measurements: 1996, 1998, 2000, 2002) and annual for 2003–2022 (20 measurements). The Stage 2 read function does not need to special-case this — it just iterates the year-to-column map from row 14. The Stage 11 confidence module's `temporal_fit` component will apply the per-year penalty per the historical-year handling in `docs/architecture/overview.md` (older years = more uncertainty, no penalty for the biennial gap per se).

### Indicator deprecation

The WGI xlsx is annual; indicators are not deprecated between releases (the 6 WGI indicators have been stable since 1996). If a future WGI release drops or renames an indicator (a sheet), the developer updates the catalog `raw_column` to match the new sheet name. The drift-guard test `test_catalog_sheet_names_match_wgi_release` catches this at test time.

### xlsx structure changes (the "voice" vs "voice_and_accountability" legacy)

The WGI xlsx has had minor sheet name changes over the years. Pre-2015 releases used shorter names like `"voice"`, `"polstab"`, `"goveff"`, `"regqual"`, `"rulelaw"`, `"corrupt"`. The current 2023 release uses the full names: `"VoiceandAccountability"`, `"Political StabilityNoViolence"`, etc. The Stage 2 adapter is locked to the current release; legacy support is out of scope (the user re-downloads the latest xlsx if they want current-format output). If the user has an older WGI xlsx on disk, the catalog's `raw_column` values will not match and `read_wgi` will raise `KeyError` on the missing sheet — this is intentional and surfaces the issue immediately.

### Per-cell read performance

The xlsx is 2.1 MB with 7 sheets and 229 rows × 146 cols per indicator sheet. With `openpyxl.read_only=True`, the per-sheet iteration is row-by-row and the read function does not hold the full xlsx in memory. Live read of the full xlsx (all 6 indicators, all 24 years) takes <5 s on a typical laptop. The test fixture is 5 countries × 2 years × 6 indicators = 60 cells and reads in <100 ms.

### `LEADERSDB_PROJECT_ROOT` interaction

The `xlsx_path` defaults to `raw_dir("world_bank_wgi") / "wgidataset.xlsx"`. The `isolated_data_lake` test fixture overrides `LEADERSDB_PROJECT_ROOT`, so the xlsx lives under the test's temp dir. The test fixture `wgi_xlsx_dir` stages the sample xlsx under the temp-dir; the unit tests pass cleanly.

### License drift (apply the WDI fix pattern)

The current `docs/sources/attributions.md` says "World Bank Open Data license" for WGI. The canonical World Bank license is CC BY 4.0 (verified live on the terms-of-use page). **The developer updates the License field to "CC BY 4.0 International" in the same commit as the WGI adapter lands** (mirroring the WDI license clarification that was done at WDI implementation time). The drift-guard test (`test_wgi_attribution_matches_attributions_doc`) covers the long-form citation; the short-form "World Bank WGI (World Bank 2023)" stays the same.

### `obs_status` and other per-cell metadata

WGI does not have an `obs_status` field per cell (WDI does). The WGI Estimate is a single point estimate with the `StdErr`, `NumSrc`, `Rank`, `Lower`, `Upper` as separate columns. There is no per-cell metadata to carry through to `source_observations`; the `notes` column carries `raw_scale=z_score; higher_is_better=1` only.

---

## 2.7 — Dispatch table entry

The `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py` needs one change: replace the existing `"world_bank_wgi": None` stub with the live import, and add the `from . import wgi` line. **No new dispatch key is added** — the key is already there from Phase A.

### Exact changes

In `src/leaders_db/ingest/__init__.py`:

```python
# Add the import alongside the vdem, wdi imports at the top of the import block:
from . import vdem, wdi, wgi

# In the STAGE2_ADAPTERS dict, change the existing line:
    "world_bank_wgi": None,
# to:
    "world_bank_wgi": wgi.ingest_wgi,
```

The full dispatch table stays the same shape (25 keys); only the value of the WGI key changes from `None` to the orchestrator. All other `None` stubs (UCDP, SIPRI, PTS, etc.) are untouched and remain for the next batches.

> **Reviewer-bug from WDI history (apply the lesson):** the WDI review found 1 blocker (a duplicate `"world_bank_wgi"` dispatch key that had been silently masked). The current dispatch table (post-WDI fix) has exactly **one** `"world_bank_wgi"` entry, with value `None`. Do not accidentally add a second one. The dispatch-table test (`test_stage2_adapters_dispatch_table` in the new `tests/test_ingest_wgi.py`) asserts the key set is exactly the 25 keys listed in the WDI test.

The `__all__` does not need to change. No CLI code change is needed — the CLI already iterates over the dispatch table.

---

## 2.8 — Workplan / docs updates

When the WGI adapter lands and the reviewer signs off, the project-manager will add the following entries to `docs/workplan.md` (Done History) and update `docs/sources/attributions.md`, `docs/sources/vetting/report.md`, and `docs/sources/registry.md`.

### `docs/workplan.md` — new Done History entry

> **Phase C.3 — WGI Stage 2 ingest landed (2026-06-18).** Third Stage 2 adapter implemented via the architect → test-builder → developer → reviewer pipeline. ~30 new tests in `tests/test_ingest_wgi.py` (~140 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/wgi.csv` lists 6 WGI indicators across the 2 rating categories WGI serves (5 under `effectiveness`: Voice and Accountability, Political Stability, Government Effectiveness, Regulatory Quality, Rule of Law; 1 under `integrity`: Control of Corruption). Read pattern: open the 2.1 MB `wgidataset.xlsx` with `openpyxl.read_only=True`, walk the 6 indicator sheets (one per WGI dimension), extract the `Estimate` cell for each (country, year), pivot long → wide. No HTTP layer; no per-year cache; no aggregate-code denylist (WGI is country-only, unlike WDI). Test fixture at `tests/fixtures/world_bank_wgi/sample.xlsx` is a 5-country × 2-year × 6-indicator real-format WGI xlsx authored with openpyxl (60 Estimate cells, 1 `#N/A` cell to exercise the missing-value path). End-to-end run for `year=2022` produces 214 real countries × 6 indicators = 1,284 `source_observations` rows in <5 s. The `WGI_ATTRIBUTION` constant is byte-identical to the citation in `docs/sources/attributions.md` (drift-guard test added). License field in the WGI entry of `docs/sources/attributions.md` updated from "World Bank Open Data" to "CC BY 4.0 International" (drift fix, same pattern as WDI). Coverage field updated from "1996–2023" to "1996–2022" (the actual data ends at 2022; "2023" in the docs refers to the release year, not the latest data year). `STAGE2_ADAPTERS["world_bank_wgi"]` is now `wgi.ingest_wgi` in `src/leaders_db/ingest/__init__.py`. WGI follows the V-Dem 3-module split (no `wgi_http.py` since WGI has no HTTP layer). Reviewer caught N blockers, M important, K nits — all fixed in a single iteration. **PASS on the second pass. Moving to UCDP next per the priority list.**

### `docs/sources/attributions.md` — three updates in the WGI entry

The `world_bank_wgi` entry (§1) needs three changes in the same commit:

1. **License field:** change "World Bank Open Data license; free for any use with attribution." → "**CC BY 4.0 International**; the World Bank's [Terms of Use for Datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) require attribution in the form \"The World Bank: Dataset name: Data source (if known).\""
2. **What we extract:** change "plus their standard errors." → "Estimate column only (the 5 other per-year statistics — StdErr, NumSrc, Rank, Lower, Upper — are deferred to a future iteration if the score module needs per-source confidence intervals)."
3. **Summary table Coverage column:** change "1996–2023" → "1996–2022" (the actual data ends at 2022; the 2023 in the title is the release year).

The short-form attribution text in reports (`"World Bank WGI (World Bank 2023)."`) and the long-form citation stay the same.

### `docs/sources/vetting/report.md` — minor updates

§3.5 ("Governance / effectiveness sources") row gets a one-line note: "Stage 2 adapter landed; see `src/leaders_db/ingest/wgi.py`."

§6 ("Caveats the Stage 2 ingest must handle") `world_bank_wgi` row gets an update:

| Source | Caveat to handle |
|---|---|
| `world_bank_wgi` | (was) "Use the `wgidataset.xlsx` file; the standard WGI API endpoint is `sources/3`, not `/v2/indicators`." → (now) "**Use the `wgidataset.xlsx` file only (one xlsx per annual release; no per-indicator HTTP API for the prototype). The xlsx is country-only — no aggregate-code denylist needed (unlike WDI). Missing-data convention is the literal string `'#N/A'`, not `-999` and not `null` (unlike V-Dem and WDI respectively). The current release is 'The Worldwide Governance Indicators, 2023 Update' (data through 2022).**" |

### `docs/sources/registry.md` — no change required

The existing WGI row already says "Free xlsx + API; 2023 data confirmed." The "xlsx + API" wording is fine; the Stage 2 adapter uses the xlsx only and the API is left as a fallback. No change required unless the user wants a more explicit statement.

### `docs/architecture/overview.md` — no change required

The existing `docs/architecture/overview.md` already lists WGI as one of the per-source Stage 2 adapters. No structural change is needed.

---

## 2.9 — Lessons from WDI / V-Dem reviews (apply to WGI from day one)

These are the 8 WDI review findings and the V-Dem findings. Apply them to WGI from the start so we don't repeat them.

1. **No duplicate dispatch-table keys.** The `__init__.py` already has exactly one `"world_bank_wgi": None` entry (Phase A placeholder that this commit will replace). Do not add a second one. The dispatch-table test asserts the 25-key set.

2. **No ruff warnings in the test file.** Hoist all imports to the top; no unused imports; no lines >100 chars. The test-builder must follow the V-Dem / WDI convention (`from __future__ import annotations` first, then `import json, shutil`, then `from pathlib`, then third-party, then `from leaders_db...`).

3. **End-to-end test for orchestrator-level fields.** The `WGIIngestResult` has 6 fields (`source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`). The end-to-end test must assert all 6, not just internal function call counts. (The WDI IngestResult has 8 fields including `indicators_cached`/`indicators_fetched`; the WGI IngestResult has 6 because there is no HTTP layer.)

4. **Docstring accuracy.** Match the runtime default in the docstring (e.g., `year: int | None = None` should be documented as "Default: all 24 years present in xlsx (1996–2022)", not "Required"). The wgi.py docstring should NOT say "400-line convention" or similar lies (WDI docstring was corrected for this); each module's line count will be reported in the Done History entry, not in the source docstring.

5. **Design doc accuracy.** The catalog CSV is the source of truth; the design doc must match exactly. If the developer discovers a discrepancy (e.g. a different sheet name in the xlsx than the design assumed), update the design doc in the same commit.

6. **`confidence IS NULL` assertion.** The Stage 2 → Stage 11 contract requires `confidence` NULL; the test must assert it (`assert all(r.confidence is None for r in rows)`).

7. **`raw_value` assertion for null cells.** The test must assert the `raw_value` for `#N/A` cells is the literal string `"#N/A"` (per the WGI missing-data convention). This is the WGI-specific corollary of WDI's `"nan"` assertion and V-Dem's `"-999.0"` assertion.

8. **Live-xlsx smoke verification.** Run the adapter against the real xlsx after tests pass; verify row count (1,284 for `year=2022`, 30,816 for `year=None`), country count (214), and the WGI attribution in the CLI end-of-run output. Recorded in `docs/testing-guide-stage2-wgi.md`.

### WDI-specific lessons to apply

- **3-module split** (no `wgi_http.py` since WGI has no HTTP layer).
- **Aim for <400 lines per module.** The WGI modules are expected to land at ~180–220, ~280–340, ~280–340 (under 400). If a module exceeds 400, split further.
- **Pydantic `WGIIngestResult`** for the CLI boundary (already in §2.3).
- **The drift-guard test `test_wgi_attribution_matches_attributions_doc` is mandatory.**
- **Update `docs/sources/attributions.md` with the canonical WGI attribution text in the same commit as the constant** (Rule #15). This includes the License field clarification (CC BY 4.0) and the Coverage field correction (1996–2022).

### V-Dem-specific lessons to apply

- **`_coerce_float` and `_coerce_float_from_string` handle all the missing-data sentinels in one place** (defense in depth). WGI's set is the V-Dem set + the WDI set + `"#N/A"`.
- **`_raw_value_to_string` preserves the original cell for the audit trail** (per the V-Dem pattern in `vdem_db.py:199`). For WGI, the audit-trail string for missing cells is `"#N/A"` (the literal).
- **V-Dem's `_delete_existing_observations` is the same pattern as WGI's** — delete existing rows for the requested years before inserting (so re-runs are idempotent for the year filter, but older years are untouched).

---

## Open questions for the developer

1. **`Control of Corruption` category — `effectiveness` or `integrity`?** The design spec marks it `integrity` (matching V-Dem's `v2x_corr` convention; lets Stage 5 use it for both categories as a cross-validation source). The source-vetting report lists WGI under both "Effectiveness / governance" (§3.5) and "Integrity / corruption" (§3.6). If the user wants `Control of Corruption` to stay in `effectiveness` (the bundle-level classification), the catalog row changes — 1-cell edit. Confirm with the user or default to `integrity` and document the choice in the catalog header.

2. **Extract `StdErr` now or defer?** The design defers `StdErr` to a future iteration (the Stage 2 → Stage 11 contract does not need per-source confidence intervals at Stage 2; the per-source authority score is already in `data/metadata/source_authority_table.csv`). If the user wants `StdErr` in Stage 2 for downstream analysis, it is a 6-row catalog extension (one row per indicator with a different sheet-cell lookup); the read function would need an additional long-format pass. Default to deferred; document the call.

3. **xlsx structure change handling.** The current release uses full sheet names (`VoiceandAccountability`); pre-2015 releases used shorter names (`voice`). The design locks the adapter to the current release. If a future WGI release renames a sheet, the developer updates the catalog `raw_column` values and re-runs. Legacy pre-2015 support is out of scope.

4. **Country code quirks.** The WGI xlsx uses 3-letter codes that are mostly ISO3 but include `ADO` (Andorra, real ISO3 = `AND`), `WBG` (West Bank and Gaza, real ISO3 = `PSE`), `ZAR` (Congo Dem. Rep., real ISO3 = `COD`), and `XKX` (Kosovo, UN-assigned). Stage 2 stores the WGI code verbatim in `source_row_reference`; Stage 3 has a `country_aliases` table that handles the rename. No Stage 2 change needed.

5. **`unit` convention.** The design uses `unit = "z_score"` for all 6 indicators. Alternative: `"std_normal"`. Both are reasonable. The developer picks one and uses it consistently; the score module in Stage 5 normalizes the z-score to 0–1 anyway. Default to `"z_score"`.

6. **Multi-year ingestion.** The design accepts a single year per call. If the user wants `year=(2020, 2021, 2022)` in one call, the read function needs to iterate the year list. The Stage 2 code is year-agnostic; the change is local to `read_wgi`. Deferred unless requested.

7. **Network reachability in CI.** WGI has no HTTP layer, so the unit tests are fully offline (the xlsx fixture is local). No `--network` flag needed. The manual smoke is the only "is the real xlsx still what we think it is" check.

8. **WGI release version tracking.** The catalog's `version` field is `2023` (the release year). The `metadata.json` should capture the release year, the download date, and the xlsx SHA-256 checksum. The Stage 2 result's `years` tuple carries the 24 distinct data years. If a future user wants to track the WGI release version more precisely, the `version` field can be widened to `"2023.1"` or similar; deferred.

9. **Standard errors for confidence intervals.** If the score module in Stage 11 ever needs to widen to per-source confidence intervals (e.g. "lower bound of WGI's 90% CI"), the WGI xlsx already carries `Lower` and `Upper` in percentile rank terms. The Stage 2 adapter would need to extract those too. Deferred.

10. **Catalog header comment on the year pattern.** The WGI xlsx is biennial 1996–2002, annual 2003–2022. The Stage 5 score module's `temporal_fit` component treats the biennial gap as no penalty (it is the WGI convention, not a coverage gap). The catalog header comment should note this so the score module author reads it. Add a 1-line note in the catalog header when the developer authors the CSV.
