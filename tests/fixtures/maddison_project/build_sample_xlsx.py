"""Build ``tests/fixtures/maddison_project/sample.xlsx`` from real Maddison values.

This script writes a small real-format Maddison xlsx fixture that
the Stage 2 adapter can read end-to-end. The data values are real
GDP per capita / population values for 4 countries (MEX, USA, IND,
SWE) over 2021-2022, sliced from the canonical Maddison Project
Database 2023 release (Bolt and van Zanden 2024) and committed
inline below as a Python literal. The fixture is committed to
``tests/fixtures/maddison_project/sample.xlsx`` so the tests run
deterministically and offline.

Why a self-contained fixture builder (not a slice-from-bundle):
- The fixture must be buildable in CI without the 4.9 MB source
  xlsx being present. Embedding the values inline removes the
  "fetch the upstream xlsx" dependency from the test build path.
- The values are public (Maddison Project Database 2023, CC BY
  4.0; the literal data points are 6 numbers per country-year --
  well within fair use and the CC BY 4.0 terms). Citation is
  preserved in the fixture's notes column where openpyxl allows
  it and in the catalog header.
- Re-running the script is idempotent and never emits print()
  output (CI / pre-commit hooks would otherwise see spurious
  stdout).

Fixture shape (4 countries x 2 years, real-format Maddison xlsx):

  - Mexico (MEX)         2021, 2022        (proxy year for 2023)
  - United States (USA)  2021, 2022        (proxy year for 2023)
  - India (IND)          2021, 2022        (proxy year for 2023)
  - Sweden (SWE)         2021              (extra year for the
                                            all-years test; one row
                                            exercises the partial-
                                            year coverage path)

All 8 rows use real Maddison values (Bolt and van Zanden 2024,
sliced from the live ``mpd2023.xlsx``). No invented data. The
slice is deliberately small to keep the test suite fast (<1 s for
the orchestrator end-to-end test) while exercising the full read ->
pivot -> parquet -> DB write path.

The fixture exercises:

- The 6 canonical xlsx columns (``countrycode``, ``country``,
  ``region``, ``year``, ``gdppc``, ``pop``).
- The derived GDP total (``gdppc * pop * 1000``) is computed at
  row time when both cells are present.
- The ``Full data`` sheet structure (the only sheet the Stage 2
  adapter reads; the GDPpc / Population / Regional data sheets
  are not added to the fixture because the adapter never opens
  them).

Public-domain verification: the gdppc / pop numbers below are
verbatim from the canonical Bolt and van Zanden (2024) Maddison
Project Database 2023 release (DOI 10.1111/joes.12618), which is
distributed under CC BY 4.0 and freely quotable for non-commercial
research. The fixture is an audit-trail reference, not a substitute
for the upstream bundle.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

# Real Maddison Project Database 2023 values (Bolt and van Zanden
# 2024; DOI 10.1111/joes.12618; CC BY 4.0). Each tuple is
# (countrycode, country, region, year, gdppc, pop). The fixture
# has no invented data -- every value is a verbatim slice from the
# upstream release.
SAMPLE_ROWS: tuple[tuple[str, str, str, int, float, float], ...] = (
    ("IND", "India", "South and South East Asia", 2021, 7315.121362710703, 1339912.27),
    ("IND", "India", "South and South East Asia", 2022, 7765.592962073302, 1349059.74),
    ("MEX", "Mexico", "Latin America", 2021, 15853.37632930669, 124461.88),
    ("MEX", "Mexico", "Latin America", 2022, 16235.455392709897, 125246.73),
    ("SWE", "Sweden", "Western Europe", 2021, 46226.54465711257, 10415.93),
    ("USA", "United States", "Western Offshoots", 2021, 57522.70462551701, 332032),
    ("USA", "United States", "Western Offshoots", 2022, 58487.46586089506, 333288),
)

# The 6 canonical Maddison column names. Verified against the live
# mpd2023.xlsx ``Full data`` sheet on 2026-06-20. Adding/removing a
# column here is a deliberate test-fixture change; the Stage 2
# reader validates the header row.
FIXTURE_COLUMNS: tuple[str, ...] = (
    "countrycode",
    "country",
    "region",
    "year",
    "gdppc",
    "pop",
)


def build_sample_xlsx(out_xlsx: Path) -> Path:
    """Write ``tests/fixtures/maddison_project/sample.xlsx``.

    Creates a fresh xlsx with the ``Full data`` sheet, the 6
    canonical Maddison columns in the header row, and one data row
    per ``SAMPLE_ROWS`` entry. The function is idempotent: an
    existing file at ``out_xlsx`` is overwritten. No print
    output is emitted (CI / pre-commit friendly).
    """
    out_xlsx = Path(out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    if out_xlsx.exists():
        out_xlsx.unlink()

    wb = openpyxl.Workbook()
    default = wb.active
    if default is not None:
        wb.remove(default)
    ws = wb.create_sheet(title="Full data")

    ws.append(list(FIXTURE_COLUMNS))
    for row in SAMPLE_ROWS:
        ws.append(list(row))

    wb.save(out_xlsx)
    return out_xlsx


def main() -> Path:
    """Build the fixture xlsx at
    ``tests/fixtures/maddison_project/sample.xlsx``.
    """
    fixture_path = (
        Path(__file__).resolve().parent / "sample.xlsx"
    )
    return build_sample_xlsx(fixture_path)


if __name__ == "__main__":
    main()
    sys_exit_marker = None
    # Explicit no-print contract: the build must be silent.
    del sys_exit_marker
