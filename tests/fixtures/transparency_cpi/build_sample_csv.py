"""Build the Transparency International CPI test fixture CSV.

Run from the repository root to (re)generate the fixture::

    python tests/fixtures/transparency_cpi/build_sample_csv.py

The fixture is a real-format slice of the HDX-mirrored
Transparency International CPI 2023 CSV. The raw API data was
captured at probe time and lives at
``tmp/source-vetting-evidence/global_cpi_2023.csv`` (the verbatim
180-row response from the OCHA HDX mirror, ~8 KB, 181 lines
including header). This script slices that raw capture to a small
set of countries to keep the test suite fast.

If the raw capture is missing at the default location (the
``tmp/`` folder is gitignored), pass an explicit ``raw_capture``
argument on the CLI or via the ``build_sample_csv`` function. The
default path intentionally points at the project-scoped ``tmp/``
folder rather than the system ``/tmp/`` so this script fails
loudly rather than silently reading from a stale system path.

The selected countries cover the real fixture scenarios:

- MEX, USA, SWE, IND, NGA -- the same 5 countries used by the
  WDI fixture (a familiar pattern). The 5 countries cover low,
  medium, and high CPI scores for 2023.
- Real values from the HDX CSV are preserved verbatim (no
  invented data). The cache CSV shape matches the HDX response
  shape (``country,iso3,region,year,score,rank,sources,
  standardError,lowerCi,upperCi``) so the parser and HTTP layer
  can run against the fixture without modification.

Idempotency: this script can be run repeatedly; the output is
deterministic given the same raw API capture.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# --- Configuration ---

# 5 real countries covering the CPI score range. Same selection
# as the WDI / WHO GHO API / UNDP HDI test fixtures to keep
# cross-source fixtures aligned.
_COUNTRIES: tuple[str, ...] = ("MEX", "USA", "SWE", "IND", "NGA")

# Single year for the prototype target. The HDX mirror also has
# per-year CSVs for other years (2012-2024).
_YEAR: int = 2023

# The HDX CSV column order. Kept as a module-level constant so
# the writer uses the same shape as the parser's required
# columns.
_COLUMNS: tuple[str, ...] = (
    "country",
    "iso3",
    "region",
    "year",
    "score",
    "rank",
    "sources",
    "standardError",
    "lowerCi",
    "upperCi",
)

# The raw capture from the HDX mirror (verbatim response). Default
# points at the project-scoped ``tmp/`` folder (gitignored per
# ``docs/local-data-store.md``); pass an explicit path to override.
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_RAW_CAPTURE: Path = (
    _PROJECT_ROOT / "tmp" / "source-vetting-evidence" / "global_cpi_2023.csv"
)
_OUTPUT_PATH: Path = Path(__file__).resolve().parent / "sample.csv"


def build_sample_csv(
    raw_capture: Path = _RAW_CAPTURE,
    output_path: Path = _OUTPUT_PATH,
    *,
    countries: tuple[str, ...] = _COUNTRIES,
    year: int = _YEAR,
) -> Path:
    """Build the slim Transparency International CPI test fixture CSV.

    Reads the verbatim HDX capture from ``raw_capture`` and writes
    a slim version to ``output_path`` containing only rows for
    the selected countries (5 countries) and the selected year
    (2023). Preserve the verbatim column order and field values
    so the parser and HTTP layer accept the fixture without
    modification.

    Args:
        raw_capture: the source CSV with all 180 country rows.
        output_path: the destination path for the slim fixture.
        countries: the country ISO3 codes to keep.
        year: the year to keep.

    Returns:
        The output path written by this call.

    Raises:
        FileNotFoundError: if the raw capture is missing.
    """
    if not raw_capture.is_file():
        raise FileNotFoundError(
            f"Raw Transparency International CPI HDX capture "
            f"missing: {raw_capture}. Re-run the live probe to "
            f"refresh."
        )
    country_set = set(countries)
    with raw_capture.open(encoding="utf-8", newline="") as src:
        reader = csv.DictReader(src)
        slim_rows = [
            row
            for row in reader
            if row.get("iso3") in country_set
            and int(row.get("year", year)) == int(year)
        ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(slim_rows)
    return output_path


if __name__ == "__main__":
    written = build_sample_csv()
    print(
        f"Wrote {written} ({_COUNTRIES} x year={_YEAR}, "
        f"{len(_COLUMNS)} columns).",
        file=sys.stderr,
    )
