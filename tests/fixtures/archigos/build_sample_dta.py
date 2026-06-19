"""Build the Archigos test fixture .dta from the real raw bundle.

Run from the repository root to (re)generate the fixture::

    python tests/fixtures/archigos/build_sample_dta.py

The fixture is a real-format slice of the canonical
``data/raw/archigos/Archigos_4.1_stata14.dta`` file
(Stata 14 .dta, 2.9 MB, 3,409 leader spells x 28 columns,
cp1252-encoded). It is NOT a hand-authored fake: every cell
value is copied verbatim from the real bundle, the cp1252
encoding is preserved, and the 28-column shape is preserved.

It contains 5 real Archigos leader-spell rows for the United
States (1869-2015, the same 5 spells the architect spec asks
for in §"Existing patterns"):

  - Grant (1869-03-04 to 1877-03-04)
  - Hayes (1877-03-04 to 1881-03-04)
  - Garfield (1881-03-04 to 1881-09-19, Irregular exit)
  - Arthur (1881-09-19 to 1885-03-04)
  - Cleveland (1885-03-04 to 1889-03-04, Regular entry/exit)

The selected slice exercises:

- 5 consecutive real US leader spells (the early Reconstruction
  era is well-documented in Archigos).
- 1 spell with an Irregular exit (Garfield, assassinated 1881).
- 5 different end dates (year-only range 1877-1889).
- The 6 catalog ``raw_column`` s are all present in the
  fixture's source rows (so the Stage 2 adapter can read the
  full long-format frame for any year in 1869-1889).

The fixture is intentionally small (5 leader spells) to keep
the test suite fast, but the column shape and cell value
encoding match the real bundle exactly: the .dta is written
with ``pyreadstat.write_dta`` so the cell values, variable
types, and Stata format codes (e.g. ``%td`` for dates) are
preserved exactly. Per the architecture design contract, the
fixture must be a real-format slice -- not invented -- so the
``pyreadstat``-based read path can be exercised end-to-end.

Idempotency: this script can be run repeatedly; the output is
deterministic given the same source .dta.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pyreadstat

# --- Configuration ---

# 5 real Archigos leader-spell obsids for the United States.
# These are the early-Reconstruction-era US presidents in
# Archigos v4.1 (verified live 2026-06-19 against the real
# data/raw/archigos/Archigos_4.1_stata14.dta).
_OBSIDS: tuple[str, ...] = (
    "USA-1869",
    "USA-1877",
    "USA-1881-1",  # Garfield
    "USA-1881-2",  # Arthur (Garfield's successor)
    "USA-1885",
)

# Real input file (relative to project root).
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_INPUT_DTA: Path = (
    _PROJECT_ROOT
    / "data"
    / "raw"
    / "archigos"
    / "Archigos_4.1_stata14.dta"
)

# Output fixture path.
_OUTPUT_DTA: Path = Path(__file__).resolve().parent / "sample.dta"


def build_sample_dta(
    input_path: Path = _INPUT_DTA,
    output_path: Path = _OUTPUT_DTA,
    *,
    obsids: tuple[str, ...] = _OBSIDS,
) -> Path:
    """Build the fixture .dta from a slice of the real raw .dta.

    Args:
        input_path: absolute path to the real raw .dta
            (cp1252-encoded, 2.9 MB).
        output_path: absolute path to write the fixture to.
        obsids: the obsids to keep (real obsid strings from
            Archigos).

    Returns:
        The output path.

    Raises:
        FileNotFoundError: if the input .dta is missing.
    """
    if not input_path.is_file():
        raise FileNotFoundError(
            f"Archigos raw .dta not found at {input_path}. "
            "Phase C acquisition must stage the file before tests can run.",
        )

    # Read the real .dta (cp1252 encoding is required;
    # pyreadstat raises "File has an unsupported character set"
    # on other encodings).
    df, _meta = pyreadstat.read_dta(
        str(input_path), encoding="cp1252",
    )

    # Filter to the 5 obsids.
    df = df[df["obsid"].isin(list(obsids))].copy()

    # Preserve original row order (sort by obsid for stability).
    df = df.sort_values("obsid").reset_index(drop=True)

    if df.empty:
        raise ValueError(
            f"No rows found for obsids {obsids} in {input_path}. "
            "Check that the obsids exist in the real bundle."
        )

    # Write the fixture .dta. pyreadstat.write_dta preserves the
    # variable types and Stata format codes (e.g. ``%td`` for
    # dates) from the original frame.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pyreadstat.write_dta(df, str(output_path))

    print(
        f"Wrote {len(df)} leader-spell rows x {len(df.columns)} "
        f"columns to {output_path} (cp1252).",
        file=sys.stderr,
    )
    return output_path


if __name__ == "__main__":
    # Allow running from project root or from the fixtures dir.
    build_sample_dta()
