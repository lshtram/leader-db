"""Stage 9 CSV export helper — column declaration, row builder, writer.

This module is the **internal** CSV export logic of the Stage 9
all-countries seam (:func:`leaders_db.score.stage9.score_category_for_all_countries`).
The facade :mod:`leaders_db.score.stage9` re-exports the
public name :func:`write_score_results_csv` and the column
declaration :data:`SCORE_RESULTS_CSV_COLUMNS` so existing
imports and CLI wiring continue to work unchanged.

Scope
-----

The CSV shape is intentionally narrow: one row per country, with
the missingness counts and the score pair so a reviewer can
quantify "how much data is missing" without re-walking the
evidence bundle. The literal string ``"NA"`` is written for the
score pair on insufficient-data rows — per the 2022 vertical
slice contract the CSV is the single missingness-investigation
artifact, so the missingness columns are first-class output,
not a sidecar.

The function is intentionally small and reusable. It does not
import the rest of the ``export`` package (no pandas, no
atomic-rename dance) so it stays trivially testable and so the
per-category seam can call it directly without dragging the
pandas dependency into the Stage 9 call path. The
:func:`leaders_db.export.csv_writer.write_csv` helper is the
canonical writer for downstream exports; this helper is the
Stage 9 batch-specific row builder.

Per AGENTS.md rule #15 ("carry source attribution forward in
every public output") and ``docs/sources/attributions.md`` §3.2
/ §3.6, the CSV opens with one ``# Attribution: <text>``
comment line per contributing source (per
:data:`leaders_db.score._attributions.CATEGORY_SOURCE_ATTRIBUTIONS`)
so a downstream consumer can grep the file for provenance
without re-reading the docs. The data header
(:data:`SCORE_RESULTS_CSV_COLUMNS`) appears on the first
non-comment line and is byte-for-byte stable. A consumer
that wants to skip the comment block reads with
``csv.reader`` and discards the leading rows whose first
cell starts with ``#``, or uses ``pandas.read_csv(..., comment="#")``.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function parameter and return.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

import csv as _csv
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from ._attributions import build_attribution_comment_lines
from .results import ScoreResult

# ---------------------------------------------------------------------------
# Public exports (re-exported through ``leaders_db.score.stage9``)
# ---------------------------------------------------------------------------

__all__ = [
    "SCORE_RESULTS_CSV_COLUMNS",
    "write_score_results_csv",
]


# ---------------------------------------------------------------------------
# CSV column declaration
# ---------------------------------------------------------------------------
#
# Columns are declared as a module-level constant so the tests can
# assert on the shape without rebuilding the header from scratch.

SCORE_RESULTS_CSV_COLUMNS: tuple[str, ...] = (
    "iso3",
    "country_name",
    "year",
    "category_key",
    "system_proposed_score_1_10",
    "normalized_score_0_1",
    "score_status",
    "is_insufficient_data",
    "human_review_required",
    "review_flags",
    "observed_count",
    "expected_count",
    "missing_count",
    "missing_primary_count",
    "observation_ref_count",
    "rationale_short",
)


# ---------------------------------------------------------------------------
# Sentinels
# ---------------------------------------------------------------------------

# Literal string used in the score-pair columns when the country
# has no usable score. CSV has no native null sentinel; ``"NA"`` is
# the R/pandas convention and matches what the Stage 15 summary
# report emits.
_NA = "NA"


# ---------------------------------------------------------------------------
# Public writer
# ---------------------------------------------------------------------------


def write_score_results_csv(
    results: Sequence[ScoreResult],
    output_path: Path | str,
    *,
    category_key: str | None = None,
) -> Path:
    """Write ``results`` to ``output_path`` as a one-row-per-country CSV.

    The CSV columns are declared in
    :data:`SCORE_RESULTS_CSV_COLUMNS`. Insufficient-data rows
    write the literal string ``"NA"`` for both score columns so
    a reviewer can sort / filter / count missingness without
    re-deriving the sentinel value. The output is written
    atomically via a temp-file rename so a partial file never
    appears in ``data/outputs/``.

    The function is deliberately independent of pandas so it
    stays trivially unit-testable; it does not import
    :func:`leaders_db.export.csv_writer.write_csv` because that
    helper depends on pandas and this module needs to stay
    pandas-free at the import boundary. The atomic-rename
    pattern mirrors :func:`leaders_db.export.csv_writer.write_csv`.

    Parameters
    ----------
    results:
        The batch of :class:`ScoreResult` rows to write. The order
        is preserved by the underlying ``csv.writer``; the caller
        is responsible for sorting (the
        :func:`score_category_for_all_countries` seam sorts by
        ``iso3``).
    output_path:
        Destination path. Parent directories are created if
        missing.
    category_key:
        Optional canonical category identifier (e.g.
        ``"social_wellbeing"``). When provided (or when
        ``results`` is non-empty and the first row carries a
        ``category_key``), the writer emits the per-category
        attribution comment block from
        :func:`leaders_db.score._attributions.build_attribution_comment_lines`.
        If both the kwarg and the first result are unavailable
        (an empty batch with no explicit category), no comment
        block is emitted and the data header is the first line.
        The CLI passes the explicit kwarg so the attribution is
        present even on empty-batch output.

    Returns
    -------
    Path
        The resolved absolute path of the written file.
    """
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    # Resolve the effective category for the attribution block.
    # An explicit ``category_key`` kwarg wins (matches the CLI's
    # authoritative source); otherwise derive from the first
    # result so a test that constructs a single
    # ``ScoreResult(category_key="social_wellbeing", ...)``
    # round-trip still produces the right comment block.
    effective_category = category_key
    if effective_category is None and results:
        effective_category = results[0].category_key
    comment_lines = build_attribution_comment_lines(effective_category)

    # Atomic write: dump to a temp file in the same directory and
    # ``os.replace`` so a partial file never appears at ``target``.
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=target.parent,
        prefix=f".{target.name}.",
        encoding="utf-8",
        newline="",
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with tmp_path.open("w", encoding="utf-8", newline="") as fh:
            # Attribution comment block first (per rule #15), then
            # the stable data header, then one row per result.
            for line in comment_lines:
                # ``csv.writer`` would quote a ``#``-prefixed line
                # and add a spurious newline-after-empty-cell; emit
                # the comment lines as plain text so a spreadsheet
                # opens the file and sees clean comment rows above
                # the header.
                fh.write(line)
                fh.write("\r\n")
            writer = _csv.writer(fh)
            writer.writerow(SCORE_RESULTS_CSV_COLUMNS)
            for result in results:
                writer.writerow(_score_result_to_row(result))
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return target


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------


def _score_result_to_row(result: ScoreResult) -> tuple[str, ...]:
    """Map one :class:`ScoreResult` to a CSV row tuple.

    The mapping is the single place that owns the per-column
    formatting (NA sentinels, pipe-separated flags, missingness
    counts). Splitting it out of :func:`write_score_results_csv`
    keeps the writer testable as a row builder.
    """
    missingness = result.missingness
    if missingness is None:
        observed = ""
        expected = ""
        missing_total = ""
    else:
        observed = str(missingness.total_observed)
        expected = str(missingness.total_expected)
        missing_total = str(missingness.total_missing)

    # Count primary-severity missing observations from the
    # missingness ``by_severity`` map. ``by_severity`` is a
    # tuple-of-pairs (the MissingnessSummary contract) so a
    # linear scan is the canonical access path.
    missing_primary_count = ""
    if missingness is not None:
        for severity, count in missingness.by_severity:
            if severity == "primary":
                missing_primary_count = str(count)
                break

    if result.is_insufficient_data:
        score_1_10 = _NA
        normalized_0_1 = _NA
        score_status = "insufficient_data"
    else:
        # ``__post_init__`` enforces the cross-field invariant
        # that a non-insufficient result has both score fields
        # populated, so the asserts below are safe.
        assert result.system_proposed_score_1_10 is not None
        assert result.normalized_score_0_1 is not None
        score_1_10 = str(result.system_proposed_score_1_10)
        normalized_0_1 = f"{result.normalized_score_0_1:.4f}"
        score_status = "scored"

    flags_str = "|".join(flag.value for flag in result.review_flags)

    return (
        result.iso3,
        result.leader_name,
        str(result.year),
        result.category_key,
        score_1_10,
        normalized_0_1,
        score_status,
        "True" if result.is_insufficient_data else "False",
        "True" if result.human_review_required else "False",
        flags_str,
        observed,
        expected,
        missing_total,
        missing_primary_count,
        str(len(result.observation_refs)),
        result.rationale_short,
    )
