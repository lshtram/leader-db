"""Stage 15 — summary report (requirement §8, REQ-CMP-003).

Markdown summary plus the CSV exports listed in
``docs/architecture.md``. The summary includes the §12 metrics
(countries processed, exact/alias match counts, conflicts, missing
external records, average score delta, highest and lowest agreement
categories, high/low confidence counts, manual-review count).
"""

from __future__ import annotations

from pathlib import Path


def summary_report(year: int) -> Path:
    """Build the summary report for ``year``.

    Returns the absolute path to ``validation_<year>_summary.md``.
    """
    raise NotImplementedError("summary_report is not implemented yet. Phase E.")


__all__ = ["summary_report"]
