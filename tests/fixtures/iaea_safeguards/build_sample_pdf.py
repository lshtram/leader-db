"""Build the IAEA Safeguards test fixture PDF using reportlab.

Run from the repository root to regenerate the fixture:
    python tests/fixtures/iaea_safeguards/build_sample_pdf.py

The fixture is a minimal 1-page PDF that reproduces the canonical
IAEA Safeguards Status List layout (verified 2026-06-27 against
the published document at
https://www.iaea.org/sites/default/files/20/01/sg-agreements-comprehensive-status.pdf).

It contains 5 synthetic country rows + 1 aggregate row (the
aggregate row is filtered out by the readiness gate's
``local_files`` / canonical-header validation because the
"Region" column does NOT carry the canonical 5 columns).

The fixture carries the 5 canonical required columns:

- State -- IAEA's source-native country display name (NOT ISO3).
- Safeguards Agreement -- the presence / status of a
  Comprehensive Safeguards Agreement (CSA) for the State.
- INFCIRC -- the IAEA document identifier for the agreement.
- Additional Protocol -- the AP status (Signed / Approved /
  In Force / Not in Force / Not Signed).
- Small Quantities Protocol -- the SQP status (Modified /
  Original / Not applicable / Not in Force).

The fixture exercises all four cell-text patterns (full status,
N/A for non-States, blank INFCIRC for non-States, "Modified"
SQP variant) and is the source of truth per the architecture
design contract -- the test assertions do NOT change the
fixture to match the tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Header row (matches the canonical IAEA status-list column order).
# Single-line headers (no \n separators) so the pdfplumber
# ``extract_tables`` header detection does not break on the
# wrapped cell text -- the canonical IAEA status list is
# typically rendered with single-line column headers.
# ---------------------------------------------------------------------------
HEADER = [
    "State",
    "Safeguards Agreement",
    "INFCIRC",
    "Additional Protocol",
    "Small Quantities Protocol",
]

# Synthetic country rows (NOT real IAEA data). The fixture is
# small on purpose -- the test suite asserts 5 fixture rows
# (one per indicator x one row each = 25 observations for a
# full bundle request) so the parser mechanics are proven
# without redistributing the real IAEA table.
ROWS = [
    # (state, safeguards_agreement, infcirc, additional_protocol,
    #  small_quantities_protocol)
    (
        "Country Alpha",
        "In Force: 153",
        "INFCIRC/153",
        "In Force",
        "Modified",
    ),
    (
        "Country Bravo",
        "In Force: 153",
        "INFCIRC/153",
        "Signed",
        "Original",
    ),
    (
        "Country Charlie",
        "Not in Force: 66",
        "INFCIRC/66",
        "Not Signed",
        "Not applicable",
    ),
    (
        "Country Delta",
        "N/A",
        "",
        "N/A",
        "Not applicable",
    ),
    (
        "Country Echo",
        "In Force: 153",
        "INFCIRC/153",
        "Not Signed",
        "Modified",
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

    styles = getSampleStyleSheet()
    title = Paragraph(
        "<b>STATUS LIST</b><br/>"
        "<i>Conclusion of Safeguards Agreements, Additional "
        "Protocols and Small Quantities Protocols</i><br/>"
        "(status as of 31 December 2025; synthetic fixture "
        "for the clean IAEA Safeguards adapter)",
        styles["Normal"],
    )

    # Assemble table data
    table_data: list[list[str]] = [HEADER]
    for row in ROWS:
        table_data.append(list(row))

    # Column widths: hand-tuned so "Additional Protocol" and
    # "Small Quantities Protocol" fit on a single line in the
    # reportlab Helvetica-Bold 9pt header (the longest header
    # cells). Page A4 = 21cm wide; 1.5cm margins on each side
    # leave 18cm usable; column totals must equal 18cm to
    # avoid reportlab clipping the rightmost cell.
    col_widths = [3.5 * cm, 3.5 * cm, 2.5 * cm, 4.0 * cm, 4.5 * cm]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    BLUE_HEADER = colors.HexColor("#1F4E79")
    LIGHT_GRAY = colors.HexColor("#F5F5F5")
    WHITE = colors.white

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
                ("ALIGN", (1, 1), (-1, -1), "LEFT"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                # Alternating row colours
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
                # Leftmost column bold
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                # Padding
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ]
        )
    )

    doc.build([title, Spacer(1, 0.5 * cm), tbl])
    print(f"Wrote: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    # Allow running from project root or from the fixtures dir.
    fixtures_dir = Path(__file__).resolve().parent
    output_path = fixtures_dir / "sample.pdf"
    build_sample_pdf(output_path)
