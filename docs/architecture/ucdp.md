# UCDP Architecture Design — Stage 2 Adapter for Uppsala Conflict Data Program GED 23.1

> **Status:** architecture design, ready for test-builder and developer.
> **Phase:** C.4 (data acquisition, fourth adapter, after V-Dem, WDI, WGI).
> **Target source key:** `ucdp`.
> **Wiring in:** `src/leaders_db/ingest/__init__.py::STAGE2_ADAPTERS` (replace the existing `"ucdp": None` stub with `ucdp.ingest_ucdp`).
> **Source verdict:** ✅ `vetted_ok` per [`docs/source-vetting/report.md`](../source-vetting/report.md) §3.7.
> **Liveness verified:** 2026-06-18 — `https://ucdp.uu.se/downloads/ged/ged231-csv.zip` returns HTTP 200 with `Content-Type: application/x-zip-compressed`, `Last-Modified: Tue, 06 Jun 2023 18:47:30 GMT`, downloaded zip is 26,587,114 bytes (25.4 MB). Inside the zip: `GEDEvent_v23_1.csv`, 228,682,471 bytes (218 MB uncompressed), **316,818 event rows** covering 1989–2022.

This document is the design contract for the UCDP Stage 2 adapter. The test-builder writes tests against the public surface in §2.3; the developer implements against the same surface. The catalog spec in §2.4 is the only place where UCDP's indicator list is decided.

---

## 2.1 — Source contract (what UCDP gives us, what we extract)

### Canonical URL and file format

| Field | Value |
|---|---|
| Canonical URL | `https://ucdp.uu.se/downloads/ged/ged231-csv.zip` |
| Format | Zip containing a single CSV (`GEDEvent_v23_1.csv`) |
| Size | 25.4 MB zip / 218 MB uncompressed CSV (last verified 2026-06-18) |
| Auth | none (public, free, no API key) — but UCDP also offers a registration wall; the zip at the canonical URL is the public download |
| Release cadence | annual; current is "UCDP Georeferenced Event Dataset (GED) 23.1" |
| Local storage | `data/raw/ucdp/ged231-csv.zip`; extracted CSV is read in-memory; `metadata.json` alongside |

> **UCDP distribution is gated but the public download is open.** UCDP offers a logged-in download portal as well, but the canonical `ged231-csv.zip` is publicly accessible from `https://ucdp.uu.se/downloads/ged/` without authentication. The Stage 2 adapter assumes the zip is pre-staged at `data/raw/ucdp/ged231-csv.zip` (the project workflow: download once, never re-fetch). The `zip_path` kwarg is the test surface.
>
> The Stage 2 adapter **does not download** — `download_ucdp()` is out of scope (the existing stub raises `NotImplementedError`; the project workflow uses the `scripts/` helpers or `curl` directly to place the zip).

### CSV structure (verified live 2026-06-18)

The CSV inside the zip is a **single flat event-level table** with **49 columns** and **316,818 rows** (one event per row). There is no nested structure; each row is a self-contained event.

**Header (49 columns, quoted):**

```
id, relid, year, active_year, code_status, type_of_violence, conflict_dset_id,
conflict_new_id, conflict_name, dyad_dset_id, dyad_new_id, dyad_name, side_a_dset_id,
side_a_new_id, side_a, side_b_dset_id, side_b_new_id, side_b, number_of_sources,
source_article, source_office, source_date, source_headline, source_original,
where_prec, where_coordinates, where_description, adm_1, adm_2, latitude, longitude,
geom_wkt, priogrid_gid, country, country_id, region, event_clarity, date_prec,
date_start, date_end, deaths_a, deaths_b, deaths_civilians, deaths_unknown,
best, high, low, gwnoa, gwnob
```

> **The fatalities column is `best`, not `best_est`.** The prompt's `best_est` reference is incorrect — the actual UCDP GED 23.1 column is `best` (with `high` and `low` as confidence bounds). The design uses `best` (the point estimate of total deaths) for the fatalities aggregation. The developer must use `best`; using `best_est` would crash on `KeyError` because the column does not exist. The catalog `raw_column` for fatalities indicators must say `best` (or its derived form), not `best_est`.

**Year range:** 1989–2022 (34 distinct years). The file is "v23.1" (release year 2023); the latest data year is 2022 (the release year is one year ahead of the data year, mirroring the WGI convention).

**Country ID format:** UCDP's **own numeric country ID**, NOT ISO3. Range 2–940, 124 distinct country IDs. Examples: `2` = United States of America, `70` = Mexico, `540` = Angola, `700` = Afghanistan, `811` = Cambodia (Kampuchea). The Stage 2 adapter **stores the raw UCDP country_id in `source_row_reference`** (e.g., `"ucdp:540"`) and **leaves `country_id` NULL** in `source_observations`. Stage 3 (country match) resolves the UCDP country_id to ISO3 via a lookup table that does not yet exist; the Stage 2 adapter makes no attempt to resolve it. (This is the same pattern as V-Dem: V-Dem's `country_text_id` is also stored verbatim in `source_row_reference`, with `country_id` left NULL for Stage 3.)

**The 3 UCDP violence types** (per the UCDP codebook):

| `type_of_violence` | UCDP name | Definition |
|---|---|---|
| `1` | **State-based conflict** | Armed conflict between two organized groups, at least one of which is a state government. Includes civil wars (government vs non-state), inter-state wars, and internationalized civil wars (civil war with foreign state intervention on one or both sides). |
| `2` | **Non-state conflict** | Armed conflict between two organized non-state groups (neither side is a state government). Examples: communal violence, rebel-vs-rebel fighting, gang violence. |
| `3` | **One-sided violence** | Use of armed force by a state government or a formally organized group against civilians. Examples: state-perpetrated massacres, genocide, extrajudicial killings. |

The 316,818 events break down as: type 1 = 227,509 (72%); type 2 = 40,642 (13%); type 3 = 48,667 (15%).

### What we extract vs what we defer

**Extract (4 categories × 2 statistics = 6 indicators × 1 statistic each, per the catalog in §2.4):**

For each `(country, year)`, six indicators (the 6 in the catalog):

1. `ucdp_state_based_events` — count of `type_of_violence == 1` events per country-year.
2. `ucdp_state_based_fatalities` — `sum(best)` for `type_of_violence == 1` events per country-year.
3. `ucdp_onesided_events` — count of `type_of_violence == 3` events per country-year.
4. `ucdp_onesided_fatalities` — `sum(best)` for `type_of_violence == 3` events per country-year.
5. `ucdp_intl_events` — count of `type_of_violence == 1` events where a foreign state is involved (filter documented in §2.6 below), per country-year.
6. `ucdp_intl_fatalities` — `sum(best)` for the same filter, per country-year.

> **Why exclude type 2 (non-state)?** Per [`docs/source-vetting/report.md`](../source-vetting/report.md) §3.7–§3.8, UCDP serves two categories for the prototype: **international_peace** (state-based, type 1) and **domestic_violence** (one-sided, type 3). Non-state conflict (type 2) is not on the indicator catalog; it is not used by any of the 8 scoring categories. If a future iteration adds a "non-state violence" category, this is a 1-row catalog extension (one row for events, one for fatalities, with `raw_column = "type=2"` or similar).

**Defer to a future iteration (kept in the CSV but not written to `source_observations`):**

- The `gwnoa` / `gwnob` (G-W state numbers for side_a and side_b) — these are useful for the international filter (see §2.6) but the Stage 2 read does not extract them as separate indicators; they are used in the filter only.
- The `deaths_a`, `deaths_b`, `deaths_civilians`, `deaths_unknown` breakdown — `best` is the canonical fatalities estimate (per the UCDP codebook, `best = deaths_a + deaths_b + deaths_civilians + deaths_unknown` when all four are present; when only some are known, UCDP's best-estimate methodology uses `high`/`low` bounds plus the available breakdown). The Stage 2 adapter uses `best` only.
- The `high` / `low` bounds — not used for the prototype's point-estimate scoring.
- The `latitude` / `longitude` / `adm_1` / `adm_2` location data — Stage 2 aggregates to country-year; sub-national location is deferred (the score modules in Stage 9–10 work at the country-year level).
- The `source_*` columns (article, office, date, headline, original) — used by UCDP for provenance, not for the prototype's indicator values.
- The `geom_wkt`, `priogrid_gid`, `where_*` — sub-national location, deferred.

### Indicator catalog scope (this design)

For the prototype, **all 6 UCDP indicators** are extracted, feeding the **2 rating categories** UCDP serves per the source-vetting report:

1. **`international_peace`** — 4 indicators: `ucdp_state_based_events`, `ucdp_state_based_fatalities`, `ucdp_intl_events`, `ucdp_intl_fatalities`. The state-based indicators measure any state-based conflict; the intl subset measures the cross-border subset. They cross-validate SIPRI milex (the other international_peace source) and serve as the event-based complement to the expenditure-based SIPRI signal.
2. **`domestic_violence`** — 2 indicators: `ucdp_onesided_events`, `ucdp_onesided_fatalities`. State-perpetrated violence against civilians; cross-validates PTS, CIRIGHTS physical-integrity index, and V-Dem's `v2csreprss` / `v2clkill` / `v2x_clphy` indicators.

The full per-indicator spec (raw column → canonical `variable_name`, filter logic, scale, unit, category, one-line description) is in §2.4. The catalog CSV the developer will author lives at `src/leaders_db/ingest/catalogs/ucdp.csv` (sibling to the adapter modules, per Phase C convention #1).

### Integration with downstream schema

None of the UCDP indicators populate the `country_years` table directly (those columns are reserved for WDI's `population`, `gdp_current_usd`, `gdp_per_capita` — see [`docs/architecture/wdi.md`](wdi.md) §2.1). All 6 UCDP indicators live in `source_observations` and are consumed by the Stage 5 score modules for `international_peace` and `domestic_violence`.

### License

The UCDP dataset is distributed under a **free academic license with attribution**. The UCDP Terms of Use (https://ucdp.uu.se/terms-of-use/) require citation of the dataset version. The canonical long-form attribution text is the citation block in [`docs/source-attributions.md`](../source-attributions.md) §1 entry for `ucdp` (and is the `UCDP_ATTRIBUTION` constant — see §2.3).

### Cited artifacts

- Indicator catalog: `src/leaders_db/ingest/catalogs/ucdp.csv` (to be authored from §2.4).
- Per-source `metadata.json`: `data/raw/ucdp/metadata.json` (to be written when the first successful read happens).
- Attribution: `docs/source-attributions.md` §1 entry for `ucdp`.

---

## 2.2 — Module structure (V-Dem-style with zip extraction)

UCDP is structurally closer to WGI (one local file, no network, no HTTP layer) than to WDI (per-indicator HTTP, JSON cache). The WGI 5-module split (`wgi.py` / `wgi_io.py` / `wgi_xlsx.py` / `wgi_db.py` / `wgi_db_helpers.py`) is the template. The UCDP module splits into **4 sibling files** under `src/leaders_db/ingest/`, each under the 400-line convention from `docs/coding-guidelines.md`:

| File | Responsibility | Approx LoC target |
|---|---|---|
| `ucdp.py` | Public orchestrator: `UCDPIngestResult` Pydantic model, `attribution()`, `ingest_ucdp()` entrypoint. Re-exports `UCDP_ATTRIBUTION`, `UCDP_SOURCE_KEY`, `IndicatorSpec` from the I/O module. | ~180–220 |
| `ucdp_io.py` | Catalog, zip extraction, CSV read, country-year aggregation (long→wide pivot), parquet write, parquet metadata attachment. Owns `UCDP_ATTRIBUTION`, `UCDP_SOURCE_KEY`, `IndicatorSpec`, the catalog loader, and the `_DEFAULT_CATALOG_PATH` constant. The aggregation logic lives here as a private helper. | ~280–340 |
| `ucdp_db.py` | `sources` upsert, `source_observations` write, run manifest, missing-value coercion (the `_coerce_int` and `_coerce_float` helpers for the UCDP `best` column). | ~280–340 |
| `ucdp_db_helpers.py` | Pure helpers: bundle metadata read, ISO date parse, year-range parse, value coercion (counts → int, fatalities → float), `raw_value_to_string` for the audit trail. | ~120–160 |

**No `ucdp_aggregate.py` because the aggregation is ~30–50 lines.** The long→wide pivot is a one-line `df.pivot_table()` after a `groupby` on `(country_id, year, type_of_violence)`. The 3-way aggregation (state-based, one-sided, intl) is three small blocks of code in `ucdp_io.py`. If the aggregation grows past 100 lines during implementation (it should not), split it into `ucdp_aggregate.py` at that time.

**No `ucdp_http.py` because UCDP has no HTTP layer.** The zip is staged locally; the read orchestrator opens the zip, reads the CSV, aggregates, and writes. Same as WGI's 3-module pattern (no WGI HTTP).

The split rationale is identical to V-Dem / WGI: `ucdp_io` owns the data-lake and the I/O contract; `ucdp_db` owns the DB contract; `ucdp_db_helpers` owns the pure coercion helpers; `ucdp` is the orchestrator. Constants live in `ucdp_io` (lowest level) to break the import cycle, and are re-exported by `ucdp.py` for the public surface.

### Read pattern — chosen approach: **zip → CSV → groupby → wide pivot**

The UCDP zip is a CSV inside a zip. The read function performs the long→wide reshape:

1. **Open the zip** with `zipfile.ZipFile(zip_path)`. The zip is 25.4 MB; the uncompressed CSV is 218 MB. **Do not extract the entire CSV to disk** — read it from the zip via `zipfile.ZipFile.open(csv_member)` which streams through the `zipfile.ZipExtFile` (deflate-decoded). This is essential for memory: 218 MB decompressed into a `pandas.read_csv` call would OOM most laptops. Use the `chunksize` parameter of `pd.read_csv` if the in-memory `DataFrame` would still be too large (316,818 rows × 49 columns = ~30–50 MB as a DataFrame after type coercion — fits in memory but is borderline; use `chunksize=50000` for defensive streaming if needed).
2. **Read the CSV** with `pd.read_csv(...)`. Use `usecols` to read only the columns needed for aggregation: `id`, `year`, `country_id`, `type_of_violence`, `best`, `side_a_new_id`, `side_b_new_id`, `gwnob`. This cuts the memory footprint to ~5 MB.
3. **Filter by year** if `year=` is passed (default: all years).
4. **Aggregate** events to country-year for each of the 6 indicators:
   - `ucdp_state_based_events` / `_fatalities`: `groupby(['country_id', 'year']).filter(type_of_violence == 1).agg(...)`.
   - `ucdp_onesided_events` / `_fatalities`: same with `type_of_violence == 3`.
   - `ucdp_intl_events` / `_fatalities`: `type_of_violence == 1` + cross-border filter (see §2.6); `groupby(['country_id', 'year']).agg(...)`.
5. **Pivot to wide format** (one row per `(country_id, year)`, one column per catalog `variable_name`). The `country_id` is UCDP's own integer ID; the `iso3` is left for Stage 3 to fill in.
6. **Coerce** the indicator columns: event counts → `Int64` (nullable integer; missing country-years have 0 events and 0 fatalities, so the wide frame is dense; but defensive NaN handling for any country that has no events in a given year is needed), fatalities → `float` (NaN if all events for a country-year are missing).
7. **Carry the raw event count** in `df.attrs["events_total"]` (the count of rows in the CSV after the year filter, before aggregation) and `df.attrs["events_filtered"]` (the count after applying the type + cross-border filters for the 6 indicators combined). The orchestrator surfaces these in `UCDPIngestResult`.

The Stage 2 → Stage 11 contract: `confidence` is left `NULL` on every row; Stage 11 fills it. `country_id` is left `NULL`; Stage 3 (country match) fills it from the UCDP `country_id` via the UCDP→ISO3 lookup table (a future Stage 3 deliverable).

---

## 2.3 — Public surface (exact function signatures)

The test-builder writes against these signatures; the developer implements against these signatures. The names and types are the contract; the docstrings below describe the contract for both audiences.

### Constants (in `ucdp_io.py`, re-exported by `ucdp.py`)

```python
UCDP_SOURCE_KEY: str = "ucdp"
```

The single source key used everywhere in the data lake, the CLI dispatch, and the test imports. Matches the `data/raw/<key>/` folder name and the `--source` CLI flag.

```python
UCDP_ATTRIBUTION: str = (
    "Davies, Shawn, Garounis, Nicholas, Sollenberg, Ralph, and Allansson, "
    "Marie (2023). UCDP Georeferenced Event Dataset (GED) 23.1. Uppsala "
    "Conflict Data Program. https://ucdp.uu.se/downloads/"
)
```

The exact citation text. Lives in `ucdp_io` to break the import cycle. The canonical long-form lives in `docs/source-attributions.md`; the drift-guard test (§2.5) enforces byte-for-byte consistency.

```python
#: Default location of the indicator catalog. Lives here so
#: :func:`write_ucdp_run_manifest` in ``ucdp_db`` can import it without
#: a cycle.
_DEFAULT_CATALOG_PATH: Path = Path(__file__).resolve().parent / "catalogs" / "ucdp.csv"

#: Raw zip file name inside ``data/raw/ucdp/``.
_RAW_ZIP_NAME: str = "ged231-csv.zip"

#: The CSV member name inside the zip.
_ZIP_CSV_MEMBER: str = "GEDEvent_v23_1.csv"

#: Narrow parquet that Stage 2 writes under ``data/processed/ucdp/``.
_PROCESSED_PARQUET_NAME: str = "ucdp_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "ucdp_attribution"
_PARQUET_META_SOURCE_KEY: str = "ucdp_source_key"
```

### Indicator catalog (in `ucdp_io.py`)

```python
@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the UCDP indicator catalog.

    The V-Dem / WDI / WGI ``IndicatorSpec`` shape is reused verbatim:
    every Stage 2 adapter resolves its raw column from this dataclass
    so the score modules in Stage 9-10 can normalize and direct
    indicators consistently across sources.
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
    """Load the UCDP indicator catalog from ``catalogs/ucdp.csv``.

    Mirrors the V-Dem / WDI / WGI loaders: handles the leading ``#``
    comment block, drops comment-only lines, validates the required
    column set, and returns one ``IndicatorSpec`` per data row in file
    order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
```

### Read (in `ucdp_io.py`)

```python
def read_ucdp(
    *,
    year: int | None = None,
    zip_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read UCDP from the zip and aggregate to country-year wide format.

    Steps:

    1. Load the catalog.
    2. Open the zip at ``zip_path`` (default:
       ``data/raw/ucdp/ged231-csv.zip``) and stream-read the
       ``GEDEvent_v23_1.csv`` member into a DataFrame (using
       ``usecols`` to read only the 7 needed columns).
    3. Filter by year if ``year=`` is passed.
    4. For each catalog row (one per indicator), aggregate to
       country-year: group by ``(country_id, year)``, filter by
       ``type_of_violence`` (and the cross-border filter for
       ``ucdp_intl_*``), and apply ``count`` (events) or ``sum`` on
       the ``best`` column (fatalities).
    5. Pivot to wide format: one row per ``(country_id, year)``, one
       column per catalog ``variable_name``.
    6. Coerce the ``year`` column to ``int``, the event-count columns
       to ``Int64`` (nullable), the fatalities columns to ``float``
       (NaN for missing).
    7. Attach ``df.attrs["events_total"]`` (raw event count after
       year filter, before type filter) and
       ``df.attrs["events_filtered"]`` (count after type + cross-border
       filter for all 6 indicators combined; the intl indicators are a
       subset of the type=1 filter, so this is the post-type-filter
       count).

    Args:
        year: filter to a single year (e.g. ``2022``).
            Default: all years present in the zip (1989-2022, 34 distinct years).
        zip_path: override the input zip. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.

    Returns:
        A pandas DataFrame with columns ``country_id``, ``year``, then
        one column per catalog indicator (named with the
        ``variable_name``). ``year`` is int. ``country_id`` is UCDP's
        own integer ID (NOT ISO3); Stage 3 resolves it to ISO3.
        Event-count columns are ``Int64``. Fatalities columns are
        ``float``. The wide frame is dense: every (country, year)
        cross-product row is present, even when the country had no
        events in that year. Empty country-years are filled with 0.0
        for events and fatalities indicators. This is the same
        behavior as the V-Dem wide frame (every country-year row, even
        with NaN for absent indicators).

    Raises:
        FileNotFoundError: if the zip is missing.
        KeyError: if the zip does not contain ``GEDEvent_v23_1.csv``,
            or if a required column is absent (defensive).
        zipfile.BadZipFile: if the file at ``zip_path`` is not a valid
            zip.
    """
```

### Path helpers (in `ucdp_io.py`)

```python
def default_zip_path() -> Path:
    """Return the conventional UCDP zip path inside the data lake.

    Resolves to ``<project_root>/data/raw/ucdp/ged231-csv.zip``.
    Raises ``FileNotFoundError`` if the file is missing (per the
    design contract in §2.3); the adapter expects the user to have
    placed the zip via the project's download workflow first.
    """
```

```python
def default_processed_parquet_path() -> Path:
    """Return the conventional UCDP narrow parquet path.

    Creates the ``data/processed/ucdp/`` directory if missing.
    """
```

### Parquet write (in `ucdp_io.py`)

```python
def write_ucdp_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet` and
    :func:`wgi_io.write_wgi_parquet` (and the
    :func:`vdem_io._attach_parquet_metadata` helper): writes the parquet
    via ``df.to_parquet``, then re-writes the file with the UCDP
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite — if pyarrow fails,
    the data parquet is still valid and a warning is logged.
    """
```

### DB writes (in `ucdp_db.py`)

```python
def register_ucdp_source(session: Session) -> int:
    """Upsert the UCDP source row into the ``sources`` table.

    Keyed by ``(source_name='UCDP (Uppsala Conflict Data Program)',
    version='23.1')``. Idempotent: returns the same ``sources.id`` on
    every call. Reads the bundle's ``metadata.json`` for
    ``source_url``, ``download_date``, ``license_note``,
    ``coverage_start_year``, ``coverage_end_year``.

    Non-destructive update policy: missing bundle fields keep the
    existing row's old value (same rule as V-Dem's
    :func:`vdem_db.register_vdem_source` and WGI's
    :func:`wgi_db.register_wgi_source`).
    """
```

```python
def write_ucdp_observations(
    session: Session,
    source_id: int,
    df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
) -> int:
    """Write one ``source_observations`` row per (country, year, variable).

    Same shape as V-Dem's :func:`vdem_db.write_vdem_observations` and
    WGI's :func:`wgi_db.write_wgi_observations`:

    - ``country_id`` is left ``NULL``; Stage 3 (country match) fills it
      from the UCDP ``country_id`` column via the UCDP→ISO3 lookup
      table (a future Stage 3 deliverable).
    - ``source_row_reference`` carries the UCDP ``country_id`` prefixed
      with ``"ucdp:"`` (e.g. ``"ucdp:540"`` for Angola) so Stage 3 can
      resolve it.
    - ``raw_value`` preserves the original cell: the int as a string
      for event counts, the float as a string for fatalities.
    - ``normalized_value`` is the int (for event counts) or float (for
      fatalities), or ``None`` if the cell is missing.
    - Idempotent: deletes existing rows for the requested years (from
      the frame) before inserting. Years outside the frame are
      untouched.

    Returns the number of ``source_observations`` rows inserted.
    """
```

### Run manifest (in `ucdp_db.py`)

```python
def write_ucdp_run_manifest(
    result,  # UCDPIngestResult, imported lazily to avoid cycle
    *,
    manifest_dir: Path | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Write a run-manifest JSON next to the narrow parquet.

    The manifest is the audit trail for ``processed/``: it records
    ``source_id``, the parquet path, the observation row count, the
    countries count, the years, the indicator count, the
    ``events_total`` and ``events_filtered``, the catalog path, and
    the attribution. Written every run (not best-effort) so Stage 15
    reports can find the attribution without re-reading the parquet
    metadata.
    """
```

### Orchestrator and Pydantic result (in `ucdp.py`)

```python
class UCDPIngestResult(BaseModel):
    """Summary of a single ``ingest_ucdp`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result crosses
    a CLI boundary: :func:`leaders_db.cli.ingest_source` reads these
    fields to print the end-of-run summary, and the manifest writer in
    :mod:`ucdp_db` consumes the same fields.

    UCDP-specific extras:
    - ``events_total``: raw event count in the zip after the year
      filter, before the type / cross-border filter. Carried forward
      from ``df.attrs["events_total"]``.
    - ``events_filtered``: count after the type + cross-border filter
      for all 6 indicators combined. Carried forward from
      ``df.attrs["events_filtered"]``.

    These are the UCDP-specific equivalents of WDI's
    ``indicators_cached`` / ``indicators_fetched``: they capture
    "how much data was in the input" vs "how much was used" for
    end-to-end audit.
    """
    source_id: int = Field(..., ge=1)
    parquet_path: Path
    observation_rows: int = Field(..., ge=0)
    countries: int = Field(..., ge=0)
    years: tuple[int, ...]
    indicators: int = Field(..., ge=0)
    events_total: int = Field(..., ge=0)
    events_filtered: int = Field(..., ge=0)

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(cls, value: tuple[int, ...]) -> tuple[int, ...]: ...

    @property
    def attribution(self) -> str:
        """The UCDP attribution text (Always-On Rule #15)."""
        return UCDP_ATTRIBUTION
```

> **Note on the IngestResult field count.** WDI has 8 fields (including `indicators_cached` / `indicators_fetched` because WDI has an HTTP layer). WGI has 6 fields (no HTTP layer). UCDP has 8 fields (6 from WGI plus `events_total` and `events_filtered` for the event-level→country-year aggregation audit trail). The end-to-end test asserts all 8.

```python
def attribution() -> str:
    """Return the UCDP attribution block for public output (Rule #15)."""
```

```python
def ingest_ucdp(
    *,
    year: int | None = None,
    zip_path: Path | None = None,
    parquet_path: Path | None = None,
    catalog_path: Path | None = None,
) -> UCDPIngestResult:
    """Run Stage 2 for UCDP end-to-end.

    Steps:

    1. Load the indicator catalog.
    2. Read the wide-format frame via :func:`read_ucdp`. Open the zip
       with ``zipfile.ZipFile``, stream-read the CSV, aggregate to
       country-year, pivot to wide.
    3. Write the narrow parquet via :func:`write_ucdp_parquet`.
    4. Open a DB session, upsert the ``sources`` row, and write
       the ``source_observations`` rows.
    5. Build the :class:`UCDPIngestResult` and write the run manifest.
    6. Return the result.

    The function is the single public entry point — both the CLI
    command ``leaders-db ingest-source --source ucdp`` and the tests
    call it. The DB session resolves through :func:`session_scope`,
    which honors the ``LEADERSDB_PROJECT_ROOT`` env var. No explicit
    ``database_url`` kwarg is needed.

    Args:
        year: filter to a single year (e.g. ``2022``).
            Default: all years present in the zip (1989-2022, 34 distinct years).
        zip_path: override the input zip. Default: data-lake path.
        parquet_path: override the output parquet. Default: data-lake path.
        catalog_path: override the indicator catalog. Default: checked-in.
    """
```

### `__all__` (in `ucdp.py`)

```python
__all__ = [
    "UCDP_ATTRIBUTION",
    "UCDP_SOURCE_KEY",
    "IndicatorSpec",
    "UCDPIngestResult",
    "attribution",
    "ingest_ucdp",
    "register_ucdp_source",
    "write_ucdp_observations",
    "write_ucdp_run_manifest",
]
```

The DB helpers (`register_ucdp_source`, `write_ucdp_observations`, `write_ucdp_run_manifest`) are re-exported so the test-builder's tests can call them through the orchestrator module — same pattern as the WGI / WDI test surface.

---

## 2.4 — Indicator catalog (the contract for the test fixture)

The test-builder will author `tests/fixtures/ucdp/sample.zip` (a real-format UCDP zip containing a real-format CSV with ~20 events across 5 countries × 2 years × multiple event types) based on this spec. The developer will author `src/leaders_db/ingest/catalogs/ucdp.csv` from this spec. The two artifacts must agree on the indicator list.

### Catalog format

Same CSV format as `vdem.csv`, `wdi.csv`, and `wgi.csv` (Phase C convention #1). The 8 required columns are exactly the V-Dem / WDI / WGI 8; the test fixture mirrors them.

```
variable_name,raw_column,rating_category,raw_scale,normalized_scale_target,higher_is_better,unit,description
```

### Indicator list (6 indicators across 2 categories)

| # | `variable_name` | `raw_column` (semantic) | Category | Scale | Unit | Direction | Why it matters | Filter |
|---|---|---|---|---|---|---|---|---|
| 1 | `ucdp_state_based_events` | `event_count(type=1)` | `international_peace` | `count` | `events` | `False` | Number of state-based violent events (gov vs non-state or inter-state) per country-year. Higher = more conflict. | `type_of_violence == 1` |
| 2 | `ucdp_state_based_fatalities` | `sum(best, type=1)` | `international_peace` | `deaths` | `deaths` | `False` | Total deaths in state-based events per country-year (best estimate). | `type_of_violence == 1` |
| 3 | `ucdp_intl_events` | `event_count(type=1 + cross-border)` | `international_peace` | `count` | `events` | `False` | Number of state-based events involving a foreign state (cross-border / internationalized). Higher = more international conflict on the country's soil. | `type_of_violence == 1` AND cross-border filter (see §2.6) |
| 4 | `ucdp_intl_fatalities` | `sum(best, type=1 + cross-border)` | `international_peace` | `deaths` | `deaths` | `False` | Total deaths in internationalized events per country-year. | `type_of_violence == 1` AND cross-border filter |
| 5 | `ucdp_onesided_events` | `event_count(type=3)` | `domestic_violence` | `count` | `events` | `False` | Number of one-sided violence events (gov / organized group vs civilians) per country-year. Higher = more state-perpetrated violence. | `type_of_violence == 3` |
| 6 | `ucdp_onesided_fatalities` | `sum(best, type=3)` | `domestic_violence` | `deaths` | `deaths` | `False` | Total deaths in one-sided events per country-year. | `type_of_violence == 3` |

> **Why `higher_is_better=False` for all 6?** For all UCDP indicators, "more events" or "more deaths" = worse rating (more violence). The Stage 5 score module inverts the raw value (e.g., a country with 0 events scores 10/10; a country with 1000 events scores 0/10; the mapping is monotonic decreasing in the raw count). The `raw_scale` and `normalized_scale_target` columns capture the shape; `higher_is_better=False` tells the score module to invert.

> **Why no `non-state` (type=2) indicator?** Per [`docs/source-vetting/report.md`](../source-vetting/report.md) §3.7–§3.8, UCDP serves `international_peace` (type 1) and `domestic_violence` (type 3) for the prototype. Type 2 (non-state) is not in the 8 rating categories. Deferred.

> **`raw_column` is a semantic label, not a literal CSV column name.** The catalog's `raw_column` for the events indicators is a derived value (`event_count` — a count of rows after the type filter), not a single CSV column. The catalog's `raw_column` for the fatalities indicators is the literal CSV column `best`. The developer encodes this in the read function: for indicators with `raw_column == "event_count"`, the aggregation is `count`; for indicators with `raw_column == "best"`, the aggregation is `sum(best)`. A cleaner alternative is to have a separate `raw_aggregation` column in the catalog (`count` or `sum_best`); this is the WGI / V-Dem convention adapted for UCDP. **The developer picks one and is consistent.** The recommended approach: have a hidden `raw_aggregation` column in the catalog (third column after `raw_column`) that says `count` or `sum_best`. The catalog spec in §2.4 below is the source of truth.

### `raw_scale` convention

| `raw_scale` | Used for | What it means |
|---|---|---|
| `count` | events indicators | A non-negative integer count of events. The `country_years` table column shape is `int`. |
| `deaths` | fatalities indicators | A non-negative integer (in UCDP's `best` column, deaths are always integer; the `high` and `low` bounds are also integer). The Stage 5 score module may log-transform this for cross-country comparability. |

### `normalized_scale_target` convention

For the prototype, all 6 indicators normalize to `0-1` (matching V-Dem / WDI / WGI). The actual normalization is the Stage 5 score module's job, not Stage 2's. Stage 2 only writes the raw value to `source_observations.normalized_value` and preserves the scale in the catalog. The `normalized_scale_target` column is documentation for Stage 5, not a transformation.

> **Note on log scaling for fatalities.** UCDP fatality counts span 0 to 75,340 (max in v23.1, per probe of the `best` column). A linear 0–1 normalization is heavily skewed by a few high-fatality countries (Afghanistan 2018 alone has 25,696 fatalities). The Stage 5 score module will likely use a log transform (`log1p(best)` then linear 0–1) for the fatalities indicators. The catalog's `normalized_scale_target = "0-1"` is the final target shape; the score module picks the transform. The Stage 2 adapter does not apply any transform.

### `unit` convention

| `unit` | Used for |
|---|---|
| `events` | event-count indicators |
| `deaths` | fatalities indicators |

The UCDP unit is a concrete count (number of events or number of deaths), unlike V-Dem (dimensionless `index` on a 0–1 scale) or WGI (dimensionless `z_score`).

### Test fixture shape (5 countries × 2 years × ~20 events)

The test-builder's fixture `tests/fixtures/ucdp/sample.zip` is a **real-format UCDP zip** authored with `zipfile.ZipFile` (committed under `tests/fixtures/ucdp/`). The CSV inside the zip is a real-format UCDP CSV with the canonical 49 columns, but only ~20 rows. The schema is:

- **5 countries**: UCDP `country_id` values picked from the live dataset (e.g., `70` Mexico, `100` Colombia, `540` Angola, `700` Afghanistan, `365` Iran — these are the real UCDP IDs).
- **2 years**: 2021, 2022 (the most recent two years).
- **~20 events**: distributed across the 5 countries × 2 years. At least one event of each `type_of_violence` (1, 2, 3) for the country-year coverage. At least one `ucdp_intl_*` event (e.g., a US-state-vs-some-rebel event in Afghanistan, which would have `gwnob` non-null OR the prompt's spec filter passing).
- **Realistic `best` values** (fatalities 0–100; no invented values — pull from the live UCDP data for the same country-year-type triples, or use plausible values for the synthetic country-year combinations if real data is unavailable).

Total cells in the fixture data: 5 countries × 2 years = 10 country-year rows × 6 indicators after aggregation. The orchestrator writes 10 × 6 = **60 `source_observations` rows** when reading the full fixture (no year filter) and 5 × 6 = **30 rows** when filtering to `year=2022`.

The fixture is small enough to keep the test suite fast (<2 s) and large enough to exercise the zip-read, type-filter, cross-border filter, aggregation, and DB-write paths.

---

## 2.5 — Test plan (what the test-builder writes)

The test plan covers the 5 Phase C convention #5 categories (catalog, read, write+DB, idempotency, attribution) plus the orchestrator and CLI. Every test has a defined fixture, an assertion, and a 1-line description. The WGI / WDI / V-Dem test files are the template.

### Catalog (Phase C convention #5a)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_load_indicator_catalog_returns_6_specs` | The checked-in catalog has 6 indicators (matches §2.4 spec). | `ucdp_catalog_path` |
| `test_load_indicator_catalog_required_columns` | The 8 required CSV columns are present; the `rating_category` set is exactly `{international_peace, domestic_violence}`. | same |
| `test_load_indicator_catalog_missing_file` | Missing catalog raises `FileNotFoundError`, not a silent empty list. | `tmp_path` |
| `test_indicator_spec_from_csv_row` | `higher_is_better=0`/`=1` round-trips to a real bool (matching V-Dem / WDI / WGI). | inline dict |
| `test_catalog_variable_names_match_design` | The 6 `variable_name` values are exactly the names in §2.4: `ucdp_state_based_events`, `ucdp_state_based_fatalities`, `ucdp_intl_events`, `ucdp_intl_fatalities`, `ucdp_onesided_events`, `ucdp_onesided_fatalities`. | `ucdp_catalog_path` |
| `test_catalog_raw_column_includes_best` | The 4 fatalities indicators' `raw_column` includes `best` (the actual UCDP fatalities column). | same |

### Read (Phase C convention #5b)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_read_ucdp_returns_full_fixture` | The fixture (5 countries × 2 years, ~20 events) produces a wide DataFrame: 10 country-year rows × 6 indicator columns + `country_id` + `year` = 8 columns. | `ucdp_zip_dir` (stages the sample zip) |
| `test_read_ucdp_filters_to_year` | `year=2022` keeps only the 5 country-year rows for 2022; `set(df["year"]) == {2022}`. | same |
| `test_read_ucdp_aggregates_events_by_country_year` | The 20 raw events aggregate to exactly 10 country-year rows; the `ucdp_state_based_events` column for Afghanistan 2022 (the heaviest country in the fixture) is `N` (the number of type=1 events in the fixture for that country-year). | same |
| `test_read_ucdp_filters_international_events` | The `ucdp_intl_*` columns contain a count for the one cross-border event in the fixture (e.g., US forces in Afghanistan); the `ucdp_state_based_*` columns include both the cross-border and the domestic events. | same |
| `test_read_ucdp_filters_one_sided_events` | The `ucdp_onesided_*` columns contain only events where `type_of_violence == 3`; no type=1 or type=2 events leak through. | same |
| `test_read_ucdp_handles_missing_columns` | If the CSV in the zip is missing a column (e.g., older UCDP release without `best`), `read_ucdp` raises `KeyError` with an actionable message. | missing-column-staging helper |
| `test_read_ucdp_preserves_zip_metadata` | `df.attrs["events_total"]` and `df.attrs["events_filtered"]` carry the raw event count + filtered count (post year + type + cross-border filter). | `ucdp_zip_dir` |
| `test_read_ucdp_missing_zip` | Missing zip raises `FileNotFoundError` with an actionable message. | `tmp_path` |
| `test_read_ucdp_invalid_zip` | Non-zip file at `zip_path` raises `zipfile.BadZipFile` (or a derived exception). | `tmp_path` (a text file at `zip_path`) |
| `test_default_path_helpers` | `default_zip_path()` points at `data/raw/ucdp/ged231-csv.zip`; raises `FileNotFoundError` if missing. `default_processed_parquet_path()` points at `data/processed/ucdp/ucdp_country_year.parquet`. | none |

### Parquet write + DB (Phase C convention #5c)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_ucdp_parquet_creates_file` | `write_ucdp_parquet(df)` writes a valid parquet under `data/processed/ucdp/`; round-trip preserves shape and columns. | `ucdp_zip_dir` |
| `test_write_ucdp_parquet_attaches_attribution_metadata` | The parquet's file-level metadata carries `ucdp_attribution` (= `UCDP_ATTRIBUTION`) and `ucdp_source_key` (= `b"ucdp"`) (Rule #15). | same |
| `test_register_ucdp_source_is_idempotent` | Two calls to `register_ucdp_source` return the same `sources.id`; the row has `source_name="UCDP (Uppsala Conflict Data Program)"`, `version="23.1"`, `source_type="academic"`. | `database_url` + `_init_test_db` |
| `test_register_ucdp_source_non_destructive_update` | Removing the bundle's `metadata.json` between calls keeps the existing `source_url` and `license_note` (same policy as V-Dem / WDI / WGI). | same |
| `test_write_ucdp_observations_row_count` | `len(df) * len(specs)` observations are written. With the full fixture (10 rows × 6 indicators) the count is 60. | `ucdp_zip_dir` + `database_url` |
| `test_write_ucdp_observations_is_idempotent` | Re-running produces the same count, not 2× the count. | same |
| `test_write_ucdp_observations_country_id_is_null` | `country_id` is `None` for every row (Stage 3 fills it); `confidence` is `None` for every row (Stage 11 fills it); `source_row_reference` starts with `"ucdp:"` and carries the UCDP country_id verbatim. | same |
| `test_write_ucdp_observations_preserves_raw_value` | `raw_value` is the stringified int (events) or float (fatalities) for non-missing cells; `raw_value` is the string `"0"` for events with 0 fatalities (not NULL, not empty). | same |

### Orchestrator (Phase C convention #5d — end-to-end idempotency)

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_ingest_ucdp_end_to_end` | `ingest_ucdp()` writes the parquet, the sources row, the 60 `source_observations` rows, and the manifest in one call. Result has `countries=5, years=(2021,2022), indicators=6, events_total=20, events_filtered=~15` (the intl + state-based + one-sided counts depend on the fixture). | `ucdp_zip_dir` + `database_url` |
| `test_ingest_ucdp_filters_to_year` | `year=2022` keeps 5 countries × 1 year × 6 indicators = 30 observation rows. | same |
| `test_ingest_ucdp_is_idempotent` | Two consecutive `ingest_ucdp()` calls produce the same `observation_rows` count, the same `source_id`, and the parquet's mtime is the same (no re-write). | same |
| `test_ingest_ucdp_result_carries_attribution` | The `UCDPIngestResult.attribution` property returns `UCDP_ATTRIBUTION` byte-for-byte; `result.attribution == UCDP_ATTRIBUTION`. | same |
| `test_ingest_ucdp_result_carries_events_total_and_filtered` | The `UCDPIngestResult.events_total` and `.events_filtered` fields are populated from `df.attrs`; `events_total >= events_filtered`. | same |

### Attribution / Rule #15

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_write_run_manifest` | The manifest is JSON next to the parquet, includes `attribution`, `source_id`, `observation_rows`, `years`, `indicators`, `events_total`, `events_filtered`. | `isolated_data_lake` |
| `test_attribution_matches_constant` | `ucdp.attribution() == UCDP_ATTRIBUTION`; contains `"UCDP"`, `"2023"`, `"Davies"`, `"Georeferenced"`, `"Uppsala"`. | — |
| `test_ucdp_attribution_matches_attributions_doc` | `UCDP_ATTRIBUTION` is a substring of `docs/source-attributions.md` (drift guard, same pattern as V-Dem's `test_vdem_attribution_matches_attributions_doc` and WGI's `test_wgi_attribution_matches_attributions_doc`). | project root |

### CLI dispatch

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_stage2_adapters_dispatch_table` | `STAGE2_ADAPTERS["ucdp"] is ucdp.ingest_ucdp`; the full key set is unchanged (25 keys). | — |
| `test_cli_ingest_source_rejects_unknown` | `leaders-db ingest-source --source nope` exits non-zero. | `CliRunner` |

### Public surface

| Test name | What it asserts | Fixture |
|---|---|---|
| `test_ucdp_module_public_surface` | The `ucdp` module exports the items in `__all__` from §2.3: `UCDP_ATTRIBUTION`, `UCDP_SOURCE_KEY`, `IndicatorSpec`, `UCDPIngestResult`, `attribution`, `ingest_ucdp`. | — |

### Live-zip smoke (manual, not in pytest)

| Test name | What it asserts | When |
|---|---|---|
| `manual: smoke UCDP end-to-end against real zip for 2022` | `ingest_ucdp(year=2022)` against the real 25.4 MB zip returns ~country-year rows × 6 indicators; full unfiltered run returns ~country-year rows × 6 indicators. | After implementation, manual one-shot, recorded in `docs/testing-guide-stage2-ucdp.md` |

The manual smoke is gated on a real on-disk zip (the user downloads it via `curl` to `data/raw/ucdp/ged231-csv.zip` first). The test fixture (`tests/fixtures/ucdp/sample.zip`) is a 20-event slice that fits in <10 KB and is what the unit tests use. The unit tests prove the contract; the manual smoke proves the real zip still works.

---

## 2.6 — Edge cases & known issues

### Country ID collisions (UCDP's own ID, not ISO3)

UCDP's `country_id` is UCDP's own numeric ID (range 2–940, 124 distinct values), NOT ISO3. Examples: `70` = Mexico, `540` = Angola, `700` = Afghanistan, `811` = Cambodia (Kampuchea). The Stage 2 adapter **stores the raw UCDP `country_id` in `source_row_reference`** as `"ucdp:<country_id>"` and **leaves `country_id` NULL** in `source_observations`. Stage 3 (country match) resolves the UCDP `country_id` to ISO3 via a lookup table that does not yet exist; the lookup is a future Stage 3 deliverable (it is NOT part of the UCDP Stage 2 adapter). Same pattern as V-Dem: V-Dem's `country_text_id` (COW code) is also stored verbatim in `source_row_reference`, with `country_id` left NULL for Stage 3.

The lookup table will live at `data/metadata/ucdp_country_iso3.csv` (per the data-sources.md "Source Authority And Specificity Tables" section) and will be loaded by Stage 3. Stage 2 does not depend on it.

### Internationalized conflict filter (the major open question for the developer)

The prompt specifies the international filter as:

> `type_of_violence == 1 AND side_a_new_id != country_id AND side_b_new_id != country_id`

**Live probe of the real UCDP GED 23.1 data shows this filter matches 227,485 of 227,509 state-based events (99.99%).** This is because UCDP's `*_new_id` columns are **actor IDs in a different identifier space** than `country_id`. The actor "Government of Iraq" has `side_a_new_id = 116` (the UCDP actor ID for the Government of Iraq), while Iraq the country has `country_id = 645`. The two identifiers are never equal, so the filter as written always passes. The prompt's filter is therefore essentially a no-op that matches ~all state-based events — not a meaningful "internationalized conflict" filter.

The **more meaningful filter** is to use the `gwnob` column (the Gleditsch-Ward state number for side_b), which UCDP populates when side_b is a foreign state. Live probe shows:

- `gwnob` is non-null for 6,150 / 227,509 state-based events (2.7%).
- The non-null cases are the genuine internationalized events (US forces in Iraq, Russia in Ukraine, Thailand in Cambodia, Nigeria in Cameroon, etc.).

The recommended Stage 2 filter for the `ucdp_intl_*` indicators is therefore:

```
type_of_violence == 1
AND gwnob is not null
```

This matches the standard UCDP definition of "internationalized internal armed conflict" (state-based conflict where a foreign state's forces are present on one side).

**Open question for the developer:** The prompt specifies the `*_new_id` filter; the actual UCDP data suggests the `gwnob` filter is more correct. The developer must:

1. Verify the filter choice with the user before implementing.
2. If the user wants the prompt's filter (i.e., a no-op that matches all state-based events), implement it verbatim and document the data observation in the test for `test_read_ucdp_filters_international_events`.
3. If the user wants the `gwnob` filter, implement it and add a test that exercises the actual cross-border signal (the fixture should include at least one event with `gwnob` non-null to exercise the path).

**Default recommendation:** Use the `gwnob` filter. Document the deviation from the prompt in the same commit as the implementation. If the user wants the prompt's filter, change the design in the same commit (do not silently change the contract — the test fixture must match the chosen filter).

### Header detection in older releases

The CSV inside the zip has a header in UCDP GED 23.1. Older UCDP releases (pre-v19) had no header. The Stage 2 adapter **assumes the header is present** (v23.1 does have it; the v19+ releases all do). If a future UCDP release drops the header, `pd.read_csv` will treat the first data row as a header. The defensive fix: detect the header by checking whether the first row's first cell parses as an integer (the `id` column is the first column and is an integer in every release). If the first cell is not an integer, skip the row. This is a 3-line defensive check; the developer adds it if a future release breaks the assumption.

### Year coverage drift (the 2023 release year, 2022 data year)

The current release is "UCDP GED 23.1" (release year 2023) and contains data through **2022** (last data year). The [`docs/source-vetting/report.md`](../source-vetting/report.md) §3.7 says "1946–2023+" and the [`docs/source-attributions.md`](../source-attributions.md) summary table says "1946–2023+" — both refer to the **release year + projection**, not the last data year. The actual data goes through 2022. **The developer updates the docs to "1989–2022" in the same commit as the adapter lands** (the GED 23.1 dataset covers 1989–2022, not 1946+; the earlier "1946+" coverage belongs to UCDP's older non-GED "UCDP/PRIO Armed Conflict Dataset" which is a separate product). Mirror the WGI "1996–2023" → "1996–2022" fix pattern from [`docs/architecture/wgi.md`](wgi.md) §2.8.

> **Note on the 1946+ coverage discrepancy.** The Phase B source-vetting report said UCDP covers "1946–2023+", which is true of the older UCDP/PRIO conflict dataset (a separate, less granular product). The UCDP GED specifically starts in 1989. The developer should clarify in the coverage field that the GED starts at 1989 (the UCDP/PRIO dataset covers 1946+, but that is not the GED 23.1 we are reading). Update [`docs/data-sources.md`](../data-sources.md) and [`docs/source-attributions.md`](../source-attributions.md) accordingly.

### Missing-data convention: no sentinels

UCDP GED has no missing-data sentinels. The `best` column is always a non-negative integer; the `type_of_violence` column is always 1, 2, or 3. The Stage 2 wide frame is dense: every (country, year) cross-product row is present, even when the country had no events in that year. Empty country-years are filled with 0.0 for events and fatalities indicators. This is the same behavior as the V-Dem wide frame (every country-year row, even with NaN for absent indicators).

The Stage 2 `_coerce_int` and `_coerce_float` helpers are defensive (handle pandas NaN, None, etc.) but in practice the UCDP data is always present. The helpers are the same pattern as V-Dem's `_coerce_float` and WGI's `_coerce_float` — defense in depth against future schema changes.

### `LEADERSDB_PROJECT_ROOT` interaction

The `zip_path` defaults to `raw_dir("ucdp") / "ged231-csv.zip"`. The `isolated_data_lake` test fixture overrides `LEADERSDB_PROJECT_ROOT`, so the zip lives under the test's temp dir. The test fixture `ucdp_zip_dir` stages the sample zip under the temp-dir; the unit tests pass cleanly.

### Aggregation: counts vs. sums

For events indicators, the aggregation is `count` (count rows in the country-year-type group). For fatalities indicators, the aggregation is `sum` on the `best` column. The `_aggregate_count` and `_aggregate_sum` helpers in `ucdp_io.py` are the two private functions used by `read_ucdp`. The output columns are `Int64` (for counts, with explicit `0` for present country-year-type groups) and `float` (for sums, with `0.0` for present country-year-type groups). Missing country-year-type groups are not present in the output (the wide frame only has the country-years where the country had at least one event of any type).

### Zip file structure changes (the UCDP release-version drift)

UCDP GED releases are versioned: 22.1, 23.1, 24.1, etc. The Stage 2 adapter is locked to 23.1 (the current release). If a future UCDP release renames the CSV inside the zip (e.g., `GEDEvent_v24_1.csv`), the developer updates the `_ZIP_CSV_MEMBER` constant. If a future release changes the column names (e.g., `best` → `best_est`), the developer updates the catalog's `raw_column` for the fatalities indicators. The drift-guard test `test_catalog_variable_names_match_design` catches the indicator-name drift; the column-name drift is caught by `test_read_ucdp_handles_missing_columns`.

### Per-cell read performance

The zip is 25.4 MB; the uncompressed CSV is 218 MB. With `usecols` to read only the 7 needed columns (`id`, `year`, `country_id`, `type_of_violence`, `best`, `side_a_new_id`, `side_b_new_id`, `gwnob`) — 8 columns total — the in-memory DataFrame is ~30 MB. The aggregation runs in <2 s on a typical laptop. The test fixture is 20 events and runs in <100 ms. The end-to-end smoke against the real zip (manual, not in pytest) takes ~5–10 s.

### Country code quirks (no denylist, no rename)

UCDP's `country_id` is UCDP's own; Stage 2 stores the raw `country_id` in `source_row_reference` and lets Stage 3 resolve it to ISO3. Stage 2 has no per-country denylist (the UCDP CSV is country-only, no aggregates) and no rename table. The list of known quirks (for the test-builder's reference; **no Stage 2 code change required**):

| UCDP `country_id` | Display name | ISO3 | Notes |
|---|---|---|---|
| `2` | United States of America | `USA` | OK |
| `70` | Mexico | `MEX` | OK |
| `540` | Angola | `AGO` | OK |
| `700` | Afghanistan | `AFG` | OK |
| `811` | Cambodia (Kampuchea) | `KHM` | display name is historical; Stage 3 resolves to modern ISO3 |

Stage 3 has a `country_aliases` table (or will, when the Stage 3 lookup is built) that handles the UCDP→ISO3 resolution. Stage 2's contract is to write the UCDP code verbatim.

### Network reachability in CI

UCDP has no HTTP layer in the Stage 2 adapter. The unit tests are fully offline (the zip fixture is local). The manual smoke is the only "is the real zip still what we think it is" check.

### Stage 1 (client matrix) interaction

UCDP has no Stage 1 interaction — the client matrix is the 2023 validation/test reference and is read separately, never counted as source evidence. UCDP is one of the cross-validation sources (with SIPRI milex) for the `international_peace` category and (with PTS, CIRIGHTS, V-Dem) for the `domestic_violence` category. The Stage 2 → Stage 12 (compare-vs-client) flow is unchanged by UCDP's presence.

---

## 2.7 — Dispatch table entry

The `STAGE2_ADAPTERS` dispatch table in `src/leaders_db/ingest/__init__.py` needs one change: replace the existing `"ucdp": None` stub with the live import, and add the `from . import ucdp` line. **No new dispatch key is added** — the key is already there from Phase A.

### Exact changes

In `src/leaders_db/ingest/__init__.py`:

```python
# Add the import alongside the vdem, wdi, wgi imports at the top of the import block:
from . import vdem, wdi, wgi, ucdp

# In the STAGE2_ADAPTERS dict, change the existing line:
    "ucdp": None,
# to:
    "ucdp": ucdp.ingest_ucdp,
```

The full dispatch table stays the same shape (25 keys); only the value of the UCDP key changes from `None` to the orchestrator. All other `None` stubs (SIPRI milex, SIPRI yearbook, PTS, UNDP HDI, WHO GHO, Polity V, PWT, etc.) are untouched and remain for the next batches.

> **Reviewer-bug from WDI history (apply the lesson):** the WDI review found 1 blocker (a duplicate `"world_bank_wgi"` dispatch key that had been silently masked). The current dispatch table (post-WGI fix) has exactly **one** `"ucdp"` entry, with value `None`. Do not accidentally add a second one. The dispatch-table test (`test_stage2_adapters_dispatch_table` in the new `tests/test_ingest_ucdp.py`) asserts the key set is exactly the 25 keys listed in the WGI test.

The `__all__` does not need to change. No CLI code change is needed — the CLI already iterates over the dispatch table.

---

## 2.8 — Workplan / docs updates

When the UCDP adapter lands and the reviewer signs off, the project-manager will add the following entries to `docs/workplan.md` (Done History) and update `docs/source-attributions.md`, `docs/source-vetting/report.md`, and `docs/data-sources.md`.

### `docs/workplan.md` — new Done History entry

> **Phase C.4 — UCDP Stage 2 ingest landed (DATE).** Fourth Stage 2 adapter implemented via the architect → test-builder → developer → reviewer pipeline. ~30 new tests in `tests/test_ingest_ucdp.py` (~175 total, all passing). Indicator catalog at `src/leaders_db/ingest/catalogs/ucdp.csv` lists 6 UCDP indicators across the 2 rating categories UCDP serves (4 under `international_peace`: `ucdp_state_based_events`, `ucdp_state_based_fatalities`, `ucdp_intl_events`, `ucdp_intl_fatalities`; 2 under `domestic_violence`: `ucdp_onesided_events`, `ucdp_onesided_fatalities`). Read pattern: open the 25.4 MB `ged231-csv.zip` with `zipfile.ZipFile`, stream-read the 218 MB CSV (using `usecols` to limit to 8 columns), aggregate events to country-year (`groupby(country_id, year, type_of_violence)` + filter for `ucdp_intl_*`), pivot long → wide. UCDP is the **first Stage 2 adapter that requires aggregation** (V-Dem, WDI, WGI all read country-year directly; UCDP starts at event-level). Test fixture at `tests/fixtures/ucdp/sample.zip` is a real-format UCDP zip (20 events, 5 countries × 2 years × multiple event types) authored with `zipfile.ZipFile` + `csv`. End-to-end run for `year=2022` produces N country-year rows × 6 indicators. The `UCDP_ATTRIBUTION` constant is byte-identical to the citation in `docs/source-attributions.md` (drift-guard test added). Coverage field updated from "1946–2023+" to "1989–2022" (the GED 23.1 dataset starts at 1989, not 1946 — the 1946+ coverage belongs to UCDP's separate non-GED product). `STAGE2_ADAPTERS["ucdp"]` is now `ucdp.ingest_ucdp` in `src/leaders_db/ingest/__init__.py`. UCDP follows the WGI 4-module split (no `ucdp_http.py` since UCDP has no HTTP layer; no `ucdp_aggregate.py` since aggregation is ~50 lines and fits in `ucdp_io.py`). The UCDP `IngestResult` carries 2 extra fields vs WGI: `events_total` and `events_filtered` (UCDP-specific equivalents of WDI's `indicators_cached` / `indicators_fetched`). The "internationalized conflict" filter (for `ucdp_intl_*`) uses `gwnob` not null (the prompt's `*_new_id != country_id` filter was verified to match 99.99% of state-based events in the live data and was rejected as a no-op; the developer confirms with user before implementing). Reviewer caught N blockers, M important, K nits — all fixed in a single iteration. **PASS on the second pass. Moving to (next source) per the priority list.**

### `docs/source-attributions.md` — three updates in the UCDP entry

The `ucdp` entry (§1) needs three changes in the same commit:

1. **Coverage field:** change "1946–2023+" → "1989–2022" (the actual UCDP GED 23.1 data range; the 1946+ coverage is for a separate UCDP product).
2. **What we extract:** add a note that UCDP contributes to both `international_peace` (type 1 + intl subset) and `domestic_violence` (type 3) categories, and that the Stage 2 adapter aggregates event-level data to country-year.
3. **No new citation line needed** — the UCDP citation is already in §1 and the long-form is the `UCDP_ATTRIBUTION` constant.

The short-form attribution text in reports (`"UCDP GED 23.1 (Davies et al. 2023)."`) and the long-form citation stay the same.

### `docs/source-vetting/report.md` — minor updates

§3.7 ("Conflict / international aggression sources") `ucdp` row gets a one-line note: "Stage 2 adapter landed; see `src/leaders_db/ingest/ucdp.py`."

§3.8 ("Domestic repression / violence sources") "UCDP one-sided (subset of `ucdp`)" row gets a one-line note: "Stage 2 adapter landed; the `ucdp_onesided_*` indicators are the country-year aggregates."

§6 ("Caveats the Stage 2 ingest must handle") `ucdp` row gets an update:

| Source | Caveat to handle |
|---|---|
| `ucdp` | (was) "UCDP uses GW (Gleditsch-Ward) country codes — needs a mapping table to ISO3." → (now) "**UCDP uses its own numeric country IDs (2-940, not ISO3); Stage 2 stores the raw UCDP `country_id` in `source_row_reference` as `ucdp:<id>` and leaves `country_id` NULL. Stage 3 resolves the UCDP `country_id` to ISO3 via `data/metadata/ucdp_country_iso3.csv` (a future Stage 3 deliverable). The fatalities column is `best` (not `best_est` — the prompt's `best_est` reference is incorrect; the actual UCDP GED 23.1 column is `best`). The internationalized conflict filter for the `ucdp_intl_*` indicators uses `gwnob` not null (the Gleditsch-Ward state number for side_b), per the standard UCDP definition of internationalized internal armed conflict. The '1946–2023+' coverage claim in the source-vetting report is for UCDP's separate non-GED conflict dataset; the UCDP GED 23.1 specifically covers 1989–2022.**" |

### `docs/data-sources.md` — one update

The existing `ucdp` row says "Free 26MB zip; 2023 data confirmed. **Primary international-conflict source** (replaces COW MID, which is blocked)." Update to: "Free 25.4MB zip; 1989-2022 data confirmed (the 23.1 release year is 2023; the data ends at 2022). **Primary international-conflict source** (replaces COW MID, which is blocked). Stage 2 adapter aggregates event-level data to country-year."

### `docs/architecture.md` — no change required

The existing `architecture.md` already lists UCDP as one of the per-source Stage 2 adapters. No structural change is needed.

---

## 2.9 — Lessons from WDI / WGI / V-Dem reviews (apply to UCDP from day one)

These are the 8 WDI review findings, the 6 WGI review findings, and the V-Dem review findings. Apply them to UCDP from the start so we don't repeat them.

### WDI lessons (apply all 8)

1. **No duplicate dispatch-table keys.** The `__init__.py` already has exactly one `"ucdp": None` entry (Phase A placeholder that this commit will replace). Do not add a second one. The dispatch-table test asserts the 25-key set.

2. **No ruff warnings in the test file.** Hoist all imports to the top; no unused imports; no lines >100 chars. The test-builder must follow the WGI / V-Dem convention (`from __future__ import annotations` first, then `import json, shutil`, then `from pathlib`, then third-party, then `from leaders_db...`).

3. **End-to-end test for orchestrator-level fields.** The `UCDPIngestResult` has 8 fields (`source_id`, `parquet_path`, `observation_rows`, `countries`, `years`, `indicators`, `events_total`, `events_filtered`). The end-to-end test must assert all 8, not just internal function call counts.

4. **Docstring accuracy.** Match the runtime default in the docstring (e.g., `year: int | None = None` should be documented as "Default: all years present in the zip (1989-2022, 34 distinct years)", not "Required"). The `ucdp.py` docstring should NOT say "400-line convention" or similar lies; each module's line count will be reported in the Done History entry, not in the source docstring.

5. **Design doc accuracy.** The catalog CSV is the source of truth; the design doc must match exactly. If the developer discovers a discrepancy (e.g., the prompt's `best_est` is actually `best` in the live data), update the design doc in the same commit.

6. **`confidence IS NULL` assertion.** The Stage 2 → Stage 11 contract requires `confidence` NULL; the test must assert it (`assert all(r.confidence is None for r in rows)`).

7. **`raw_value` assertion.** The test must assert the `raw_value` for non-missing cells is the stringified int (events) or float (fatalities), and for missing country-years it is `""` (the audit trail of absent). This is the UCDP-specific corollary of V-Dem's `"-999.0"` assertion, WGI's `"#N/A"` assertion, and WDI's `"nan"` assertion.

8. **Live-zip smoke verification.** Run the adapter against the real 25.4 MB zip after tests pass; verify row count, country count, and the UCDP attribution in the CLI end-of-run output. Recorded in `docs/testing-guide-stage2-ucdp.md`.

### WGI lessons (apply all 6)

1. **The WGI reviewer's #3 (index-swap SQL) was a release-blocker because the developer changed the schema to make a test pass. Never change the schema or canonical text to make a test pass. Fix the test instead.** Specifically for UCDP:
   - If a test uses a fragile dict-comprehension pattern, fix the test to sort the rows before building the dict, or use `.order_by()`.
   - If a test asserts on a canonical text (like `"UCDP" in attribution`), change the test to assert on a substring that's actually in the canonical text (like `"Uppsala Conflict Data Program" in attribution`), not the canonical text itself.
   - If a test fails because the catalog column name doesn't match the real data, change the test to match the data, not the data to match the test.

2. **WGI line counts exceeded 400.** For UCDP, design the module split upfront so no file exceeds 400 lines. The 4-module split (`ucdp.py` ~180-220, `ucdp_io.py` ~280-340, `ucdp_db.py` ~280-340, `ucdp_db_helpers.py` ~120-160) is the target. If a module grows past 400, split it during implementation.

3. **WGI `default_xlsx_path()` raise semantics.** UCDP's `default_zip_path()` should also raise `FileNotFoundError` if the file is missing (per the design's stated contract in §2.3). The test `test_default_path_helpers` verifies this.

### V-Dem lessons

1. **`_coerce_float` and `_coerce_int` handle all the missing-data sentinels in one place** (defense in depth). UCDP's set is empty by default (UCDP has no missing sentinels), but the helpers must handle pandas NaN, None, and the V-Dem / WGI / WDI sentinels as defense in depth for future schema changes.

2. **`_raw_value_to_string` preserves the original cell for the audit trail** (per the V-Dem pattern in `vdem_db.py:199`). For UCDP, the audit-trail string for missing country-years is `""` (empty); for present cells, it's `str(cell)`.

3. **V-Dem's `_delete_existing_observations` is the same pattern as UCDP's** — delete existing rows for the requested years before inserting (so re-runs are idempotent for the year filter, but older years are untouched).

4. **V-Dem's `country_id` is renamed to `vdem_country_id` in the narrow frame to avoid collision with the `countries.id` FK.** UCDP's `country_id` is also a non-ISO3 ID; the same approach applies — UCDP's `country_id` is UCDP's own and is stored verbatim in `source_row_reference` as `"ucdp:<id>"`. The `source_observations.country_id` is left NULL. (Note: unlike V-Dem, UCDP does NOT need to rename its `country_id` column in the wide frame because there is no `countries.id` collision — the wide frame's `country_id` is the UCDP integer, and the `source_observations.country_id` is the SQLite FK. Both are different concepts; the wide frame's `country_id` stays as-is.)

5. **V-Dem's session_scope honors `LEADERSDB_PROJECT_ROOT`.** The UCDP orchestrator does the same; no explicit `database_url` kwarg is needed. The `isolated_data_lake` test fixture works without changes.

---

## Open questions for the developer

1. **Internationalized conflict filter (the major open question).** The prompt specifies `type_of_violence == 1 AND side_a_new_id != country_id AND side_b_new_id != country_id`. Live probe of the real UCDP GED 23.1 data shows this filter matches 227,485 of 227,509 state-based events (99.99%) because the `*_new_id` columns are actor IDs in a different identifier space than `country_id` (the filter is essentially a no-op). The more meaningful filter is `gwnob` not null (the Gleditsch-Ward state number for side_b), which matches 6,150 of 227,509 events (2.7%) and corresponds to the standard UCDP definition of internationalized internal armed conflict. **The developer must verify the filter choice with the user before implementing.** Default recommendation: use the `gwnob` filter. Document the deviation from the prompt in the same commit as the implementation. The test fixture must include at least one event with `gwnob` non-null (and at least one with `gwnob` null but `type_of_violence == 1`) to exercise the filter.

2. **Coverage year fix.** The Phase B source-vetting report says UCDP covers "1946–2023+", which is true of the older UCDP/PRIO conflict dataset (a separate product). The UCDP GED 23.1 specifically starts at 1989. The developer updates the docs to "1989–2022" in the same commit as the adapter lands (mirror the WGI "1996–2023" → "1996–2022" fix pattern).

3. **Test fixture scale.** The prompt suggests 5 countries × 2 years. The WGI fixture is 5 countries × 2 years × 6 indicators = 60 cells. The UCDP fixture is 5 countries × 2 years × ~20 events → 10 country-year rows × 6 indicators = 60 observation rows. This is the same final observation count as WGI. Confirm the fixture scale with the user if a different size is preferred.

4. **Aggregation function for events indicators.** The catalog's `raw_column` for events indicators is `event_count` (a derived value, not a single CSV column). The cleanest implementation is to have a separate `raw_aggregation` column in the catalog that says `count` (for events) or `sum_best` (for fatalities). The developer picks one convention and is consistent. Default: `raw_aggregation` as a hidden 9th column in the catalog CSV.

5. **Multi-year ingestion.** The design accepts a single year per call. If the user wants `year=(2020, 2021, 2022)` in one call, the read function needs to iterate the year list. The Stage 2 code is year-agnostic; the change is local to `read_ucdp`. Deferred unless requested.

6. **Zip extraction to disk.** The design reads the CSV from inside the zip via `zipfile.ZipFile.open(...)` (streaming, no disk extraction). If the developer prefers to extract the CSV to disk first (simpler `pd.read_csv` call, but 218 MB on disk), the change is local to `read_ucdp`. The streaming approach is recommended for memory (5x less peak memory).

7. **Catalog header on the year convention.** The UCDP GED 23.1 data ends at 2022. The Stage 5 score module's `temporal_fit` component treats the 2023 gap (release year - data year) the same as the WGI release-year drift (no penalty; the score module reads the data year, not the release year). The catalog header comment should note this. Add a 1-line note in the catalog header when the developer authors the CSV.

8. **Defensive header detection for older UCDP releases.** The current GED 23.1 has a header. Older releases (pre-v19) had no header. The Stage 2 adapter assumes the header is present. If a future UCDP release drops the header, the developer adds a 3-line defensive check (detect the first cell as integer). Deferred unless a real need arises.

9. **UCDP actor lookup table.** The internationalized filter for the `ucdp_intl_*` indicators ideally uses a UCDP-actor-to-UCDP-country lookup (e.g., "actor 116 = Government of Iraq" → "country 645 = Iraq" → "for events in country X, actor 116 is foreign if X != 645"). This is a separate lookup table that would enable a more inclusive filter (foreign state on side_a OR side_b). Without it, we use `gwnob not null` as the proxy. The lookup table is a future Stage 3 deliverable; deferred.

10. **`raw_value` for missing country-years.** UCDP has no missing-data sentinels; the wide frame is dense on every (country, year) cross-product row. Empty country-years are filled with 0.0 for events and fatalities indicators. The Stage 2 `_raw_value_to_string` helper returns `""` for `None` (defense in depth) and `str(cell)` for present cells. The test for `raw_value` assertion is in the WGI / WDI / V-Dem pattern; the developer should follow the same shape.
