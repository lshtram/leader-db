"""CSV writer for the Country-Year Chronicle slice.

The writer is deliberately small:

1. Writes the attribution comment block as leading ``#`` lines (one
   line per source) before the header.
2. Writes the header using the canonical column order from
   :data:`CHRONICLE_CSV_COLUMNS`.
3. Writes one row per record from the input row list.
4. Uses an atomic write: the CSV is built in a temporary file under
   the same directory as the destination and then renamed. A
   crash mid-write leaves the destination file untouched.

The function is pure in the sense that it does not read from any
external source — it only consumes the row list and writes to disk.
The CSV writer accepts both ``str`` and ``int``/``float`` cell values;
non-string values are coerced to their ``str`` representation with
``None`` and ``float('nan')`` normalized to empty strings (which the
CSV reader will turn into empty cells).

Increment 2 added the Maddison Project attribution line plus the
Archigos / REIGN attribution lines (ruler resolver sources). The
exact attribution text is sourced from
:mod:`leaders_db.chronicle.source_constants` and is drift-guarded
against :file:`docs/source-attributions.md`.
"""

from __future__ import annotations

import csv
import math
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .constants import CHRONICLE_CSV_COLUMNS
from .source_constants import (
    ARCHIGOS_ATTRIBUTION,
    CSHAPES_ATTRIBUTION,
    MADDISON_PROJECT_ATTRIBUTION,
    REIGN_ATTRIBUTION,
    SIPRI_MILEX_ATTRIBUTION,
    SOVIET_LEADERS_CURATED_ATTRIBUTION,
    VDEM_ATTRIBUTION,
    WDI_ATTRIBUTION,
    WIKIDATA_RECENT_RULERS_ATTRIBUTION,
)


def build_attribution_comment_block(
    *,
    sources_used: Iterable[str],
    extra_lines: Iterable[str] = (),
) -> list[str]:
    """Build the leading ``#`` comment lines for the CSV output.

    Each line is a complete CSV cell that begins with ``#`` (per the
    project's manual-review-queue convention in
    :file:`docs/source-attributions.md` §3.2). The block always opens
    with a one-line ``# Country-Year Chronicle pilot CSV`` header so a
    downstream consumer can detect the file format.

    The source-specific attribution lines are emitted in
    alphabetical order of the source key (the same order the runner
    reports in ``sources_used``), so the CSV's leading comment
    block is byte-identical across runs that touch the same sources.
    """
    lines: list[str] = ["# Country-Year Chronicle pilot CSV"]
    lines.append(
        "# Experimental vertical slice; do not treat as authoritative."
    )
    source_attribution_map = {
        "archigos": ARCHIGOS_ATTRIBUTION,
        "cshapes": CSHAPES_ATTRIBUTION,
        "colonial_rule_placeholder": VDEM_ATTRIBUTION,
        "maddison_project": MADDISON_PROJECT_ATTRIBUTION,
        "reign": REIGN_ATTRIBUTION,
        "sipri_milex": SIPRI_MILEX_ATTRIBUTION,
        "soviet_leaders_curated": SOVIET_LEADERS_CURATED_ATTRIBUTION,
        "vdem": VDEM_ATTRIBUTION,
        "wdi": WDI_ATTRIBUTION,
        "wikidata_recent_rulers": WIKIDATA_RECENT_RULERS_ATTRIBUTION,
    }
    for source in sorted(set(sources_used)):
        attribution = source_attribution_map.get(source)
        if attribution:
            lines.append(f"# {attribution}")
    for line in extra_lines:
        if line:
            lines.append(f"# {line}")
    return lines


def _normalize_cell(value: object) -> str:
    """Coerce one cell value to its CSV string representation.

    ``None`` and ``float('nan')`` become empty strings. Other objects
    are passed through ``str()``.
    """
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def write_chronicle_csv(
    *,
    output_path: Path,
    rows: list[dict[str, object]],
    sources_used: Iterable[str],
    extra_attribution_lines: Iterable[str] = (),
) -> Path:
    """Write the chronicle rows to ``output_path`` atomically.

    The function:

    1. Creates the parent directory if it does not exist.
    2. Writes a temporary file under the same directory using
       :class:`tempfile.NamedTemporaryFile` so the rename is atomic
       on the same filesystem.
    3. Renames the temporary file to ``output_path``.

    The function returns the resolved output path on success. If the
    write fails partway, the temporary file is removed and the
    exception is re-raised; the destination file is never left in a
    partial state.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=output_path.name + ".",
        suffix=".tmp",
        dir=str(output_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        # ``newline=""`` so csv writes its own line terminators (csv
        # module uses \r\n by default; this matches the project's
        # other CSV outputs).
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            attribution_lines = build_attribution_comment_block(
                sources_used=sources_used,
                extra_lines=extra_attribution_lines,
            )
            for line in attribution_lines:
                fh.write(line)
                fh.write("\r\n")

            writer = csv.DictWriter(
                fh,
                fieldnames=list(CHRONICLE_CSV_COLUMNS),
                lineterminator="\r\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in rows:
                normalized = {
                    col: _normalize_cell(row.get(col, "")) for col in CHRONICLE_CSV_COLUMNS
                }
                writer.writerow(normalized)
        os.replace(tmp_path, output_path)
    except Exception:
        # Best-effort cleanup so a failed run does not litter
        # ``data/outputs/`` with stale ``.tmp`` files.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise
    return output_path


__all__ = [
    "build_attribution_comment_block",
    "write_chronicle_csv",
]
