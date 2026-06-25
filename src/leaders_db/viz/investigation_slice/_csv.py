"""CSV writer for the investigation slice.

The writer emits a stable long-form CSV keyed on
``(country_iso3, year, source_id, indicator_code)`` so successive runs
produce byte-identical files when the input observations are stable
-- Superset schema and any downstream hash check both rely on this.

The ``question_key`` column is set explicitly by the writer from the
caller-supplied :class:`InvestigationQuestion.question_key` rather
than read out of :class:`ConceptObservation.extension`. The concept
catalog does not inject a question key into the observation
extension, so reading from there would emit blank cells; the slice
owns the question, so the slice owns the column value.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from ...sources.concepts import ConceptObservation

# Column order for the chart-ready CSV. Stable across runs so the
# Superset schema doesn't drift.
INVESTIGATION_CSV_COLUMNS: tuple[str, ...] = (
    "question_key",
    "concept_key",
    "country_iso3",
    "year",
    "source_id",
    "source_version",
    "indicator_code",
    "value",
    "unit",
    "scale",
    "mapping_type",
    "recipe_key",
    "observation_id",
    "quality_flag",
)


def write_concept_csv(
    csv_path: Path,
    concept_rows: Sequence[ConceptObservation],
    *,
    question_key: str,
) -> None:
    """Write ``concept_rows`` to ``csv_path`` atomically.

    ``question_key`` is written verbatim into the ``question_key``
    column for every row so the CSV is never blank in that column.
    The slice owns the question; the concept catalog does not inject
    a question key into the observation extension, and reading it from
    there would silently produce empty cells.

    Rows are sorted by ``(country_iso3, year, source_id,
    indicator_code)`` so successive runs produce byte-identical files
    when the input observations are stable.
    """
    sorted_rows = sorted(
        concept_rows,
        key=lambda row: (
            row.country_code or "",
            row.year if row.year is not None else 0,
            row.source_id.slug,
            row.source_indicator_codes[0] if row.source_indicator_codes else "",
        ),
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(INVESTIGATION_CSV_COLUMNS))
        writer.writeheader()
        for row in sorted_rows:
            quality_flag = row.quality_flags[0] if row.quality_flags else ""
            writer.writerow(
                {
                    "question_key": question_key,
                    "concept_key": row.concept_key,
                    "country_iso3": row.country_code or "",
                    "year": row.year if row.year is not None else "",
                    "source_id": row.source_id.slug,
                    "source_version": row.source_version or "",
                    "indicator_code": (
                        row.source_indicator_codes[0]
                        if row.source_indicator_codes
                        else ""
                    ),
                    "value": "" if row.value is None else row.value,
                    "unit": row.unit or "",
                    "scale": row.scale or "",
                    "mapping_type": row.mapping_type,
                    "recipe_key": row.recipe_key or "",
                    "observation_id": (
                        row.input_observation_ids[0]
                        if row.input_observation_ids
                        else ""
                    ),
                    "quality_flag": quality_flag,
                }
            )
    tmp_path.replace(csv_path)


__all__ = [
    "INVESTIGATION_CSV_COLUMNS",
    "write_concept_csv",
]
