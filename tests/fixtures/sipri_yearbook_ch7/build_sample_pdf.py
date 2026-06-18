"""Build the SIPRI Yearbook Ch.7 test fixture PDF using reportlab.

Run from the repository root to regenerate the fixture:
    python tests/fixtures/sipri_yearbook_ch7/build_sample_pdf.py

The fixture is a minimal 1-page PDF that reproduces the canonical
Table 7.1 layout from the live SIPRI Yearbook 2024 PDF (YB24 07 WNF.pdf).
It contains 5 country rows (the 5 P5 members) + 1 aggregate "Total" row
(the aggregate is returned by read_table_7_1 and filtered out by the
non-country denylist in the Stage 2 adapter).

The fixture exercises all 3 sentinel patterns:
  - UK retired = en-dash "–" (nil/negligible value)
  - France retired = ".." (not applicable)
  - China deployed = "c. 24 j" (approximately 24, footnote j)

The test assertions do NOT change the fixture to match the tests —
the fixture is the source of truth per the architecture design contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

# ---------------------------------------------------------------------------
# Table 7.1 fixture data (from the live YB24 PDF, §3.4 architecture design)
# ---------------------------------------------------------------------------
#
# Columns in the PDF table: Country | Deployed | Stored | Stockpile total |
#                              Retired | Total inventory
#
# The fixture uses the live YB24 values for the 5 P5 countries:
#   USA:     deployed=1770d, stored=1938e, stockpile_total=3708,
#            retired=1336f, total_inventory=5044
#   Russia:  deployed=1710g, stored=2670h, stockpile_total=4380,
#            retired=1200f,  total_inventory=5580
#   UK:      deployed=120,  stored=105,  stockpile_total=225,
#            retired=– (nil), total_inventory=225
#   France:  deployed=280,  stored=10,   stockpile_total=290,
#            retired=.. (N/A), total_inventory=290
#   China:   deployed=c. 24j, stored=476, stockpile_total=500,
#            retired=–, total_inventory=500
#   Total:   (aggregate — filtered out by _SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS)
#
# Footnotes in the live PDF:
#   d — Deployed warheads on operational ICBMs, SLBMs, and strategic bombers.
#   e — Warheads in central storage.
#   f — Retired warheads awaiting dismantlement.
#   g,h — Similar to d,e for Russia.
#   j — SIPRI assesses that, as of Jan. 2024, China might have started to
#       deploy a small number of its warheads (c. 24).
#
# The fixture stores the cell text exactly as the PDF would render it,
# including the "c. " prefix and footnote letter suffix for annotated cells.
# ---------------------------------------------------------------------------

# Header row
HEADER = [
    "Country",
    "Deployed",
    "Stored",
    "Stockpile\ntotal",
    "Retired",
    "Total\ninventory",
]

# Data rows (strings — stored exactly as the PDF cell would appear)
#
# Format per row:
#   (country_display_name, deployed_str, stored_str, stockpile_total_str,
#    retired_str, total_inventory_str)
#
# Key sentinels in fixture:
#   UK retired = "–"  (en-dash, U+2013)  → coerced to 0 in normalized_value
#   France retired = ".." (two dots)      → coerced to None in normalized_value
#   China deployed = "c. 24 j" (c. prefix + footnote j)
#                                        → coerced to 24 in normalized_value
#                                        → raw_value = "c. 24 j"
#
ROWS = [
    # (country, deployed, stored, stockpile_total, retired, total_inventory)
    (
        "United States",
        "1 770 d",
        "1 938 e",
        "3 708",
        "1 336 f",
        "5 044",
    ),
    (
        "Russia",
        "1 710 g",
        "2 670 h",
        "4 380",
        "1 200 f",
        "5 580",
    ),
    (
        "United Kingdom",
        "120",
        "105",
        "225",
        "–",  # nil/negligible → 0 in normalized_value
        "225",
    ),
    (
        "France",
        "280",
        "10",
        "290",
        "..",  # not applicable → None in normalized_value
        "290",
    ),
    (
        "China",
        "c. 24 j",  # circa 24, footnote j
        "476",
        "500",
        "–",
        "500",
    ),
    # "Total" is filtered out by _SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS
    (
        "Total",
        "3 904",
        "5 681",
        "9 585",
        "2 536",
        "12 121",
    ),
]


def build_sample_pdf(output_path: Path) -> None:
    """Build the fixture PDF at the given path."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    # Assemble table data
    table_data: list[list[str]] = [HEADER]
    for row in ROWS:
        table_data.append(list(row))

    # Column widths: Country wide, then equal numeric columns
    col_widths = [3.5 * cm] + [2.2 * cm] * 5

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    BLUE_HEADER = colors.HexColor("#1F4E79")
    LIGHT_BLUE = colors.HexColor("#D6E4F0")
    WHITE = colors.white
    LIGHT_GRAY = colors.HexColor("#F5F5F5")

    tbl.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), BLUE_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                # Data rows
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                # Alternating row colours (skip Total row at index -1 for alt)
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, LIGHT_GRAY]),
                # Last row (Total) — slightly bolder
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, -1), (-1, -1), LIGHT_BLUE),
                # Leftmost column
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                # Padding
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ]
        )
    )

    doc.build([tbl])
    print(f"Wrote: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    # Allow running from project root or from the fixtures dir
    fixtures_dir = Path(__file__).resolve().parent
    output_path = fixtures_dir / "sample.pdf"
    build_sample_pdf(output_path)
