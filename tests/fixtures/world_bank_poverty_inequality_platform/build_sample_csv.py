"""Build the World Bank Poverty and Inequality Platform (PIP)
test fixture CSV (and JSON wrapper).

Run from the repository root to regenerate the fixtures:

    python tests/fixtures/world_bank_poverty_inequality_platform/build_sample_csv.py

The fixtures are intentionally minimal so a test failure is
easy to diagnose. The fixture exercises:

- 6 cached country-year rows (hand-authored, no real World
  Bank PIP claims). The country labels are SYNTHETIC
  (``"Country A"`` / ``"Country B"`` etc.) so the fixture does
  NOT make historical factual claims about real poverty /
  inequality data per the task brief: "prefer synthetic
  non-real country labels if it tests parser mechanics
  without factual assertions".
- All 11 required columns, including the required release-basis
  fields ``version_id`` and ``ppp_version``. ``ppp_base_year`` is
  included as an extra audit field.
- The full 3-indicator catalog coverage (headcount + poverty
  gap + Gini) -- each row exercises every catalog indicator.
- The per-row PPP version + reporting level + welfare type +
  poverty line as documented source-native cells preserved
  verbatim on the audit-trail extension payload (the
  transform never invents a value from missing source-native
  data).
- One row with all-numeric cells (the canonical happy path
  row), one row with one blank numeric cell (the
  ``value_type='missing'`` sentinel path), and one row with
  one non-numeric cell (the non-numeric sentinel path) so
  the transform layer exercises the blank / non-numeric
  coercion matrix.
- One row outside the canonical 1960-2024 coverage envelope
  (``year=1900``) so the transform layer exercises the
  out-of-coverage year filter (the row is excluded from the
  canonical output set; the readiness envelope surfaces a
  structured ``YEAR_ABSENT`` warning on the request for
  ``years=(1900,)``).

The fixture is the source of truth per the architecture
design contract; the test assertions do NOT change the
fixture to match the tests.
"""

from __future__ import annotations

import json
from pathlib import Path

HEADER: tuple[str, ...] = (
    "country_code",
    "country_name",
    "year",
    "reporting_level",
    "welfare_type",
    "poverty_line",
    "headcount",
    "poverty_gap",
    "gini",
    "version_id",
    "ppp_version",
    "ppp_base_year",
)


# Hand-authored fixture rows. Country labels are SYNTHETIC
# so the fixture does NOT make historical factual claims
# about real World Bank PIP poverty / inequality data. The
# numeric headcount / poverty_gap / gini values are
# hand-chosen small floats so the per-indicator test math is
# trivial.
ROWS: tuple[dict[str, str], ...] = (
    {
        # Row 1: canonical happy path row (all numeric cells,
        # in-coverage year, full optional metadata).
        "country_code": "AAA",
        "country_name": "Country A",
        "year": "2018",
        "reporting_level": "national",
        "welfare_type": "consumption",
        "poverty_line": "1.9",
        "headcount": "0.054",
        "poverty_gap": "0.012",
        "gini": "32.4",
        "version_id": "20260324_2021",
        "ppp_version": "2021",
        "ppp_base_year": "2021",
    },
    {
        # Row 2: blank numeric cell (headcount) -- the
        # ``value_type='missing'`` sentinel path. Other cells
        # are populated so the Gini / poverty_gap observations
        # for the row are still numeric.
        "country_code": "AAA",
        "country_name": "Country A",
        "year": "2020",
        "reporting_level": "national",
        "welfare_type": "consumption",
        "poverty_line": "3.2",
        "headcount": "",
        "poverty_gap": "0.025",
        "gini": "33.1",
        "version_id": "20260324_2021",
        "ppp_version": "2021",
        "ppp_base_year": "2021",
    },
    {
        # Row 3: non-numeric numeric cell (gini) -- the
        # non-numeric sentinel path. Other cells are
        # populated so the headcount / poverty_gap observations
        # for the row are still numeric.
        "country_code": "BBB",
        "country_name": "Country B",
        "year": "2017",
        "reporting_level": "national",
        "welfare_type": "income",
        "poverty_line": "5.5",
        "headcount": "0.187",
        "poverty_gap": "0.063",
        "gini": "n.a.",
        "version_id": "20260324_2021",
        "ppp_version": "2021",
        "ppp_base_year": "2021",
    },
    {
        # Row 4: in-coverage year, all numeric cells, required
        # version_id present.
        "country_code": "CCC",
        "country_name": "Country C",
        "year": "2019",
        "reporting_level": "national",
        "welfare_type": "consumption",
        "poverty_line": "1.9",
        "headcount": "0.221",
        "poverty_gap": "0.078",
        "gini": "40.2",
        "version_id": "20260324_2021",
        "ppp_version": "2021",
        "ppp_base_year": "2021",
    },
    {
        # Row 5: in-coverage year, all numeric cells.
        "country_code": "DDD",
        "country_name": "Country D",
        "year": "2015",
        "reporting_level": "rural",
        "welfare_type": "consumption",
        "poverty_line": "1.9",
        "headcount": "0.310",
        "poverty_gap": "0.114",
        "gini": "38.7",
        "version_id": "20260324_2021",
        "ppp_version": "2021",
        "ppp_base_year": "2021",
    },
    {
        # Row 6: out-of-coverage year (1900). The transform
        # excludes the row from the canonical output; the
        # readiness envelope surfaces a structured
        # ``YEAR_ABSENT`` warning on the request.
        "country_code": "EEE",
        "country_name": "Country E",
        "year": "1900",
        "reporting_level": "national",
        "welfare_type": "consumption",
        "poverty_line": "1.9",
        "headcount": "0.500",
        "poverty_gap": "0.250",
        "gini": "45.0",
        "version_id": "20260324_2021",
        "ppp_version": "2021",
        "ppp_base_year": "2021",
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


def _build_json() -> str:
    """Build the JSON wrapper payload.

    The cached World Bank PIP JSON shape mirrors the canonical
    CSV schema: a JSON array of objects keyed by the canonical
    column names. The reader parses the array, computes the
    canonical header (the union of every object's keys, in the
    order they first appear), and routes each object into a
    dict keyed by the header column names.
    """
    payload = [dict(row) for row in ROWS]
    return json.dumps(payload, indent=2)


def build_sample_fixtures(fixtures_dir: Path) -> tuple[Path, Path]:
    """Build the CSV + JSON fixtures under ``fixtures_dir``.

    Returns ``(csv_path, json_path)`` for the staged fixtures.
    """
    csv_path = fixtures_dir / "sample.csv"
    json_path = fixtures_dir / "sample.json"
    csv_path.write_text(_format_csv(), encoding="utf-8")
    json_path.write_text(_build_json(), encoding="utf-8")
    return csv_path, json_path


if __name__ == "__main__":
    fixtures_dir = Path(__file__).resolve().parent
    csv_out, json_out = build_sample_fixtures(fixtures_dir)
    print(f"Wrote: {csv_out}", flush=True)
    print(f"Wrote: {json_out}", flush=True)
