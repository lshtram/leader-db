"""Build the CTBTO Treaty Status test fixture CSV.

Run from the repository root to regenerate the fixture:

    python tests/fixtures/ctbto_treaty_status/build_sample_csv.py

The fixture is intentionally minimal so a test failure is easy
to diagnose. The fixture exercises:

- 6 cached State rows (hand-authored, no real CTBTO claims).
  The state labels are SYNTHETIC ("State A", "State B", ...)
  so the fixture does NOT make historical factual claims per
  the task brief: "fixtures must not redistribute copied
  full table in outputs". The regions are SYNTHETIC too
  ("Region X" / "Region Y").
- All 4 required columns (``Region`` / ``State`` /
  ``Signature Date`` / ``Ratification Date``).
- The 3 documented signature / ratification status cell
  patterns:
    * Row 1: signed + ratified (signature date present +
      ratification date present).
    * Row 2: signed but NOT yet ratified (signature date
      present + ratification date empty).
    * Row 3: NOT signed + NOT ratified (both date cells
      empty). This row exercises the
      ``"not_signed"`` / ``"not_ratified"`` sentinel path --
      the transform never invents a signature / ratification
      status from empty / blank date cells.
    * Row 4: signed + ratified (both dates present).
    * Row 5: NOT signed + NOT ratified (both empty).
    * Row 6: signed + ratified (both present; the ratification
      date uses ISO 8601 format ``YYYY-MM-DD`` to exercise
      the optional ISO-date parsing path).
- The ISO 8601 signature / ratification date formats
  (``YYYY-MM-DD``) for rows 1, 2, 4, 6 and a free-form date
  format (``D-MMM-YYYY``) for row 6's ratification date so
  the test exercises the date-cell preservation contract.

The fixture is the source of truth per the architecture
design contract; the test assertions do NOT change the
fixture to match the tests.
"""

from __future__ import annotations

from pathlib import Path

HEADER: tuple[str, ...] = (
    "Region",
    "State",
    "Signature Date",
    "Ratification Date",
)


# Hand-authored fixture rows. State / Region labels are
# SYNTHETIC ("State A" / "Region X") so the fixture does NOT
# make historical factual claims about real CTBT signature /
# ratification data. The signature / ratification date cells
# exercise the documented empty-cell / filled-cell patterns.
ROWS: tuple[dict[str, str], ...] = (
    {
        "Region": "Region X",
        "State": "State A",
        "Signature Date": "1996-09-24",
        "Ratification Date": "1998-07-10",
    },
    {
        "Region": "Region X",
        "State": "State B",
        "Signature Date": "1996-09-25",
        "Ratification Date": "",
    },
    {
        "Region": "Region Y",
        "State": "State C",
        "Signature Date": "",
        "Ratification Date": "",
    },
    {
        "Region": "Region Y",
        "State": "State D",
        "Signature Date": "2012-06-15",
        "Ratification Date": "2014-03-04",
    },
    {
        "Region": "Region X",
        "State": "State E",
        "Signature Date": "",
        "Ratification Date": "",
    },
    {
        "Region": "Region Y",
        "State": "State F",
        "Signature Date": "2008-10-14",
        "Ratification Date": "12-Mar-2009",
    },
)


def _format_csv() -> str:
    """Format the canonical CSV text including header + rows."""
    lines: list[str] = []
    lines.append(",".join(f'"{col}"' for col in HEADER))
    for row in ROWS:
        cells = [f'"{row.get(col, "")}"' for col in HEADER]
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def build_sample_fixture(fixtures_dir: Path) -> Path:
    """Build the CSV fixture under ``fixtures_dir``.

    Returns the resolved CSV path.
    """
    csv_path = fixtures_dir / "sample.csv"
    csv_path.write_text(_format_csv(), encoding="utf-8")
    return csv_path


if __name__ == "__main__":
    fixtures_dir = Path(__file__).resolve().parent
    csv_out = build_sample_fixture(fixtures_dir)
    print(f"Wrote: {csv_out}", flush=True)
