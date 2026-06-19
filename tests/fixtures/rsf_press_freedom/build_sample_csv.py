"""Build the RSF test fixture CSVs from the real raw bundle.

Run from the repository root to (re)generate the fixtures::

    python tests/fixtures/rsf_press_freedom/build_sample_csv.py

The fixtures are real-format slices of the canonical RSF annual
files at ``data/raw/rsf_press_freedom/rsf_press_freedom_<year>.csv``.
Every cell value is copied verbatim from the real bundle; the
semicolon delimiter, comma decimal separator, and encoding are
preserved.

The fixtures cover 3 distinct year-schema generations so the tests
exercise the pre/post-2022 schema break:

- ``rsf_press_freedom_2002_sample.csv`` -- 2002 file, 16-col wide
  format. Pre-2022 schema: score column is ``Score N``, rank column
  is ``Rank N``; no component-context columns. Country selection:
  MEX, USA, NGA (one with non-empty data, one with empty Score N
  for the empty-cell-drop test, one with empty pre-2022 cells).

- ``rsf_press_freedom_2022_sample.csv`` -- 2022 file, 22-col wide
  format with 181 blank separator rows. The blank-row filter test
  must run against this file. The 2022 file uses ``Score`` (not
  ``Score N``) and ``Rank`` (not ``Rank N``) as the column names;
  the reader resolves the logical ``raw_column`` to the actual
  year-specific column.

- ``rsf_press_freedom_2023_sample.csv`` -- 2023 file, 25-col wide
  format with all 5 component-context columns present
  (``Political Context``, ``Economic Context``, ``Legal Context``,
  ``Social Context``, ``Safety``). The component-extraction test
  must run against this file.

Idempotency: this script can be run repeatedly; the output is
deterministic given the same source CSVs. The fixture data is a
real-format slice (no invented data) per the architecture §8
fixture contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# --- Configuration ---

# 5 countries for the pre-2022 fixture: MEX, USA, NGA + 2 fillers
# for row-count diversity. The chosen set has at least one
# pre-2022 row with empty cells (NGA in the real bundle has empty
# cells in early-year rows for some indicators).
_PRE_2022_COUNTRIES: tuple[str, ...] = ("MEX", "USA", "NGA", "FIN", "NOR")

# 5 countries for the 2022 fixture (blank-row test). The 2022 file
# has 181 blank separator rows; we keep all 5 with their original
# positions intact so the blank-row filter test exercises the real
# pattern.
_2022_COUNTRIES: tuple[str, ...] = ("NOR", "DNK", "SWE", "USA", "NGA")

# 5 countries for the 2023 fixture (component test). The 2023 file
# has the full 25-col wide format with all 5 component-context
# columns; we pick 5 countries covering the indicator range.
_POST_2022_COUNTRIES: tuple[str, ...] = ("NOR", "USA", "SWE", "MEX", "NGA")

_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_RAW_DIR: Path = _PROJECT_ROOT / "data" / "raw" / "rsf_press_freedom"
_OUTPUT_DIR: Path = Path(__file__).resolve().parent


def _build_year_sample_csv(
    raw_filename: str,
    output_filename: str,
    iso3_codes: tuple[str, ...],
) -> Path:
    """Build one year-fixture CSV by slicing the real raw CSV.

    Reads the source CSV with the same encoding + delimiter +
    dtype conventions the production reader uses, keeps the rows
    for the requested ISO3 codes verbatim, and writes back with the
    original encoding so the fixture is byte-identical to the
    production input minus the dropped rows.
    """
    src_path = _RAW_DIR / raw_filename
    if not src_path.is_file():
        raise FileNotFoundError(
            f"RSF raw CSV not found at {src_path}. Phase C acquisition "
            "must stage the file before tests can run.",
        )

    # Detect encoding via the same logic as the production reader.
    raw_bytes = src_path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    else:
        try:
            raw_bytes.decode("cp1252")
            encoding = "cp1252"
        except UnicodeDecodeError:
            encoding = "latin-1"

    df = pd.read_csv(
        src_path,
        sep=";",
        encoding=encoding,
        keep_default_na=False,
        dtype=str,
    )
    if "ISO" not in df.columns:
        raise ValueError(
            f"RSF source CSV {src_path} is missing the ISO column"
        )
    df = df[df["ISO"].isin(iso3_codes)].copy()
    # Preserve the original row order (the reader is order-
    # independent, but the fixture's literal order matches the
    # source).
    df = df.reset_index(drop=True)

    out_path = _OUTPUT_DIR / output_filename
    df.to_csv(out_path, sep=";", index=False, encoding=encoding)
    print(
        f"Wrote {len(df)} country row(s) x {len(df.columns)} column(s) "
        f"to {out_path.name} (encoding={encoding}, delimiter=';').",
        file=sys.stderr,
    )
    return out_path


def build_sample_csvs() -> list[Path]:
    """Build all 3 RSF year-fixture CSVs.

    Returns:
        The list of output paths in the order:
        2002 (pre-2022 shape) -> 2022 (transition shape with
        blank rows) -> 2023 (post-2022 shape with components).
    """
    written: list[Path] = []
    written.append(
        _build_year_sample_csv(
            "rsf_press_freedom_2002.csv",
            "rsf_press_freedom_2002_sample.csv",
            _PRE_2022_COUNTRIES,
        ),
    )
    written.append(
        _build_year_sample_csv(
            "rsf_press_freedom_2022.csv",
            "rsf_press_freedom_2022_sample.csv",
            _2022_COUNTRIES,
        ),
    )
    written.append(
        _build_year_sample_csv(
            "rsf_press_freedom_2023.csv",
            "rsf_press_freedom_2023_sample.csv",
            _POST_2022_COUNTRIES,
        ),
    )
    return written


if __name__ == "__main__":
    written = build_sample_csvs()
    print(
        f"Wrote {len(written)} fixture file(s).",
        file=sys.stderr,
    )
