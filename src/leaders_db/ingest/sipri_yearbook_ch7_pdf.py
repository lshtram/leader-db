"""Stage 2 -- SIPRI Yearbook Ch.7 PDF table extraction (REQ-SRC-002).

The **PDF parser** half of the SIPRI Yearbook Ch.7 adapter. The
first PDF-based reader in the pipeline: every prior Stage 2
adapter reads xlsx / CSV / zip-CSV / API JSON. Wraps
``pdfplumber`` to extract Table 7.1 from the YB24 07 WNF.pdf and
returns a list of dicts (one per country row).

Owns:

- :func:`read_table_7_1` -- the public PDF read.
- :data:`EN_DASH_SENTINEL` / :data:`DOTS_SENTINEL` -- the
  literal missing-value tokens (``"-"`` and ``".."``).
- :data:`_FOOTNOTE_LETTER_RE` -- the regex for stripping the
  ``"c. "`` prefix and footnote letter from numeric cells.
- :func:`_coerce_cell_to_int` -- turn a Table 7.1 cell into
  ``(value, raw_value)``.

The read orchestrator
(:func:`sipri_yearbook_ch7_io.read_sipri_yearbook_ch7`) calls
:func:`read_table_7_1` and does the long -> wide pivot.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pdfplumber

_logger = logging.getLogger(__name__)

__all__ = ["read_table_7_1"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Table 7.1 en-dash sentinel (U+2013). Per the Table 7.1 legend,
#: this means "nil or a negligible value". The Stage 2 read
#: coerces it to ``0`` in ``normalized_value`` (and preserves the
#: literal in ``raw_value``).
EN_DASH_SENTINEL: str = "\u2013"

#: Table 7.1 two-dot sentinel (two ASCII FULL STOP characters).
#: Per the Table 7.1 legend, this means "not applicable or not
#: available". The Stage 2 read coerces it to ``None`` in
#: ``normalized_value`` (and preserves the literal in
#: ``raw_value``).
DOTS_SENTINEL: str = ".."

#: Number of pages to scan for Table 7.1. The live YB24 PDF has
#: the table on page 1 (the first content page after the chapter
#: overview); the test fixture has it on page 0. The 3-page buffer
#: absorbs any future edition where the chapter layout shifts.
_TABLE_7_1_SCAN_PAGES: int = 3

#: pdfplumber table extraction settings: the ``lines`` strategy
#: uses the PDF's vector lines to find cell boundaries (most
#: robust for Adobe InDesign-rendered tables like SIPRI's).
_TABLE_SETTINGS_LINES: dict[str, object] = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 4,
}

#: pdfplumber table extraction settings: the ``text`` strategy
#: uses font positions to find cell boundaries. Fallback only --
#: less robust for SIPRI's tables because the column-header text
#: wraps over multiple visual rows.
_TABLE_SETTINGS_TEXT: dict[str, object] = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 4,
}

#: Table 7.1 column key order (5 numeric columns; the ``Country``
#: column is at index 0 and is the country name). These keys
#: match the per-row dict's numeric fields and the
#: ``raw_value_<key>`` audit-trail keys. The live YB24 PDF has a
#: 6th column (``Year of first nuclear test``) at index 1; the
#: test fixture does not. The reader detects the column count
#: dynamically; this order is the 5-numeric-column convention.
_NUMERIC_COL_KEYS: tuple[str, ...] = (
    "deployed",
    "stored",
    "stockpile_total",
    "retired",
    "total_inventory",
)

#: Footnote-letter regex. Matches three cell-text shapes:
#: 1. ``"c. 24 j"`` -- leading ``c.`` + digits + footnote letter
#: 2. ``"24 j"`` -- digits + footnote letter (no ``c.`` prefix)
#: 3. ``"1 770 d"`` -- digits with thousands separator + footnote
#:    letter
#: The regex extracts the digit group (with spaces) and the
#: optional footnote letter; the digit group is then stripped of
#: spaces and parsed as int. The footnote letter is dropped; the
#: original cell text is preserved in ``raw_value``.
_FOOTNOTE_LETTER_RE = re.compile(
    r"^\s*(?:[cC]\.\s*)?(\d[\d\s]*?)\s*([a-z])?\s*$",
)

#: Header-row detection literal. The first row whose col 0
#: equals this string is the header row. A rename in a future
#: SIPRI release (e.g. lowercase ``"country"``) would surface
#: here.
_HEADER_TOKEN: str = "Country"

#: Error message template for the table-not-found case. The
#: test asserts the message contains the substring ``"Table 7.1"``.
_TABLE_NOT_FOUND_MSG: str = (
    "Table 7.1 not found in the first {scan} pages of the PDF. "
    "Check that the PDF is the canonical YB24 07 WNF.pdf and that "
    "the table layout has not changed in a new Yearbook edition. "
    "Path: {path}"
)


# ---------------------------------------------------------------------------
# Cell coercion
# ---------------------------------------------------------------------------


def _coerce_cell_to_int(cell: object) -> tuple[int | None, str]:
    """Coerce a Table 7.1 cell to ``(value, raw_value)``.

    Returns a 2-tuple ``(value, raw_value)``:

    - ``value`` is the parsed integer (``int``), or ``0`` for the
      en-dash sentinel (per the SIPRI legend, "nil or a negligible
      value" is treated as zero), or ``None`` for the two-dot
      sentinel (per the legend, "not applicable or not available"
      is treated as missing). For numeric cells with a ``c.``
      prefix and/or footnote letter, ``value`` is the parsed
      integer (the prefix and footnote letter are stripped).
    - ``raw_value`` is the original cell text preserved verbatim
      (the literal ``"-"``, ``".."``, ``"c. 24 j"``, ``"1 770 d"``,
      ``"5044"``, etc.) for the ``source_observations.raw_value``
      audit trail.

    Args:
        cell: a Table 7.1 cell (string from pdfplumber's
            ``extract_table``; usually ``str`` but may be ``None``
            for empty cells).

    Returns:
        A ``(value, raw_value)`` tuple. ``value`` is ``int | None``;
        ``raw_value`` is ``str`` (the literal cell text, or
        ``""`` for None cells).
    """
    if cell is None:
        return None, ""
    raw = str(cell).strip()
    if not raw:
        return None, ""
    # Sentinel dispatch: the en-dash maps to 0; the two-dot
    # maps to None; everything else goes through the
    # footnote-letter regex.
    if raw == EN_DASH_SENTINEL:
        return 0, EN_DASH_SENTINEL
    if raw == DOTS_SENTINEL:
        return None, DOTS_SENTINEL
    return _coerce_cell_via_footnote_regex(raw)


def _coerce_cell_via_footnote_regex(
    raw: str,
) -> tuple[int | None, str]:
    """Apply the footnote-letter regex to a non-sentinel cell.

    Matches three cell-text shapes: ``"c. 24 j"`` (leading
    ``c.`` + digits + footnote letter), ``"24 j"`` (digits +
    footnote letter), or plain digits. The footnote letter is
    dropped; the digit group (with spaces stripped) is parsed
    as an int. The original cell text is preserved in
    ``raw_value``.
    """
    match = _FOOTNOTE_LETTER_RE.match(raw)
    if match is None:
        # Unknown cell text. Preserve the raw text and return
        # None so the audit trail shows what the PDF actually said.
        return None, raw
    digit_str = match.group(1) or ""
    # Strip space thousands separators (and any U+00A0
    # non-breaking space) before int() parse.
    digit_str_clean = (
        digit_str.replace(" ", "").replace("\u00a0", "")
    )
    try:
        return int(digit_str_clean), raw
    except ValueError:
        # The matched digit group did not parse as int (this
        # is defensive; the regex is tight). Return None with
        # the raw text.
        return None, raw


def _build_country_dict(
    header_row: list[str],
    data_row: list[str],
) -> dict[str, object]:
    """Build a per-country dict from a Table 7.1 data row.

    The dict has ``country``, one numeric key per catalog
    column (``deployed``, ``stored``, etc.) with the coerced
    int (or 0/None for sentinels), one ``raw_value_<col>`` key
    per numeric column with the literal original PDF cell, and
    optionally ``year_first_test`` (for the live YB24 PDF which
    has 7 columns; the 6-column test fixture has no
    ``year_first_test``).

    Args:
        header_row: the Table 7.1 header row.
        data_row: a single Table 7.1 data row.

    Returns:
        A dict consumed by
        :func:`sipri_yearbook_ch7_io.read_sipri_yearbook_ch7`
        for the long -> wide pivot.
    """
    country_cell = (data_row[0] or "").strip()
    out: dict[str, object] = {"country": country_cell}

    # Detect the column layout. The live YB24 PDF has 7 columns
    # (Country | Year of first nuclear test | 5 numeric); the
    # test fixture has 6 columns (Country | 5 numeric).
    n_cols = max(len(header_row), len(data_row))
    has_year_first_test = (
        n_cols == 7
        or (len(header_row) >= 2 and header_row[1] is not None
            and "first" in str(header_row[1]).lower()
            and "test" in str(header_row[1]).lower())
    )
    numeric_offset = 2 if has_year_first_test else 1

    if has_year_first_test and n_cols >= 2:
        yft_cell = data_row[1] if len(data_row) >= 2 else None
        if yft_cell is None or (
            isinstance(yft_cell, str) and not yft_cell.strip()
        ):
            out["year_first_test"] = None
        else:
            yft_text = str(yft_cell).strip()
            try:
                out["year_first_test"] = int(yft_text)
            except ValueError:
                # The two-dot sentinel or any other non-integer
                # cell; preserve as the literal string.
                out["year_first_test"] = yft_text

    for i, key in enumerate(_NUMERIC_COL_KEYS):
        cell_idx = numeric_offset + i
        cell = data_row[cell_idx] if cell_idx < len(data_row) else None
        value, raw_value = _coerce_cell_to_int(cell)
        out[key] = value
        out[f"raw_value_{key}"] = raw_value

    return out


# ---------------------------------------------------------------------------
# Public PDF read
# ---------------------------------------------------------------------------


def read_table_7_1(pdf_path: Path) -> list[dict[str, object]]:
    """Read Table 7.1 from the SIPRI Yearbook Ch.7 PDF.

    Opens the PDF, scans the first 3 pages, and extracts the
    table from the first page that returns a non-empty table
    (using pdfplumber's ``lines`` strategy with a ``text``
    fallback). Each row becomes a dict via
    :func:`_build_country_dict`; the 1 aggregate row (``Total``)
    is also returned and filtered by the read orchestrator.

    Raises:
        FileNotFoundError: if ``pdf_path`` does not exist.
        ValueError: if Table 7.1 cannot be found (message
            contains the substring ``"Table 7.1"``).

    The per-cell coercion is the SIPRI-Yearbook-Ch.7-specific
    pattern:

    - ``"-"`` (U+2013 en-dash) -> ``0`` in the dict's numeric
      field; ``raw_value_<col>`` preserves the literal ``"-"``.
    - ``".."`` (two ASCII dots) -> ``None`` in the dict's numeric
      field; ``raw_value_<col>`` preserves the literal ``".."``.
    - ``"c. <num> [letter]"`` (e.g. ``"c. 24 j"``) -> the parsed
      integer in the dict's numeric field (the ``"c. "`` prefix
      and the footnote letter are stripped); ``raw_value_<col>``
      preserves the literal annotated string.
    - Plain numeric cells (e.g. ``"5044"``, ``"1 770 d"``) -> the
      parsed integer; ``raw_value_<col>`` preserves the literal
      cell text (including the footnote letter and the space
      thousands separator).

    The 5 ``raw_value_<col>`` keys (deployed, stored,
    stockpile_total, retired, total_inventory) are always
    present in each dict and are non-None strings (the empty
    string ``""`` is the sentinel for a missing/empty cell).

    Args:
        pdf_path: absolute path to the SIPRI Yearbook Ch.7 PDF.

    Returns:
        A list of dicts, one per row in Table 7.1 (including the
        aggregate ``Total`` row, which the read orchestrator
        filters out via the non-country denylist).

    Raises:
        FileNotFoundError: if ``pdf_path`` does not exist.
        ValueError: if Table 7.1 cannot be found in the first 3
            pages (the message contains ``"Table 7.1"``).
    """
    if not pdf_path.is_file():
        raise FileNotFoundError(
            f"SIPRI Yearbook Ch.7 PDF not found: {pdf_path}"
        )

    try:
        with pdfplumber.open(pdf_path) as pdf:
            n_pages = len(pdf.pages)
            scan_pages = min(_TABLE_7_1_SCAN_PAGES, n_pages)

            for page_idx in range(scan_pages):
                page = pdf.pages[page_idx]
                # ``lines`` strategy first (most robust for Adobe
                # InDesign-rendered tables); fall back to ``text``
                # if ``lines`` returns 0 tables.
                raw_table = page.extract_table(
                    table_settings=_TABLE_SETTINGS_LINES,
                )
                if not raw_table:
                    raw_table = page.extract_table(
                        table_settings=_TABLE_SETTINGS_TEXT,
                    )
                if not raw_table:
                    # No table on this page; try the next page.
                    continue

                # The first row is the header. Validate it.
                header_row = [
                    ("" if c is None else str(c).strip())
                    for c in raw_table[0]
                ]
                if not header_row or header_row[0] != _HEADER_TOKEN:
                    # The page has a table but it is not Table 7.1.
                    continue

                data_rows = raw_table[1:]
                countries: list[dict[str, object]] = []
                for data_row in data_rows:
                    # Skip rows whose col 0 is empty (blank
                    # separator rows the PDF sometimes inserts).
                    if not data_row or not data_row[0]:
                        continue
                    countries.append(
                        _build_country_dict(header_row, data_row),
                    )
                return countries

            # No table on any of the first 3 pages. The test
            # asserts the message contains "Table 7.1".
            raise ValueError(
                _TABLE_NOT_FOUND_MSG.format(
                    scan=scan_pages, path=pdf_path,
                )
            )
    except ValueError:
        # Re-raise the table-not-found case verbatim so the
        # test's ``pytest.raises(ValueError, match="Table 7.1")``
        # assertion matches.
        raise
    except (OSError, RuntimeError) as exc:
        # Transient I/O or pdfplumber error. Log and re-raise as
        # a ValueError so the CLI's ``ingest-source`` command
        # can report it cleanly.
        _logger.error(
            "PDF read failed for %s: %s. The PDF may be corrupt "
            "or the layout may have changed in a new Yearbook "
            "edition.",
            pdf_path, exc,
        )
        raise ValueError(
            f"Failed to read Table 7.1 from {pdf_path}: {exc}"
        ) from exc
