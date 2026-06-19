"""Build the FAS Nuclear Notebook test fixture HTML.

Run from the repository root to (re)generate the fixture::

    python tests/fixtures/fas/build_sample_html.py

The fixture is a real-format slice of the FAS "Status of World
Nuclear Forces" page
(https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html).
The raw HTML was captured at probe time and lives at
``tmp/source-vetting-evidence/fas-nukestatus.html`` (the verbatim
~54 KB response from the FAS server, 398 lines). This script
slices the captured HTML to a small set of countries (5) plus the
header row, the aggregate TOTAL row, and the page footer to keep
the test suite fast and to verify the parser handles the
sentinels (``n.a.``, ``?``, ``<10``, ranges ``100-120``, footnote
letters).

If the raw capture is missing at the default location (the
``tmp/`` folder is gitignored), pass an explicit ``raw_capture``
argument on the CLI or via the ``build_sample_html`` function. The
default path intentionally points at the project-scoped ``tmp/``
folder rather than the system ``/tmp/`` so this script fails
loudly rather than silently reading from a stale system path.

The selected countries cover the real fixture scenarios:

- USA, Russia, China, UK, North Korea -- the 5 countries covering
  the indicator range (Russia/USA for high stockpile, North Korea
  for ``<10`` sentinel, China for the ``0j`` footnote letter).
- Real values from the captured FAS HTML are preserved verbatim
  (no invented data). The HTML structure matches the FAS server
  response shape (table id="table1" with 6 columns + meta date
  element) so the parser and HTTP layer can run against the
  fixture without modification.

Idempotency: this script can be run repeatedly; the output is
deterministic given the same raw HTML capture.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# --- Configuration ---

# 5 real countries covering the FAS table range. Each row has a
# different shape so the parser handles all sentinels:
#   - United States: footnote letters on multiple columns
#   - Russia: highest stockpile counts, footnote letters
#   - China: "0j" (0 with footnote j) + "?k" (unknown) sentinels
#   - United Kingdom: "160l" footnote letter + "n.a." sentinel
#   - North Korea: "<10" sentinel (less than 10)
_COUNTRIES: tuple[str, ...] = (
    "United States",
    "Russia",
    "China",
    "United Kingdom",
    "North Korea",
)

#: The raw capture from the FAS server (verbatim response). Default
#: points at the project-scoped ``tmp/`` folder (gitignored per
#: ``docs/local-data-store.md``); pass an explicit path to override.
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
_RAW_CAPTURE: Path = (
    _PROJECT_ROOT / "tmp" / "source-vetting-evidence" / "fas-nukestatus.html"
)

#: The output fixture path (committed to the repo).
_OUTPUT_PATH: Path = Path(__file__).resolve().parent / "sample.html"


def build_sample_html(
    raw_capture: Path = _RAW_CAPTURE,
    output_path: Path = _OUTPUT_PATH,
    *,
    countries: tuple[str, ...] = _COUNTRIES,
) -> Path:
    """Build the slim FAS Nuclear Notebook test fixture HTML.

    Reads the verbatim FAS HTML from ``raw_capture`` and writes a
    slim version to ``output_path`` containing only the header
    row, the 5 selected country rows, the aggregate TOTAL row,
    and the footer. Preserve the verbatim table structure
    (``<table id="table1">``) and meta date element so the parser
    and HTTP layer accept the fixture without modification.

    Args:
        raw_capture: the source HTML file with all 9 country rows.
        output_path: the destination path for the slim fixture.
        countries: the country names to keep.

    Returns:
        The output path written by this call.

    Raises:
        FileNotFoundError: if the raw capture is missing.
    """
    if not raw_capture.is_file():
        raise FileNotFoundError(
            f"Raw FAS HTML capture missing: {raw_capture}. Re-run "
            "the live probe to refresh."
        )
    raw_text = raw_capture.read_text(encoding="utf-8", errors="replace")

    # Extract the table block. The FAS page has
    # ``<table ... id="table1">...</table>`` twice (once as the
    # empty placeholder, once with the actual data); we keep
    # the second one.
    table_matches = list(
        re.finditer(
            r'<table[^>]+id="table1"[^>]*>(.*?)</table>',
            raw_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if len(table_matches) < 2:
        # Fallback: try a single-table extraction.
        if not table_matches:
            raise ValueError(
                "FAS raw HTML has no <table id=\"table1\"> block"
            )
        table_block = table_matches[0].group(0)
    else:
        table_block = table_matches[1].group(0)

    # Extract the table rows. We need:
    # - 1 header row
    # - 1 row per selected country
    # - 1 aggregate TOTAL row
    # - 1 footer row (with the notes paragraph)
    # Each row is a ``<tr>...</tr>`` block; we use a permissive
    # regex.
    row_pattern = re.compile(
        r"<tr[^>]*>.*?</tr>",
        re.IGNORECASE | re.DOTALL,
    )
    rows = row_pattern.findall(table_block)

    # Identify the index of each selected country row by parsing
    # the first <td> of each row. The first row is the header
    # (``Country`` in col 0); rows with non-empty col 0 that
    # match the whitelist are kept; the aggregate TOTAL row is
    # the one whose col 0 is empty but whose col 1 starts with
    # ``~``; the footer row is the one with ``colspan="6"``.
    slim_rows: list[str] = []
    for row in rows:
        # Extract the first cell text.
        first_cell_match = re.search(
            r"<td[^>]*>(.*?)</td>",
            row,
            re.IGNORECASE | re.DOTALL,
        )
        if first_cell_match is None:
            # No cells (e.g. header row with <th>); skip.
            continue
        first_cell_text = re.sub(
            r"<[^>]+>", "", first_cell_match.group(1)
        ).strip()
        # Replace HTML non-breaking-space entity (literal
        # ``&nbsp;`` in the source text, NOT the Unicode
        # non-breaking-space char ``\u00a0``) with empty.
        first_cell_text = (
            first_cell_text.replace("&nbsp;", "")
            .replace("\u00a0", "")
            .strip()
        )
        if first_cell_text == "Country":
            slim_rows.append(row)
            continue
        if first_cell_text in countries:
            slim_rows.append(row)
            continue
        if not first_cell_text:
            # Empty first cell = either the aggregate TOTAL row
            # or the footer row. We include both for parser
            # coverage (the reader filters them).
            slim_rows.append(row)
            continue

    # Reconstruct the table block with only the slim rows.
    table_open_match = re.search(
        r'<table[^>]+id="table1"[^>]*>',
        table_block,
        re.IGNORECASE,
    )
    if table_open_match is None:
        raise ValueError(
            "FAS table block missing the opening <table> tag"
        )
    slim_table = (
        table_open_match.group(0)
        + "\n".join(slim_rows)
        + "</table>"
    )

    # Replace the original table block (the second one) with the
    # slim version in the page HTML. The page header (with the
    # meta date) is preserved verbatim so the snapshot year is
    # still parseable from the fixture.
    # Find the position of the SECOND table-block (matches[1]).
    second_table_span = table_matches[1].span()
    slim_text = (
        raw_text[: second_table_span[0]]
        + slim_table
        + raw_text[second_table_span[1]:]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(slim_text, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    written = build_sample_html()
    print(
        f"Wrote {written} (header + {_COUNTRIES} country rows + "
        "TOTAL + footer).",
        file=sys.stderr,
    )
