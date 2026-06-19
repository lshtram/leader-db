"""Build the UNDP HDI test fixture CSV from the real raw bundle.

Run from the repository root to (re)generate the fixture::

    python tests/fixtures/undp_hdi/build_sample_csv.py

The fixture is a real-format slice of the canonical
``data/raw/undp_hdi/HDR23-24_Composite_indices_complete_time_series.csv``
file (latin-1 encoded, 1.9 MB, 207 countries x 1,076 columns). It is
NOT a hand-authored fake: every cell value is copied verbatim from the
real bundle, the latin-1 encoding is preserved, and the wide
``prefix_year`` column shape is preserved.

It contains 4 countries (Mexico, United States, Nigeria, Côte d'Ivoire)
across 2 years (1990, 2022) for the 5 in-scope prefixes
(``hdi``, ``le``, ``eys``, ``mys``, ``gnipc``). The selected slice
exercises:

- A country with diacritics in the display name (``Côte d'Ivoire``).
- A country with at least one empty in-scope cell (Nigeria has
  ``hdi_1990`` empty).
- Real data values across all 5 in-scope indicators for 2022.

The fixture is intentionally small (4 countries x 2 years x 5
prefixes) to keep the test suite fast, but the column shape matches
the real bundle exactly: static columns first, then 10
``{prefix}_{year}`` columns. Per the architecture design contract
(``docs/architecture/undp-hdi.md`` §8), the fixture must be a
real-format slice — not invented — so the wide-to-long narrow frame
tests can exercise the real ``prefix_year`` column shape.

Idempotency: this script can be run repeatedly; the output is
deterministic given the same source CSV.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# --- Configuration ---

# Static columns preserved from the raw CSV (per architecture §2).
_STATIC_COLUMNS: tuple[str, ...] = ("iso3", "country", "hdicode", "region")

# In-scope prefixes from the catalog (architecture §3).
_IN_SCOPE_PREFIXES: tuple[str, ...] = ("hdi", "le", "eys", "mys", "gnipc")

# Two years are sufficient to exercise the wide-to-long parser; the
# architect spec asks for at least 2-3 real countries and 2 years.
_YEARS: tuple[int, ...] = (1990, 2022)

# 4 countries: MEX, USA, NGA, CIV. Chosen to cover:
#   - diacritics (Côte d'Ivoire),
#   - empty in-scope cells (Nigeria has hdi_1990 empty in the real file),
#   - high (USA, SWE-like) and low (NGA) HDI for code diversity.
_COUNTRIES: tuple[str, ...] = ("MEX", "USA", "NGA", "CIV")

# Real input file (relative to project root).
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_INPUT_CSV: Path = (
    _PROJECT_ROOT
    / "data"
    / "raw"
    / "undp_hdi"
    / "HDR23-24_Composite_indices_complete_time_series.csv"
)

# Output fixture path.
_OUTPUT_CSV: Path = Path(__file__).resolve().parent / "sample.csv"


def build_sample_csv(
    input_path: Path = _INPUT_CSV,
    output_path: Path = _OUTPUT_CSV,
    *,
    iso3_codes: tuple[str, ...] = _COUNTRIES,
    years: tuple[int, ...] = _YEARS,
    prefixes: tuple[str, ...] = _IN_SCOPE_PREFIXES,
) -> Path:
    """Build the fixture CSV from a slice of the real raw CSV.

    Args:
        input_path: absolute path to the real raw CSV (latin-1).
        output_path: absolute path to write the fixture to.
        iso3_codes: the countries to keep (real iso3 codes).
        years: the years to keep (one prefix per year per indicator).
        prefixes: the in-scope indicator prefixes to keep.

    Returns:
        The output path.

    Raises:
        FileNotFoundError: if the input CSV is missing.
    """
    if not input_path.is_file():
        raise FileNotFoundError(
            f"UNDP HDI raw CSV not found at {input_path}. "
            "Phase C acquisition must stage the file before tests can run.",
        )

    # Build the column list to read: 4 static + 5 prefixes * 2 years = 14 columns.
    dynamic_cols: list[str] = [f"{prefix}_{year}" for prefix in prefixes for year in years]
    cols_to_read: list[str] = list(_STATIC_COLUMNS) + dynamic_cols

    # Read only the required columns from the real latin-1 CSV.
    df = pd.read_csv(
        input_path,
        encoding="latin-1",
        dtype=str,
        usecols=cols_to_read,
    )

    # Filter to the 4 countries.
    df = df[df["iso3"].isin(iso3_codes)].copy()

    # Reorder columns explicitly (just to be safe; usecols preserves
    # the source order, but we want the static columns first).
    df = df[list(_STATIC_COLUMNS) + dynamic_cols]

    # Reset index for a clean write.
    df = df.reset_index(drop=True)

    # Write back in latin-1 (per architecture §2 + the real file's
    # encoding). The diacritic in "Côte d'Ivoire" requires latin-1.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="latin-1")

    print(
        f"Wrote {len(df)} country rows x {len(df.columns)} columns to {output_path} (latin-1).",
        file=sys.stderr,
    )
    return output_path


if __name__ == "__main__":
    # Allow running from project root or from the fixtures dir.
    build_sample_csv()
