"""Build the WHO GHO API test fixture JSON cache from the captured API data.

Run from the repository root to (re)generate the fixture::

    python tests/fixtures/who_gho_api/build_sample_cache.py

The fixture is a real-format slice of the WHO GHO OData API
(``https://ghoapi.azureedge.net/api/``) responses. The raw API
data was captured by ``capture_real_responses.py`` and lives in
``research/fixture-evidence/who_gho_api/cache_raw/<year>/<IndicatorCode>.json``
(preserved audit evidence under ``research/``, which is gitignored —
the verbatim 1000-record API responses, ~1.1 MB total, are kept out
of the tests tree because the unit tests only need the slim slice).
This script slices those raw responses to a small set of countries
to keep the test suite fast.

If the raw cache is missing at the default location (it is
gitignored and lives under ``research/``), pass an explicit
``raw_cache_dir`` argument on the CLI or via the ``build_sample_cache``
function. The default path intentionally points at the evidence
tree, not the tests tree, so this script fails loudly rather than
silently reading from a stale test fixture.

The selected countries cover the real fixture scenarios:

- MEX, USA, SWE, IND, NGA -- the same 5 countries used by the WDI
  fixture (a familiar pattern). The 5 countries cover low,
  medium, and high values for all 5 in-scope indicators.
- Real values from the captured API responses are preserved
  verbatim (no invented data). The cache JSON shape matches the
  WHO GHO OData response shape (``{"@odata.context": ...,
  "value": [...]}``) so the parser and HTTP layer can run against
  the fixture without modification.

Two years (2019, 2021) are used. 2019 is the pre-pandemic
baseline; 2021 is the latest year with full life-expectancy data
in the GHO API. The catalog's row count assertions in
``tests/test_ingest_who_gho_api.py`` are calibrated against this
fixture.

Idempotency: this script can be run repeatedly; the output is
deterministic given the same raw API captures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# --- Configuration ---

# 5 real countries covering the indicator range. Same selection as
# the WDI test fixture to keep cross-source fixtures aligned.
_COUNTRIES: tuple[str, ...] = ("MEX", "USA", "SWE", "IND", "NGA")

# 2 years for the same reasons as the WDI fixture: a baseline
# year and a current year. 2019 is pre-pandemic; 2021 is the
# latest year with full GHO life-expectancy data.
_YEARS: tuple[int, ...] = (2019, 2021)

# The 5 catalog indicators (mirrors
# ``src/leaders_db/ingest/catalogs/who_gho_api.csv``).
_INDICATORS: tuple[str, ...] = (
    "WHOSIS_000001",
    "MDG_0000000007",
    "WHS4_100",
    "WHS4_117",
    "WHS4_543",
)

# Default raw-cache location lives under ``research/`` (gitignored)
# because the verbatim API responses are audit evidence, not
# test data. Pass an explicit ``raw_cache_dir`` to override.
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_RAW_CACHE_DIR: Path = (
    _PROJECT_ROOT / "research" / "fixture-evidence" / "who_gho_api" / "cache_raw"
)
_OUTPUT_DIR: Path = Path(__file__).resolve().parent / "cache"


def build_sample_cache(
    raw_cache_dir: Path = _RAW_CACHE_DIR,
    output_dir: Path = _OUTPUT_DIR,
    *,
    countries: tuple[str, ...] = _COUNTRIES,
    years: tuple[int, ...] = _YEARS,
    indicators: tuple[str, ...] = _INDICATORS,
) -> list[Path]:
    """Build the slim WHO GHO API test fixture cache.

    For each ``(year, indicator)`` pair, read the raw captured
    response from ``raw_cache_dir/<year>/<indicator>.json`` and
    write a slim version to ``output_dir/<year>/<indicator>.json``
    containing only records for the selected countries. Preserve
    the response envelope (``@odata.context``, ``@odata.count``,
    etc.) and the verbatim per-record fields so the parser
    accepts the fixture without modification.

    Args:
        raw_cache_dir: the source directory with the captured raw
            API responses (committed evidence).
        output_dir: the destination directory for the slim
            fixture cache.
        countries: the country ISO3 codes to keep.
        years: the years to keep.
        indicators: the WHO GHO API IndicatorCodes to keep.

    Returns:
        A list of output file paths written by this call.

    Raises:
        FileNotFoundError: if a raw cache file is missing.
    """
    written: list[Path] = []
    country_set = set(countries)
    for year in years:
        out_year_dir = output_dir / str(year)
        out_year_dir.mkdir(parents=True, exist_ok=True)
        for indicator in indicators:
            raw_path = raw_cache_dir / str(year) / f"{indicator}.json"
            if not raw_path.is_file():
                raise FileNotFoundError(
                    f"Raw WHO GHO API capture missing: {raw_path}. "
                    "Re-run capture_real_responses.py to refresh."
                )
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            # The captured responses already have the
            # SpatialDimType eq 'COUNTRY' + TimeDim eq <year>
            # filter applied (and the SEX_BTSX Dim1 filter for the
            # 2 SEX-disaggregated indicators). We just need to
            # slice to the selected countries.
            slim_values = [
                r
                for r in raw.get("value", [])
                if r.get("SpatialDim") in country_set
            ]
            slim = dict(raw)
            slim["value"] = slim_values
            # If the captured response had a nextLink, drop it (the slim
            # slice fits on one page).
            slim.pop("@odata.nextLink", None)
            out_path = out_year_dir / f"{indicator}.json"
            out_path.write_text(
                json.dumps(slim, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written.append(out_path)
    return written


if __name__ == "__main__":
    written = build_sample_cache()
    print(
        f"Wrote {len(written)} fixture files ({_COUNTRIES} x "
        f"{_YEARS} x {len(_INDICATORS)} indicators).",
        file=sys.stderr,
    )
