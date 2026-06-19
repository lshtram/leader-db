"""Build the REIGN test fixture CSV from the real raw bundle.

Run from the repository root to (re)generate the fixture::

    python tests/fixtures/reign/build_sample_csv.py

The fixture is a real-format slice of the canonical
``data/raw/reign/REIGN_2021_8.csv`` file
(34.4 MB, 138,600 leader-month rows x 41 columns,
UTF-8 encoded, comma-delimited). It is NOT a hand-authored
fake: every cell value is copied verbatim from the real
bundle, the UTF-8 encoding is preserved, and the 41-column
shape is preserved.

It contains 3 real REIGN countries x 2 years x 2 months
(Mexico, United States, Sweden; 2020 + 2021; January + August).
The selected slice exercises:

- 3 distinct country display names (Mexico -> ``"Mexico"``,
  United States -> ``"USA"``, Sweden -> ``"Sweden"``).
- 2 years (2020, 2021) to exercise the year filter and the
  year-window computation in the manifest.
- 2 months (1, 8) to exercise the month column in
  ``source_row_reference`` (e.g.
  ``reign:USA:Trump:2020:1:leader``).
- The 8 catalog ``raw_column`` s are all present in the
  fixture's source rows (so the Stage 2 adapter can read the
  full long-format frame for any year in 2020-2021).

The fixture is intentionally small (3 countries x 2 years x
2 months = 12 leader-month rows; 12 rows x 8 catalog variables
= 96 ``source_observations`` rows for a no-year run) to keep
the test suite fast, but the column shape and cell value
encoding match the real bundle exactly. Per the architecture
design contract, the fixture must be a real-format slice --
not invented -- so the ``pandas.read_csv``-based read path can
be exercised end-to-end.

Idempotency: this script can be run repeatedly; the output is
deterministic given the same source CSV.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# --- Configuration ---

# 3 countries: MEX, USA, SWE. Chosen to cover:
#   - a country with Spanish diacritics (Mexico -> "Mexico" in
#     the REIGN display names; ``Mëxico`` is not in REIGN but
#     ``Mexico`` is),
#   - the US (USA), which has the longest REIGN coverage,
#   - a European country (Sweden), which has a long history of
#     parliamentary democracy.
_COUNTRIES: tuple[str, ...] = ("Mexico", "USA", "Sweden")

# 2 years are sufficient to exercise the year filter and the
# year-window computation; 2020 and 2021 are the last 2 years
# in the live REIGN bundle.
_YEARS: tuple[int, ...] = (2020, 2021)

# 2 months (1, 8) to exercise the month column in
# ``source_row_reference`` and to ensure the per-month
# granularity is preserved.
_MONTHS: tuple[int, ...] = (1, 8)

# Real input file (relative to project root).
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_INPUT_CSV: Path = (
    _PROJECT_ROOT
    / "data"
    / "raw"
    / "reign"
    / "REIGN_2021_8.csv"
)

# Output fixture path.
_OUTPUT_CSV: Path = Path(__file__).resolve().parent / "sample.csv"


def build_sample_csv(
    input_path: Path = _INPUT_CSV,
    output_path: Path = _OUTPUT_CSV,
    *,
    countries: tuple[str, ...] = _COUNTRIES,
    years: tuple[int, ...] = _YEARS,
    months: tuple[int, ...] = _MONTHS,
) -> Path:
    """Build the fixture CSV from a slice of the real raw CSV.

    Args:
        input_path: absolute path to the real raw CSV (UTF-8,
            34.4 MB).
        output_path: absolute path to write the fixture to.
        countries: the country display names to keep.
        years: the years to keep.
        months: the months to keep.

    Returns:
        The output path.

    Raises:
        FileNotFoundError: if the input CSV is missing.
    """
    if not input_path.is_file():
        raise FileNotFoundError(
            f"REIGN raw CSV not found at {input_path}. "
            "Phase C acquisition must stage the file before tests can run.",
        )

    # Read the real CSV. ``usecols`` and the year/month filters
    # keep the in-memory frame small.
    df = pd.read_csv(input_path)
    df = df[
        df["country"].isin(list(countries))
        & df["year"].isin(list(years))
        & df["month"].isin(list(months))
    ].copy()
    # Preserve the original column order; reset the index.
    df = df.reset_index(drop=True)

    if df.empty:
        raise ValueError(
            f"No rows found for countries={countries}, years={years}, "
            f"months={months} in {input_path}. Check that the filters "
            "match the real bundle."
        )

    # Write the fixture CSV. UTF-8 is the real bundle's encoding;
    # the Stage 2 reader (pandas.read_csv) will read it back with
    # the default UTF-8 codec.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(
        f"Wrote {len(df)} leader-month rows x {len(df.columns)} "
        f"columns to {output_path} (UTF-8).",
        file=sys.stderr,
    )
    return output_path


if __name__ == "__main__":
    # Allow running from project root or from the fixtures dir.
    build_sample_csv()
