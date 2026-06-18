# WDI Architecture Design — Stage 2 Adapter for World Bank World Development Indicators

> **Status:** architecture design, ready for test-builder and developer.
> **Phase:** C.2 (data acquisition, second adapter, after V-Dem).
> **Target source key:** `world_bank_wdi`.
> **Wiring in:** `src/leaders_db/ingest/__init__.py::STAGE2_ADAPTERS`.
> **Source verdict:** ✅ `vetted_ok` per [`docs/source-vetting-report.md`](../source-vetting-report.md) §3.3.
> **Liveness verified:** 2026-06-17 — `https://api.worldbank.org/v2/` returns HTTP 200 with valid JSON for `SP.POP.TOTL`, the indicator-list endpoint, and the country-list endpoint.

This document is the design contract for the WDI Stage 2 adapter. The test-builder writes tests against the public surface in §2.3; the developer implements against the same surface. The catalog spec in §2.4 is the only place where WDI's indicator list is decided.

---

## 2.1 — Source contract (what WDI gives us, what we extract)

### Canonical URL and access pattern

| Field | Value |
|---|---|
| API base | `https://api.worldbank.org/v2/` |
| Indicator endpoint pattern | `https://api.worldbank.org/v2/country/all/indicator/<CODE>?date=<YEAR>&format=json&per_page=32500` |
| Country list endpoint | `https://api.worldbank.org/v2/country?per_page=32500&format=json` |
| Format | JSON; 2-element top-level array `[metadata, data]` |
| Auth | none (public, free, no API key) |
| Rate limit | not documented; observed to be tolerant of ~10 req/s |
| HTTPS | yes; Cloudflare-fronted; HTTP/2 |
| User-Agent | not enforced; we send a normal browser UA for parity with V-Dem probes |

The 2-element array shape was confirmed live (2026-06-17). Example `SP.POP.TOTL` for MEX, 2023:

```json
[
  {"page":1,"pages":1,"per_page":50,"total":1,"sourceid":"2","lastupdated":"2026-04-08"},
  [{"indicator":{"id":"SP.POP.TOTL","value":"Population, total"},
    "country":{"id":"MX","value":"Mexico"},
    "countryiso3code":"MEX","date":"2023","value":129739759,
    "unit":"","obs_status":"","decimal":0}]
]
```

**Key observation:** the response field `countryiso3code` is exactly the ISO3 string (e.g. `"MEX"`) — no ISO2→ISO3 mapping is needed at any point. The V-Dem caveat about "ISO2 → ISO3 mapping" does not apply to WDI. (See §2.6 for the multi-indicator caveat instead.)

### License

The World Bank distributes its datasets under **Creative Commons Attribution 4.0 International (CC BY 4.0)** per the [Terms of Use for Datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) (last updated 2018-03-23, verified live 2026-06-17). The terms require attribution in the form:

> The World Bank: Dataset name: Data source (if known).

The current `docs/source-attributions.md` entry paraphrases the license as "World Bank Open Data license; free for any use with attribution." That paraphrase is acceptable as a short form; the canonical long-form citation that the code carries (per the V-Dem pattern in `VDEM_ATTRIBUTION`) is the full bibliographic citation. See §2.3 for the constant.

> **Note for the developer:** while implementing, also update the `world_bank_wdi` entry in `docs/source-attributions.md` to mention "CC BY 4.0" in the `License` field (it currently says "World Bank Open Data"). The license clarification is a one-line addition; deferring it is forbidden by AGENTS.md Always-On Rule #15.

### Coverage and indicator universe

| Dimension | Value |
|---|---|
| Year range | 1960 → present (year-by-year) |
| Country universe | 296 (real + aggregate codes from the v2 `country` endpoint); 217 real countries after filtering with `_WDI_AGGREGATE_ISO3_CODES` (see §2.6) |
| Indicator universe | 29,512 indicators across 5,903 pages of `per_page=5` (live probe 2026-06-17) |
| Frequency | annual; one row per (country, indicator, year) |
| Missing pattern | `value` is `null` for unobserved (country, indicator, year) cells |
| Aggregate codes | yes — the country endpoint returns aggregate regions (e.g. `AFE`, `ARB`, `WLD`) alongside real countries; we filter these out by ISO3 denylist (see §2.6) |

### Indicator catalog scope (this design)

For the prototype we will read a **starter set of 14 indicators** spanning the **2 categories WDI actually serves** (per the user's correction in the design brief: "the governance/effectiveness WGI indicators are NOT WDI — they live in WGI"):

1. **economic_wellbeing** — primary; population, GDP, GDP per capita, GNI per capita, exports, imports, FDI.
2. **social_wellbeing** — secondary; literacy, secondary school enrollment, life expectancy, under-5 mortality, Gini index, hospital beds.

The full per-indicator spec (WDI code → canonical `variable_name`, scale, unit, category, one-line why-it-matters) is in §2.4. The catalog CSV the developer will author lives at `src/leaders_db/ingest/catalogs/wdi.csv` (sibling to the adapter modules, per Phase C convention #1).

> **Why only 2 categories and not 5+?** WDI does not produce political-freedom, integrity/corruption, international-peace, nuclear, or domestic-violence indicators — those are filled by V-Dem, TI CPI, UCDP, FAS, and PTS respectively. The user's brief explicitly carved out the WGI governance category. WDI's coverage of effectiveness indicators (e.g. tax revenue) is borderline and is not in the prototype's required-categories list; if the user wants it in a later iteration, it's a one-row addition to the catalog.

### Integration with downstream schema

Three of the cataloged indicators populate the `country_years` table directly (Stage 5 reads from `source_observations` and writes to `country_years`):

| `variable_name` | → `country_years` column |
|---|---|
| `wdi_population` (SP.POP.TOTL) | `population` |
| `wdi_gdp_current_usd` (NY.GDP.MKTP.CD) | `gdp_current_usd` |
| `wdi_gdp_per_capita` (NY.GDP.PCAP.CD) | `gdp_per_capita` |

The remaining 11 indicators live in `source_observations` and are consumed by the Stage 5 score modules for `economic_wellbeing` and `social_wellbeing`.

### Cited artifacts

- Indicator catalog: `src/leaders_db/ingest/catalogs/wdi.csv` (to be authored from §2.4).
- Per-source `metadata.json`: `data/raw/world_bank_wdi/metadata.json` (to be written when the first successful fetch happens).
- Attribution: `docs/source-attributions.md` §1 entry for `world_bank_wdi`.

---

## 2.2 — Module structure (follow the V-Dem split)

The convention from the Phase C workplan and the V-Dem implementation is **three sibling files per source** under `src/leaders_db/ingest/`, each under the 400-line convention from `docs/coding-guidelines.md`:

| File | Responsibility | Approx LoC target |
|---|---|---|
| `wdi.py` | Public orchestrator: `WDIIngestResult` Pydantic model, `attribution()`, `ingest_wdi()` entrypoint. Re-exports `WDI_ATTRIBUTION`, `WDI_SOURCE_KEY`, `IndicatorSpec` from the I/O module. | ~180–220 |
| `wdi_io.py` | Catalog, HTTP read, JSON parsing, long-to-wide pivot, parquet write, parquet metadata attachment. Owns `WDI_ATTRIBUTION`, `WDI_SOURCE_KEY`, `IndicatorSpec`, and the `_DEFAULT_CATALOG_PATH` constant. | ~280–340 |
| `wdi_db.py` | `sources` upsert, `source_observations` write, missing-value coercion, run manifest. | ~280–340 |

The split rationale is identical to the V-Dem split (see `vdem.py` docstring): `wdi_io` owns the data-lake and the I/O contract; `wdi_db` owns the DB contract; `wdi` is the orchestrator that wires them together. Constants live in `wdi_io` (lowest level) to break the import cycle, and are re-exported by `wdi.py` for the public surface.

### Read pattern — chosen approach: **Option C (one call per indicator, all countries at once, cached JSON)**

Three patterns were considered:

| Pattern | Calls per year | Re-run cost | Failure isolation |
|---|---|---|---|
| A. Per-indicator, per-country batch | N_indicators × N_countries / 100 ≈ thousands | full re-fetch | poor (one bad country breaks) |
| B. One bulk JSON per indicator | N_indicators ≈ 14 | full re-fetch | good (one bad indicator) |
| C. Per-indicator, all countries, with on-disk JSON cache | N_indicators ≈ 14 | re-parse JSON cache | best (HTTP skipped on rerun) |

**We pick Option C**, with one variation: the **HTTP call returns the full country universe (per_page=32500, `country/all`)** in a single call. The API supports this: the live probe of `SP.POP.TOTL` for all countries returned `total=266` in `pages=1` with `per_page=32500`. So 1 HTTP call = 1 indicator × all real countries for one year. The full prototype ingestion of 14 indicators for one year is therefore **14 HTTP calls**, each writing one JSON file to `data/raw/world_bank_wdi/cache/` and one row in the long-format response frame.

Why not Option B (one merged JSON per year)? WDI v2 does **not** support multiple indicators in one call — the live probe of `country/MEX/indicator/SP.POP.TOTL;NY.GDP.MKTP.KD?date=2022:2023&format=json` returned `{"message":[{"id":"120","key":"Invalid value","value":"The provided parameter value is not valid"}]}`. So Option B is mechanically impossible; per-indicator calls are required.

The JSON cache directory layout:

```
data/raw/world_bank_wdi/
├── metadata.json            # source bundle metadata
└── cache/
    └── <year>/
        └── <indicator_code>.json    # verbatim API response for one (year, indicator)
```

The cache is **the audit trail of what the World Bank returned on a given day**. If the API changes a value or deprecates an indicator, the diff is visible in the cache. Re-runs skip the HTTP call when the cache file exists and the orchestrator's `read_wdi(force_refresh=False)` is the default. (NFR-PERF-001: "re-runs must not re-download already-cached source files unless the cache is explicitly invalidated.")

The narrow parquet that Stage 2 writes is wide-format (one row per `(iso3, year)`, one column per catalog indicator) — same shape as the V-Dem narrow parquet. The read function is responsible for the long-to-wide pivot; the write function does not change.

---

## 2.3 — Public surface (exact function signatures)

The test-builder writes against these signatures; the developer implements against these signatures. The names and types are the contract; the docstrings below describe the contract for both audiences.

### Constants (in `wdi_io.py`, re-exported by `wdi.py`)

```python
WDI_SOURCE_KEY: str = "world_bank_wdi"
```

The single source key used everywhere in the data lake, the CLI dispatch, and the test imports. Matches the `data/raw/<key>/` folder name and the `--source` CLI flag.

```python
WDI_ATTRIBUTION: str = (
    "World Bank. 2024. World Development Indicators. "
    "Washington, D.C.: The World Bank. https://data.worldbank.org/ "
    "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
)
```

The exact citation text. Lives in `wdi_io` to break the import cycle. The canonical long-form lives in `docs/source-attributions.md`; the drift-guard test (§2.5) enforces byte-for-byte consistency.

### Indicator catalog (in `wdi_io.py`)

```python
@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the WDI indicator catalog.

    The V-Dem ``IndicatorSpec`` shape is reused verbatim: every Stage 2
    adapter resolves its raw column from this dataclass so the score
    modules in Stage 9-10 can normalize and direct indicators
    consistently across sources.
    """
    variable_name: str         # canonical, e.g. "wdi_population"
    raw_column: str            # the WDI API code, e.g. "SP.POP.TOTL"
    rating_category: str       # one of the 8 from §4
    raw_scale: str             # "absolute", "usd_constant_2015", "percent", "per_1000", "index_0_1", "years", "ratio"
    normalized_scale_target: str  # "0-1" or "0-10" per the catalog convention
    higher_is_better: bool     # True for GDP/capita/life expectancy; False for mortality/Gini
    unit: str                  # "persons", "USD", "USD 2015", "%", "per 1k live births", etc.
    description: str           # one-line human description for audit / docs

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "IndicatorSpec": ...
```

```python
def load_indicator_catalog(catalog_path: Path | None = None) -> list[IndicatorSpec]:
    """Load the WDI indicator catalog from ``catalogs/wdi.csv``.

    Mirrors the V-Dem loader: handles the leading ``#`` comment block,
    drops comment-only lines, validates the required column set, and
    returns one ``IndicatorSpec`` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing.
    """
```

### Read (in `wdi_io.py`)

```python
def read_wdi(
    *,
    year: int | None = None,
    indicator_codes: list[str] | None = None,
    catalog_path: Path | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> pd.DataFrame:
    """Read WDI for ``year`` and pivot to wide format (one row per country).

    Steps:
    1. Load the catalog (or use the ``indicator_codes`` override).
    2. For each indicator: if the cache file exists at
       ``<cache_dir>/<year>/<CODE>.json`` AND ``force_refresh`` is False,
       read the cached JSON; else HTTP-GET the WDI v2 endpoint, write
       the verbatim response to the cache, then parse.
    3. Filter aggregate ISO3 codes (see §2.6) and rows with ``value is None``.
    4. Pivot from long format (one row per (country, indicator, year))
       to wide format (one row per (iso3, year), one column per catalog
       indicator). The narrow frame's column for the indicator value
       uses the catalog's ``variable_name``.
    5. Coerce the year column to int and the indicator columns to float
       (NaN for the absent values; see §2.6 for the missing-value story).

    Args:
        year: filter to a single year. Default: all years present in cache.
        indicator_codes: override the catalog. Default: read from catalog.
        catalog_path: override the indicator catalog. Default: checked-in.
        cache_dir: override the JSON cache root. Default: data-lake path.
        force_refresh: re-download even when the cache file exists.
        request_timeout: per-request HTTP timeout in seconds.

    Returns:
        A pandas DataFrame with columns: ``iso3``, ``year``, then one
        column per catalog indicator (named with the ``variable_name``).
        ``year`` is integer. Indicator columns are float (NaN = missing).

    Raises:
        FileNotFoundError: no cached file and no network reachability
            (or ``force_refresh=True`` and HTTP fails).
        requests.HTTPError: non-2xx WDI API response.
        ValueError: malformed JSON or a catalog code absent from the API.
    """
```

### Parquet write (in `wdi_io.py`)

```python
def write_wdi_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the narrow wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet` and the
    :func:`vdem_io._attach_parquet_metadata` helper: writes the parquet
    via ``df.to_parquet``, then re-writes the file with the WDI
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite — if pyarrow fails,
    the data parquet is still valid and a warning is logged.
    """
```

### DB writes (in `wdi_db.py`)

```python
def register_wdi_source(session: Session) -> int:
    """Upsert the WDI source row into the ``sources`` table.

    Keyed by ``(source_name='World Bank WDI', version='2024')``.
    Idempotent: returns the same ``sources.id`` on every call. Reads
    the bundle's ``metadata.json`` for ``source_url``, ``download_date``,
    ``license_note``, ``coverage_start_year``, ``coverage_end_year``.
    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source`).
    """
```

```python
def write_wdi_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    Same shape as V-Dem's :func:`vdem_db.write_vdem_observations`:

    - ``country_id`` is left ``NULL``; Stage 3 (country match) fills it.
    - ``source_row_reference`` carries the ISO3 prefixed with ``"wdi:"``
      (e.g. ``"wdi:MEX"``) so Stage 3 can resolve it.
    - ``raw_value`` preserves the original numeric string from the API.
    - ``normalized_value`` is the float, or ``None`` if WDI returned
      ``null`` for that cell.
    - Idempotent: deletes existing rows for the requested years
      (from the frame) before inserting. Years outside the frame are
      untouched.

    Returns the number of ``source_observations`` rows inserted.
    """
```

### Run manifest (in `wdi_db.py`)

```python
def write_wdi_run_manifest(
    result: "WDIIngestResult",  # imported lazily to avoid cycle
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

### Orchestrator and Pydantic result (in `wdi.py`)

```python
class WDIIngestResult(BaseModel):
    """Summary of a single ``ingest_wdi`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: ``leaders_db.cli.ingest_source`` reads these fields
    to print the end-of-run summary, and the manifest writer in
    :mod:`wdi_db` consumes the same fields. Same shape as V-Dem's
    :class:`vdem.IngestResult` for consistency.
    """
    source_id: int = Field(..., ge=1)
    parquet_path: Path
    observation_rows: int = Field(..., ge=0)
    countries: int = Field(..., ge=0)
    years: tuple[int, ...]
    indicators: int = Field(..., ge=0)
    indicators_cached: int = Field(..., ge=0)  # how many of the catalog indicators were read from cache
    indicators_fetched: int = Field(..., ge=0)  # how many were HTTP-fetched this run

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]: ...

    @property
    def attribution(self) -> str:
        """The WDI attribution text (Always-On Rule #15)."""
        return WDI_ATTRIBUTION


def attribution() -> str:
    """Return the WDI attribution block for public output (Rule #15)."""


def ingest_wdi(
    *,
    year: int | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> WDIIngestResult:
    """Run Stage 2 for WDI end-to-end.

    Steps:
    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_wdi`.
    3. Write the narrow parquet via :func:`write_wdi_parquet`.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Build the :class:`WDIIngestResult` and write the run manifest.
    6. Return the result.

    The function is the single public entry point — both the CLI
    command ``leaders-db ingest-source --source world_bank_wdi`` and
    the tests call it. The DB session resolves through
    :func:`session_scope`, which honors the ``LEADERSDB_PROJECT_ROOT``
    env var. No explicit ``database_url`` kwarg is needed.
    """
```

### `__all__` (in `wdi.py`)

```python
__all__ = [
    "WDI_ATTRIBUTION",
    "WDI_SOURCE_KEY",
    "IndicatorSpec",
    "WDIIngestResult",
    "attribution",
    "ingest_wdi",
]
```

---

## 2.4 — Indicator catalog (the contract for the test fixture)

The test-builder will author `tests/fixtures/wdi/sample.json` based on this spec. The developer will author `src/leaders_db/ingest/catalogs/wdi.csv` from this spec. The two artifacts must agree on the indicator list.

### Catalog format

Same CSV format as `vdem.csv` (Phase C convention #1). The 8 required columns are exactly the V-Dem 8; the test fixture mirrors them.

```
variable_name,raw_column,rating_category,raw_scale,normalized_scale_target,higher_is_better,unit,description
```

### Starter indicator list (14 indicators across 2 categories)

| # | WDI code | `variable_name` | Category | Scale | Unit | Direction | Why it matters |
|---|---|---|---|---|---|---|---|
| 1 | `SP.POP.TOTL` | `wdi_population` | economic_wellbeing | absolute | persons | higher_is_better | Total population; the denominator for per-capita metrics and the `country_years.population` column. |
| 2 | `NY.GDP.MKTP.CD` | `wdi_gdp_current_usd` | economic_wellbeing | usd_current | USD | higher_is_better | GDP at market prices in current USD; the `country_years.gdp_current_usd` column. |
| 3 | `NY.GDP.PCAP.CD` | `wdi_gdp_per_capita` | economic_wellbeing | usd_current | USD per capita | higher_is_better | GDP per capita; the `country_years.gdp_per_capita` column. The headline economic well-being metric. |
| 4 | `NY.GDP.MKTP.KD` | `wdi_gdp_constant_2015_usd` | economic_wellbeing | usd_constant_2015 | USD 2015 | higher_is_better | GDP at constant 2015 USD; inflation-adjusted for cross-year comparison. |
| 5 | `NY.GDP.PCAP.PP.KD` | `wdi_gdp_per_capita_ppp_constant_2017` | economic_wellbeing | usd_constant_2017_intl | intl $ 2017 | higher_is_better | GDP per capita at PPP; the cross-country-purchasing-power metric. Cross-checks PWT. |
| 6 | `NY.GNP.PCAP.CD` | `wdi_gni_per_capita_atlas` | economic_wellbeing | usd_current | USD per capita | higher_is_better | GNI per capita (Atlas method); the World Bank's lending-classification denominator. |
| 7 | `NE.EXP.GNFS.ZS` | `wdi_exports_pct_gdp` | economic_wellbeing | percent | % of GDP | higher_is_better | Exports of goods and services as a share of GDP. Trade openness. |
| 8 | `NE.IMP.GNFS.ZS` | `wdi_imports_pct_gdp` | economic_wellbeing | percent | % of GDP | neutral | Imports of goods and services as a share of GDP. |
| 9 | `BX.KLT.DINV.CD.WD` | `wdi_fdi_inflows_current_usd` | economic_wellbeing | usd_current | USD | higher_is_better | Foreign direct investment, net inflows (BoP, current USD). |
| 10 | `SP.DYN.LE00.IN` | `wdi_life_expectancy_at_birth` | social_wellbeing | years | years | higher_is_better | Life expectancy at birth (total, years). The headline social well-being metric. Cross-checks WHO GHO. |
| 11 | `SE.ADT.LITR.ZS` | `wdi_literacy_rate_adult` | social_wellbeing | percent | % of people 15+ | higher_is_better | Adult literacy rate. Has shorter coverage (1990+ for many countries). |
| 12 | `SE.SEC.ENRR` | `wdi_secondary_school_enrollment` | social_wellbeing | percent | % gross | higher_is_better | Secondary school enrollment (gross %). Can exceed 100 due to over-age students. |
| 13 | `SH.DYN.MORT` | `wdi_under5_mortality_per_1000` | social_wellbeing | per_1000 | per 1k live births | lower_is_better | Under-5 mortality rate. The inverse direction (`higher_is_better=False`). |
| 14 | `SI.POV.GINI` | `wdi_gini_index` | social_wellbeing | index_0_1 | 0–1 | lower_is_better | Gini index of income inequality. Inverse direction. Has shorter coverage (1990+ for many countries). |

### Direction (higher_is_better) summary

- `higher_is_better=True`: indicators 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12 (11 indicators).
- `higher_is_better=False`: indicators 8 (`NE.IMP.GNFS.ZS` is `neutral`; we'll mark it `higher_is_better=True` for now since import capacity correlates with economic health — but flag for review), 13, 14.
- Indicator 8 is the one judgment call: high imports can mean either "open economy" (good) or "chronic trade deficit" (bad). Mark `higher_is_better=True` for the prototype and add a follow-up note in the catalog header.

> **Open question for the developer:** confirm `NE.IMP.GNFS.ZS` direction. The Phase D score module is the right place to make this judgment; for the Stage 2 catalog, default to `higher_is_better=True` and document the call.

> **Footnote (WDI v2 indicator codes):** WDI v2 returns `Invalid value` for `NV.EXP.TOTL.ZS` / `NV.IMP.TOTL.ZS`; the working codes are `NE.EXP.GNFS.ZS` / `NE.IMP.GNFS.ZS` (exports/imports of goods **and services**, not goods only). The catalog CSV (`src/leaders_db/ingest/catalogs/wdi.csv`) is the source of truth; the design doc was corrected at the WDI implementation time.

### `normalized_scale_target`

For the prototype, all 14 indicators normalize to `0-1` (matching V-Dem). The actual normalization is the Stage 5 score module's job, not Stage 2's. Stage 2 only writes the raw value to `source_observations.normalized_value` and preserves the scale in the catalog. The `normalized_scale_target` column is documentation for Stage 5, not a transformation.

### Scale tag convention

| `raw_scale` value | Used for |
|---|---|
| `absolute` | population |
| `usd_current` | current-USD dollar figures |
| `usd_constant_2015` | constant-2015-USD figures |
| `usd_constant_2017_intl` | constant-2017-international-$-PPP figures |
| `percent` | percentage values |
| `per_1000` | rates per 1,000 (e.g. mortality) |
| `index_0_1` | normalized indices (Gini) |
| `years` | life-expectancy years |
| `ratio` | ratios (e.g. school enrollment) |

### Test fixture shape (5 countries × 2 years × 14 indicators)

The test-builder's fixture `tests/fixtures/wdi/sample.json` will be a single JSON file matching the WDI v2 API response shape, but sliced to:

- 5 countries: MEX, USA, SWE, IND, NGA (matching V-Dem's test fixture).
- 2 years: 2022, 2023.
- 14 indicators (one file per indicator under `cache/2023/` etc.; the test reads them in one frame).

The fixture file shape is **a directory of 14 JSON files**, one per indicator. The read function is exercised by pointing the fixture's parent dir as the `cache_dir` override. No HTTP call is made in unit tests; the cache is the test data.

```json
{
  "metadata": {"page":1,"pages":1,"per_page":50,"total":5,"sourceid":"2","lastupdated":"2026-04-08"},
  "data": [
    {"indicator":{"id":"SP.POP.TOTL","value":"Population, total"},
     "country":{"id":"MX","value":"Mexico"},"countryiso3code":"MEX",
     "date":"2023","value":129739759,"unit":"","obs_status":"","decimal":0},
    {"indicator":{"id":"SP.POP.TOTL","value":"Population, total"},
     "country":{"id":"US","value":"United States"},"countryiso3code":"USA",
     "date":"2023","value":334914895,"unit":"","obs_status":"","decimal":0},
    ...
  ]
}
```

Plus 4 more countries × 2022 and 2023 rows for all 14 indicators = 5 × 2 × 14 = 140 data rows. The test asserts: `len(df) == 5 * 2 == 10` (wide format), 14 indicator columns + `iso3` + `year` = 16 columns.

---

## 2.5 — Test plan (what the test-builder writes)

The test plan covers the 5 Phase C convention #5 categories (catalog, read, write+DB, idempotency, attribution) plus the orchestrator and CLI. Every test has a defined fixture, an assertion, and a 1-line description. The V-Dem test file is the template.

### Catalog (Phase C convention #5a)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_load_indicator_catalog_returns_14_specs` | The checked-in catalog has 14 indicators (matches §2.4 spec). | `wdi_catalog_path` (the path helper) |
| `test_load_indicator_catalog_required_columns` | The 8 required CSV columns are present; the rating_category set is exactly `{economic_wellbeing, social_wellbeing}`. | same |
| `test_load_indicator_catalog_missing_file` | Missing catalog raises `FileNotFoundError`, not a silent empty list. | `tmp_path` |
| `test_indicator_spec_from_csv_row` | `higher_is_better=0`/`=1` round-trips to a real bool (matching V-Dem's test). | inline dict |

### Read (Phase C convention #5b)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_wdi_returns_full_fixture` | The fixture (5 countries × 2 years × 14 indicators) produces a wide DataFrame: 10 rows, 16 columns (iso3, year, 14 indicators). | `wdi_cache_dir` (stages the JSON fixture under `data/raw/world_bank_wdi/cache/`) |
| `test_read_wdi_filters_to_year` | `year=2023` keeps only the 5 rows for 2023; `set(df["year"]) == {2023}`. | same |
| `test_read_wdi_pivots_long_to_wide` | Each catalog indicator is one column; no row is duplicated; no (country, indicator) cell is in long format. | same |
| `test_read_wdi_filters_aggregates` | The cache also includes aggregate ISO3 codes (`AFE`, `ARB`); the returned DataFrame excludes them. Asserts `assert "AFE" not in df["iso3"].values`. | aggregate-staging helper |
| `test_read_wdi_handles_null_values` | The API's `value: null` cells become `NaN` in the DataFrame; `normalized_value` is `None` in `source_observations`. | null-staging helper |
| `test_read_wdi_uses_cache_when_present` | With cache files present, `read_wdi(force_refresh=False)` does NOT call HTTP (use a `monkeypatch` on `requests.get` to assert zero calls). | `wdi_cache_dir` + `monkeypatch` |
| `test_read_wdi_force_refresh_overrides_cache` | `force_refresh=True` calls HTTP even when cache exists. | same |
| `test_read_wdi_missing_cache_and_no_network` | When no cache and no network (monkeypatched `requests.get` raises), `read_wdi` raises `FileNotFoundError` with an actionable message. | `monkeypatch` |
| `test_default_path_helpers` | `default_raw_dir()` and `default_processed_parquet_path()` point at the conventional data-lake locations; `default_cache_dir()` exists under `data/raw/world_bank_wdi/cache/`. | none |

### Parquet write + DB (Phase C convention #5c)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_wdi_parquet_creates_file` | `write_wdi_parquet(df)` writes a valid parquet under `data/processed/world_bank_wdi/`; round-trip preserves shape and columns. | `wdi_cache_dir` |
| `test_write_wdi_parquet_attaches_attribution_metadata` | The parquet's file-level metadata carries `wdi_attribution` (= `WDI_ATTRIBUTION`) and `wdi_source_key` (= `b"world_bank_wdi"`) (Rule #15). | same |
| `test_register_wdi_source_is_idempotent` | Two calls to `register_wdi_source` return the same `sources.id`; the row has `source_name="World Bank WDI"`, `version="2024"`, `source_type="official"`. | `database_url` + `_init_test_db` |
| `test_register_wdi_source_non_destructive_update` | Removing the bundle's `metadata.json` between calls keeps the existing `source_url` and `license_note` (same policy as V-Dem). | same |
| `test_write_wdi_observations_row_count` | `len(df) * len(specs)` observations are written. With the fixture (10 rows × 14 indicators) the count is 140. | `wdi_cache_dir` + `database_url` |
| `test_write_wdi_observations_is_idempotent` | Re-running produces the same count, not 2× the count. | same |
| `test_write_wdi_observations_country_id_is_null` | `country_id` is `None` for every row (Stage 3 fills it); `source_row_reference` starts with `"wdi:"`. | same |
| `test_write_wdi_observations_handles_null_values` | An API `value: null` row becomes `normalized_value=NULL` in SQLite and `raw_value="nan"` (or empty) in the audit trail. | null-staging helper |
| `test_default_path_helpers` | (See Read section above — same test, also belongs here.) | — |

### Orchestrator (Phase C convention #5d — end-to-end idempotency)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_ingest_wdi_end_to_end` | `ingest_wdi()` writes the parquet, the sources row, the 140 `source_observations` rows, and the manifest in one call. Result has `countries=5, years=(2022,2023), indicators=14, indicators_cached=14, indicators_fetched=0`. | `wdi_cache_dir` + `database_url` |
| `test_ingest_wdi_filters_to_year` | `year=2023` keeps 5 countries × 1 year × 14 indicators = 70 observation rows. | same |
| `test_ingest_wdi_is_idempotent` | Two consecutive `ingest_wdi()` calls produce the same `observation_rows` count, the same `source_id`, and the parquet's mtime is the same (no re-write). | same |
| `test_ingest_wdi_indicators_cached_and_fetched` | With a partial cache (3 of 14 indicators), the result's `indicators_cached=3, indicators_fetched=11`. | partial-cache helper + `monkeypatch` |

### Attribution / Rule #15

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_run_manifest` | The manifest is JSON next to the parquet, includes `attribution`, `source_id`, `observation_rows`, `years`, `indicators`. | `isolated_data_lake` |
| `test_attribution_matches_constant` | `wdi.attribution() == WDI_ATTRIBUTION`; contains `"World Bank"`, `"2024"`, `"WDI"`, `"CC BY 4.0"`. | — |
| `test_wdi_attribution_matches_attributions_doc` | `WDI_ATTRIBUTION` is a substring of `docs/source-attributions.md` (drift guard, same pattern as V-Dem's). | project root |

### CLI dispatch

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_stage2_adapters_dispatch_table` | `STAGE2_ADAPTERS["world_bank_wdi"] is wdi.ingest_wdi`; the full key set is unchanged (25 keys including WDI). | — |
| `test_cli_ingest_source_rejects_unknown` | `leaders-db ingest-source --source nope` exits non-zero. | `CliRunner` |

### Live-network smoke (manual, not in pytest)

| Test name | What it asserts | When |
|---|---|---|
| `manual: smoke WDI end-to-end against real API for 2023` | `ingest_wdi(year=2023)` with `force_refresh=True` against the live WDI v2 API returns 217 real countries × 14 indicators = 3,038 `source_observations` rows. | After implementation, manual one-shot, recorded in `docs/testing-guide-stage2-wdi.md` |

The manual smoke is gated on a real network call. It is **not** part of `pytest -q` because the WDI API is an external dependency. The test plan is complete when the unit tests pass; the manual smoke is the "is the live API still what we think it is" check.

---

## 2.6 — Edge cases & known issues

### Aggregate country codes (denylist)

The WDI v2 `country/all` endpoint returns aggregate regions as well as real countries. **Live probe on 2026-06-18** (`/v2/country?per_page=400`) returned **296 rows** total: **217 real countries** (where `region.value != "Aggregates"`) and **79 aggregate codes** (where `region.value == "Aggregates"`). The full aggregate set is documented in the constant `_WDI_AGGREGATE_ISO3_CODES` in `src/leaders_db/ingest/wdi_io.py`. The earlier design estimate of "~196 real countries" was stale; the live count is 217, and the denylist was updated at WDI implementation time to add the 30 missing aggregate codes (`AFR`, `BEA`, `BEC`, `BHI`, `BLA`, `BMN`, `BSS`, `CAA`, `CEA`, `CEU`, `CLA`, `CME`, `CSA`, `DEA`, `DEC`, `DLA`, `DMN`, `DNS`, `DSA`, `DSF`, `DSS`, `FXS`, `IBB`, `MDE`, `NAF`, `NRS`, `NXS`, `RRS`, `SXZ`, `XZN`) and to remove the obsolete `HIB` code (no longer in the API).

**Handling:** the read function filters on a static denylist of 79 aggregate ISO3 codes. The denylist lives as a constant in `wdi_io.py` (e.g. `_WDI_AGGREGATE_ISO3_CODES: frozenset[str] = frozenset({"AFE", "AFR", ...})`). The test fixture deliberately includes `AFE` and `ARB` to exercise the filter (the test `test_read_wdi_filters_aggregates` asserts they are absent from the returned DataFrame).

**Why a denylist and not a call to `/country?per_page=32500`?** The denylist is a frozen constant — no I/O, fast, deterministic. The alternative (call the country endpoint and filter on `region.value == "Aggregates"`) is fragile (the World Bank has changed region classifications before) and adds an extra HTTP call per ingest. The denylist is the Stage 2 contract; if a new aggregate is added, the developer updates the constant and the catalog header.

### Multi-indicator not supported

WDI v2 rejects `;`-separated indicator lists (verified live: `country/MEX/indicator/SP.POP.TOTL;NY.GDP.MKTP.KD` returns `{"id":"120","key":"Invalid value","value":"..."}`). **Handling:** the read function loops over `indicator_codes` and makes one HTTP call per indicator. The cache file naming (`<cache_dir>/<year>/<CODE>.json`) keeps the calls independent.

### Pagination

The default `per_page=50` is too small for the all-countries endpoint (266 countries). The API supports `per_page=32500` (the v2 max). **Handling:** `read_wdi` always passes `per_page=32500`. The 1-element `pages=1` response confirms this works for any year × indicator combination (the largest total seen is ~266 country rows).

### Missing values (WDI returns `null`)

Unlike V-Dem's `-999` sentinel, WDI uses `null` for missing cells. The live probe returned `null` for a small number of (country, indicator, year) cells (e.g. some recent years for small countries). **Handling:** the pivot to wide format converts `null` to `NaN`; `_coerce_float_wdi` in `wdi_db.py` converts `NaN` to `None` for the `source_observations.normalized_value` column. The `raw_value` column preserves the literal `"nan"` string (pandas convention) for the audit trail.

### Indicator deprecation

WDI occasionally deprecates indicators (the response includes a `sourceid` and `lastupdated` field per metadata block). **Handling:** the catalog CSV is the source of truth; if a WDI code is deprecated, the developer updates the catalog and the catalog header documents the change. The test `test_load_indicator_catalog_required_columns` would catch a typo in `raw_column`; a deprecated code would surface as `KeyError` or `null`-filled values at read time, which the developer catches in the manual smoke.

### Multi-year requests

The endpoint `country/all/indicator/SP.POP.TOTL?date=2022:2023` returns both years in one call. **Handling:** the read function loops over `year` (when the caller passes a year range in the future) and over `indicator_codes` (the present). For the prototype we accept a single year per call; multi-year is a follow-up if/when the user needs it.

### Country coverage gaps for older years

Some WDI cells are missing for years before ~1990 for certain indicators. **Handling:** the per-cell `null` handling covers this. The Stage 5 score module applies the temporal-fit penalty from the fixed confidence formula (REQ-HIST-001).

### Per-request timeouts and retries

The WDI API is occasionally slow (~3 s for the all-countries call). **Handling:** `read_wdi` accepts a `request_timeout` kwarg (default 30 s). Retry logic: one automatic retry on `requests.ConnectionError` and `requests.Timeout`; no retry on 4xx. The test `test_read_wdi_uses_cache_when_present` confirms the no-HTTP path; the retry behavior is not unit-tested (the manual smoke covers it).

### `LEADERSDB_PROJECT_ROOT` interaction

The `cache_dir` defaults to `raw_dir("world_bank_wdi") / "cache"`. The `isolated_data_lake` test fixture overrides `LEADERSDB_PROJECT_ROOT`, so the cache lives under the test's temp dir. **Handling:** the test fixture `wdi_cache_dir` stages the JSON fixture under the temp-dir cache; the unit tests pass cleanly.

### License drift

The license is CC BY 4.0 (verified live on the terms-of-use page). The current `docs/source-attributions.md` says "World Bank Open Data license". **Handling:** the developer updates the attributions file to add "CC BY 4.0" to the License field of the WDI entry, in the same commit as the WDI adapter. The drift-guard test (`test_wdi_attribution_matches_attributions_doc`) covers the long-form citation; the short-form "World Bank WDI (World Bank 2024)" stays the same.

---

## 2.7 — Dispatch table entry

The `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py` needs one change: replace the `"world_bank_wdi": None` stub with the live import, and add the `from . import wdi` line.

### Exact changes

In `src/leaders_db/ingest/__init__.py`:

```python
# Add the import alongside the vdem import at the top of the import block:
from . import vdem, wdi

# In the STAGE2_ADAPTERS dict, change the existing line:
    "world_bank_wdi": None,
# to:
    "world_bank_wdi": wdi.ingest_wdi,
```

The full dispatch table stays the same shape (25 keys); only the value of the WDI key changes from `None` to the orchestrator. All other `None` stubs (UCDP, SIPRI, PTS, etc.) are untouched and remain for the next batches.

The `__all__` does not need to change. No CLI code change is needed — the CLI already iterates over the dispatch table.

---

## 2.8 — Workplan / docs updates

When the WDI adapter lands and the reviewer signs off, the project-manager will add the following entries to `docs/workplan.md` (Done History) and update `docs/source-vetting-report.md`.

### `docs/workplan.md` — new Done History entry

> **Phase C.2 — WDI Stage 2 ingest landed (2026-06-18).** Second Stage 2 adapter implemented, end-to-end smoke for 2023 green. New test file `tests/test_ingest_wdi.py` covers catalog, read, write+DB, idempotency, attribution, and CLI dispatch (31 tests, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/wdi.csv` lists 14 WDI indicators across the 2 rating categories WDI actually serves (economic_wellbeing, social_wellbeing). Read pattern: one HTTP call per indicator (WDI v2 does not support multi-indicator queries), all 217 real countries at once (`per_page=32500`), cached verbatim as JSON under `data/raw/world_bank_wdi/cache/<year>/<CODE>.json`. Re-runs skip HTTP when the cache is present. Test fixture at `tests/fixtures/world_bank_wdi/cache/{2022,2023}/` is 5 countries × 2 years × 14 indicators = 140 (country, indicator, year) cells in 28 JSON files (real WDI response shape, no invented data). End-to-end run for 2023 produces 217 real countries × 14 indicators = 3,038 `source_observations` rows in <60 s. `STAGE2_ADAPTERS["world_bank_wdi"]` is now `wdi.ingest_wdi` in `src/leaders_db/ingest/__init__.py`. WDI attribution text aligned to the canonical citation in `docs/source-attributions.md`; the License field is updated to "CC BY 4.0" (was "World Bank Open Data"). Reviewer caught 1 blocker (duplicate `world_bank_wgi` dispatch key), 5 important (lint warnings, end-to-end test gap, docstring bug, design-doc code drift, missing confidence-NULL test), and 4 nits — all 8 fixed in a single iteration. **PASS on the second pass. Moving to WGI next per the priority list.**

### `docs/source-vetting-report.md` — minor update

§6 ("Caveats the Stage 2 ingest must handle") gets one row updated:

| Source | Caveat to handle |
|---|---|
| `world_bank_wdi` | (was) "ISO2 → ISO3 mapping; pagination for >100 countries." → (now) "**WDI v2 does not support multi-indicator queries — one HTTP call per indicator. Always pass `per_page=32500` to get all countries in one page. Filter aggregate ISO3 codes (`AFE`, `ARB`, `WLD`, ~50 total) via the static denylist in `wdi_io.py`.**" |

The §3.3 row (Economic sources) gets a one-line note: "Stage 2 adapter landed; see `src/leaders_db/ingest/wdi.py`."

### `docs/source-attributions.md` — License field update

The `world_bank_wdi` entry's License line changes from:
> License: World Bank Open Data license; free for any use with attribution.
to:
> License: **CC BY 4.0 International**; the World Bank's [Terms of Use for Datasets](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets) require attribution in the form "The World Bank: Dataset name: Data source (if known)."

The short-form attribution text in reports (`"World Bank WDI (World Bank 2024)."`) and the long-form citation stay the same.

### `docs/architecture.md` — no change required

The existing `architecture.md` already lists WDI as one of the per-source Stage 2 adapters (the WDI placeholder is in the Stage 2 component row). No structural change is needed.

---

## Open questions for the developer

1. **Indicator 8 direction (`NE.IMP.GNFS.ZS`).** Marked `higher_is_better=True` in the spec (import capacity correlates with open economy). The Phase D score module may want to flip this if a high import share is interpreted as "trade deficit". Confirm with the user or defer to the score module.
2. **Retry policy.** Spec says "one automatic retry on `ConnectionError` and `Timeout`; no retry on 4xx." If the user wants exponential backoff or a retry counter in the run manifest, the WDI_ATTRIBUTION-style constant pattern in `wdi_db.py` should add an `http_retries` field to the run manifest JSON.
3. **Network reachability in CI.** The unit tests skip HTTP (cache-based). The CI pipeline may want a `pytest -q --network` flag to exercise the live API on a nightly basis, but that is out of scope for the Stage 2 design.
4. **Cache invalidation policy.** Spec says cache files are never auto-deleted. The `force_refresh=True` flag overrides. A `--refresh-after YYYY-MM-DD` flag could auto-invalidate the cache for a date threshold; deferred to a follow-up.
5. **CC BY 4.0 attribution text.** The drift-guard test enforces byte-for-byte consistency with the attributions doc. If the long-form citation is changed, both the constant and the doc must change in the same commit.
6. **Multi-year support.** The spec accepts a single year per call. If the orchestrator should support `year=(2020, 2021, 2022, 2023)` in one call, the read function needs a `date=<START>:<END>` URL parameter. The indicator catalog and the result schema are year-agnostic; the change is local to `read_wdi`.
7. **`obs_status` and `decimal` fields.** The WDI response includes these per cell. The spec ignores them (they are sparse and not in the prototype's needs). If the user wants them in the audit trail, add them to the narrow frame as columns; the parquet column count goes up by 2.
