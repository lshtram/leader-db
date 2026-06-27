"""Build the SIPRI Arms Transfers test fixture CSV + JSON wrapper.

Run from the repository root to regenerate the fixtures:
    python tests/fixtures/sipri_arms_transfers/build_sample_csv.py

The fixtures are intentionally minimal so a test failure is
easy to diagnose. The fixture exercises:

- 6 cached transfer rows (hand-authored, no real SIPRI claims).
  The country labels are SYNTHETIC ("Country A", "Country B",
  etc.) so the fixture does NOT make historical factual claims
  per the task brief: "prefer synthetic non-real country labels
  if it tests parser mechanics without factual assertions".
- All 8 required columns + 7 optional columns.
- The SIPRI preamble / citation block (the lines that precede
  the documented header row, per the canonical SIPRI export
  contract). The preamble is preserved on the audit-trail
  ``extension["sipri_arms_transfers_preamble"]`` field on every
  emitted observation.
- Two cell quirks the parser must handle safely:
    * Row 2: ``Delivery year`` is "2012-2014" (range -- the
      parser extracts the first 4-digit year token as the
      canonical delivery year, preserving the verbatim range
      on ``extension["sipri_arms_transfers_delivery_year_raw"]``).
    * Row 3: ``TIV (delivered)`` is "n.a." (string sentinel
      -- the parser emits
      ``value=None`` / ``value_type="missing"`` with the
      verbatim raw cell text on ``extension.raw_value``).
- One CSV fixture (``sample.csv``) + one base64-JSON wrapper
  fixture (``sample.json``) so the tests can exercise BOTH
  cached shapes per the task brief.

The fixture is the source of truth per the architecture
design contract; the test assertions do NOT change the
fixture to match the tests.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

HEADER: tuple[str, ...] = (
    "Supplier",
    "Recipient",
    "Order year",
    "Order date",
    "Delivery year",
    "Delivery date",
    "Designation",
    "Description",
    "Weapon category",
    "Status",
    "Numbers ordered",
    "Numbers delivered",
    "TIV (ordered)",
    "TIV (delivered)",
    "Comments",
)


# Hand-authored fixture rows. Country labels are SYNTHETIC
# ("Country A", "Country B", "Country C") so the fixture does
# NOT make historical factual claims about real SIPRI Arms
# Transfers data. The numeric TIV / number values are
# hand-chosen small integers so the aggregate test math is
# trivial.
ROWS: tuple[dict[str, str], ...] = (
    {
        "Supplier": "Country A",
        "Recipient": "Country B",
        "Order year": "2010",
        "Order date": "2010-03-15",
        "Delivery year": "2012",
        "Delivery date": "2012-08-22",
        "Designation": "Fixture Fighter Mk1",
        "Description": "Synthetic multirole fighter",
        "Weapon category": "Combat aircraft",
        "Status": "Delivered",
        "Numbers ordered": "24",
        "Numbers delivered": "24",
        "TIV (ordered)": "876",
        "TIV (delivered)": "876",
        "Comments": "Synthetic fixture row 1",
    },
    {
        "Supplier": "Country A",
        "Recipient": "Country C",
        "Order year": "2014",
        "Order date": "2014-11-04",
        "Delivery year": "2016-2018",
        "Delivery date": "",
        "Designation": "Fixture Trainer Mk2",
        "Description": "Synthetic trainer aircraft",
        "Weapon category": "Trainer aircraft",
        "Status": "Delivered",
        "Numbers ordered": "12",
        "Numbers delivered": "12",
        "TIV (ordered)": "120",
        "TIV (delivered)": "120",
        "Comments": "Synthetic fixture row 2 (delivery year range)",
    },
    {
        "Supplier": "Country B",
        "Recipient": "Country C",
        "Order year": "2008",
        "Order date": "2008-06-01",
        "Delivery year": "2010",
        "Delivery date": "2010-09-30",
        "Designation": "Fixture Frigate Mk3",
        "Description": "Synthetic frigate",
        "Weapon category": "Naval",
        "Status": "Delivered",
        "Numbers ordered": "2",
        "Numbers delivered": "2",
        "TIV (ordered)": "540",
        "TIV (delivered)": "n.a.",
        "Comments": "Synthetic fixture row 3 (TIV missing sentinel)",
    },
    {
        "Supplier": "Country A",
        "Recipient": "Country B",
        "Order year": "2018",
        "Order date": "2018-02-20",
        "Delivery year": "2020",
        "Delivery date": "2020-11-05",
        "Designation": "Fixture UAV Mk4",
        "Description": "Synthetic UAV",
        "Weapon category": "UAV",
        "Status": "Delivered",
        "Numbers ordered": "8",
        "Numbers delivered": "8",
        "TIV (ordered)": "44",
        "TIV (delivered)": "44",
        "Comments": "Synthetic fixture row 4",
    },
    {
        "Supplier": "Country C",
        "Recipient": "Country A",
        "Order year": "2011",
        "Order date": "2011-07-10",
        "Delivery year": "2013",
        "Delivery date": "2013-04-12",
        "Designation": "Fixture Radar Mk5",
        "Description": "Synthetic radar system",
        "Weapon category": "Sensors",
        "Status": "Delivered",
        "Numbers ordered": "1",
        "Numbers delivered": "1",
        "TIV (ordered)": "60",
        "TIV (delivered)": "60",
        "Comments": "Synthetic fixture row 5",
    },
    {
        "Supplier": "Country B",
        "Recipient": "Country A",
        "Order year": "2019",
        "Order date": "2019-12-01",
        "Delivery year": "2021",
        "Delivery date": "2021-08-15",
        "Designation": "Fixture Missile Mk6",
        "Description": "Synthetic missile system",
        "Weapon category": "Missiles",
        "Status": "Delivered",
        "Numbers ordered": "100",
        "Numbers delivered": "100",
        "TIV (ordered)": "230",
        "TIV (delivered)": "230",
        "Comments": "Synthetic fixture row 6",
    },
)


# Canonical SIPRI preamble / citation block (the lines that
# precede the documented header row in the canonical SIPRI
# Trade Register export). The unified adapter preserves these
# lines on the audit-trail extension payload so downstream code
# can recover the verbatim SIPRI citation block. The preamble
# is informational only -- the transform layer does NOT branch
# on the preamble contents.
PREAMBLE_LINES: tuple[str, ...] = (
    "# SIPRI Arms Transfers Database Trade Register",
    "# Source: https://www.sipri.org/databases/armstransfers",
    "# Copyright (c) SIPRI 2026.",
    "# Database use must be non-commercial and in line with SIPRI fair-use policy.",
    "# Year coverage: 1950-2025. Updated 2026-03-09.",
    "# This fixture is a hand-authored synthetic sample for unit tests;",
    "# the country labels and TIV values are NOT real SIPRI data.",
)


def _format_csv() -> str:
    """Format the canonical CSV text including preamble + header + rows."""
    lines: list[str] = list(PREAMBLE_LINES)
    # CSV-quote every column header so the documented header
    # schema survives the SIPRI preamble's hash-prefix lines.
    lines.append(",".join(f'"{col}"' for col in HEADER))
    for row in ROWS:
        cells = [
            f'"{row.get(col, "")}"' for col in HEADER
        ]
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def _build_base64_json() -> str:
    """Build the base64-JSON wrapper payload."""
    csv_text = _format_csv()
    encoded = base64.b64encode(
        csv_text.encode("utf-8"),
    ).decode("ascii")
    payload = {
        "data": encoded,
        "metadata": {
            "source": "SIPRI Arms Transfers Trade Register",
            "year_coverage": "1950-2025",
            "format": "trade_register_csv",
        },
    }
    return json.dumps(payload, indent=2)


def build_sample_fixtures(fixtures_dir: Path) -> tuple[Path, Path]:
    """Build the CSV + base64-JSON fixtures under ``fixtures_dir``.

    Returns ``(csv_path, json_path)`` for the staged fixtures.
    """
    csv_path = fixtures_dir / "sample.csv"
    json_path = fixtures_dir / "sample.json"
    csv_path.write_text(_format_csv(), encoding="utf-8")
    json_path.write_text(_build_base64_json(), encoding="utf-8")
    return csv_path, json_path


if __name__ == "__main__":
    fixtures_dir = Path(__file__).resolve().parent
    csv_out, json_out = build_sample_fixtures(fixtures_dir)
    print(f"Wrote: {csv_out}", flush=True)
    print(f"Wrote: {json_out}", flush=True)
