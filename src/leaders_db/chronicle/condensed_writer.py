"""Condensed CSV writer for the Country-Year Chronicle slice.

The condensed CSV is a deliberately small companion artifact to the
detailed CSV. It exposes only the data a reader wants when scanning
country-year rows by eye:

    year, iso3, country, existence_status,
    ruler, political_regime, system_type,
    population, gdp, gdp_per_capita, military_spend, country_area_km2

It OMITS (per the Increment 5 contract):

- every source tag (``*_source``);
- every confidence value (``*_confidence``);
- the ``provenance_summary``;
- the ``data_quality_flags``;
- the ``system_type_notes`` / ``controlled_area_note``;
- the ``shared_rule_flag`` / ``disputed_rule_flag``;
- the controlled-area value (``controlled_area_km2``) — controlled-area
  modeling is deferred per Increment 4, so the condensed export
  carries only the standard ``country_area_km2``;
- all unit / method text columns (``gdp_unit``, ``gdp_per_capita_unit``,
  ``gdp_per_capita_method``, ``military_spend_unit``).

The condensed writer is a pure transform from the detailed row
list plus a :class:`CountryScopeEntry` mapping. It does NOT
re-query any source. The detailed CSV / SQLite are the canonical
audited artifacts; the condensed CSV is a view on top of them.

Existence semantics:

- The condensed writer maps each ``(iso3, year)`` row to one of
  four ``existence_status`` labels via
  :func:`leaders_db.chronicle.country_scope.get_existence_status`.
- For rows that fall OUTSIDE the country's existence window
  (``not_formed`` or ``split_or_dissolved``), the writer emits
  ONLY ``year``, ``iso3``, ``country``, ``existence_status`` and
  leaves every other column blank. This is the documented
  Increment 5 behavior; the alternative (carrying empty ruler /
  population / area rows for entities that did not exist) would
  clutter the condensed file with rows that have no data.
- For ``exists`` rows, the writer maps the detailed row's
  ``ruler_name`` / ``political_regime_bucket`` /
  ``system_type_primary`` / ``population`` / ``gdp`` /
  ``gdp_per_capita`` / ``military_spend`` / ``country_area_km2``
  values verbatim.

Atomic write:

- The condensed CSV is written through the same
  tempfile + rename pattern as the detailed writer. A crash
  mid-write leaves the destination untouched.
"""

from __future__ import annotations

import csv
import math
import os
import tempfile
from pathlib import Path

from .constants import (
    CONDENSED_CSV_COLUMNS,
    EXISTS_STATUS_NOT_FORMED,
    EXISTS_STATUS_SPLIT,
)
from .country_scope import (
    CountryScopeEntry,
    get_existence_status,
)


def _normalize_cell(value: object) -> str:
    """Coerce one cell value to its CSV string representation.

    ``None`` and ``float('nan')`` become empty strings. Other objects
    are passed through ``str()``. This mirrors the detailed writer's
    helper so the two outputs share the same cell semantics.
    """
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def _build_condensed_row(
    detailed: dict[str, str],
    scope_entry: CountryScopeEntry | None,
    year: int,
) -> dict[str, str]:
    """Map one detailed row to the condensed column dict.

    The detailed row's ``year`` / ``iso3`` values are trusted
    (the row builder produces them deterministically). The
    ``country_name`` is overridden by the scope entry's
    ``country_name`` when one is provided so the all-country
    condensed export shows real country names for every row.

    For rows OUTSIDE the existence window the writer leaves
    every data column blank. The ``ruler``, ``political_regime``,
    ``system_type``, ``population``, ``gdp``, ``gdp_per_capita``,
    ``military_spend``, and ``country_area_km2`` columns are
    blank for ``not_formed`` / ``split_or_dissolved`` rows.
    """
    iso3 = detailed.get("iso3", "")
    if scope_entry is not None:
        existence_status = get_existence_status(scope_entry, year)
        country_name = scope_entry.country_name
    else:
        # No scope entry: behave like the detailed row's
        # ``country_status`` and emit ``exists``. Today every
        # detailed row has a scope entry when the condensed
        # writer is invoked through the CLI; this branch exists
        # so unit tests that build condensed rows directly
        # without a scope still produce well-formed output.
        existence_status = "exists"
        country_name = detailed.get("country_name", iso3)

    row: dict[str, str] = {
        "year": _normalize_cell(detailed.get("year", str(year))),
        "iso3": iso3,
        "country": country_name,
        "existence_status": existence_status,
        "ruler": "",
        "political_regime": "",
        "system_type": "",
        "population": "",
        "gdp": "",
        "gdp_per_capita": "",
        "military_spend": "",
        "country_area_km2": "",
    }

    if existence_status in (EXISTS_STATUS_NOT_FORMED, EXISTS_STATUS_SPLIT):
        # Out-of-window rows keep only the four-window columns.
        # The audit trail (data_quality_flags, *_source) is
        # available in the detailed CSV; the condensed export
        # deliberately does not duplicate it.
        return row

    row["ruler"] = _normalize_cell(detailed.get("ruler_name", ""))
    row["political_regime"] = _normalize_cell(
        detailed.get("political_regime_bucket", "")
    )
    row["system_type"] = _normalize_cell(detailed.get("system_type_primary", ""))
    row["population"] = _normalize_cell(detailed.get("population", ""))
    row["gdp"] = _normalize_cell(detailed.get("gdp", ""))
    row["gdp_per_capita"] = _normalize_cell(detailed.get("gdp_per_capita", ""))
    row["military_spend"] = _normalize_cell(detailed.get("military_spend", ""))
    row["country_area_km2"] = _normalize_cell(detailed.get("country_area_km2", ""))
    return row


def build_condensed_rows(
    detailed_rows: list[dict[str, str]],
    country_scope: dict[str, CountryScopeEntry],
) -> list[dict[str, str]]:
    """Build the condensed rows for a list of detailed rows.

    Parameters
    ----------
    detailed_rows:
        One dict per chronicle record, keys matching
        :data:`CHRONICLE_CSV_COLUMNS` (the detailed CSV column
        order). The condensed writer reads ``year`` / ``iso3`` /
        ``country_name`` / ``ruler_name`` /
        ``political_regime_bucket`` / ``system_type_primary`` /
        ``population`` / ``gdp`` / ``gdp_per_capita`` /
        ``military_spend`` / ``country_area_km2``.
    country_scope:
        Mapping of ISO3 -> :class:`CountryScopeEntry`. The writer
        looks up each row's iso3 in this mapping to compute
        ``existence_status`` and to override ``country_name``.
        Rows whose iso3 is not in the scope are emitted with
        ``existence_status = "exists"`` and the detailed row's
        ``country_name`` (the conservative fallback; the CLI
        always passes a scope that covers every requested iso3).

    Returns
    -------
    list[dict[str, str]]
        Condensed rows in the same order as ``detailed_rows``.
    """
    condensed: list[dict[str, str]] = []
    for detailed in detailed_rows:
        try:
            year = int(str(detailed.get("year", "")).strip())
        except (TypeError, ValueError):
            year = 0
        iso3 = str(detailed.get("iso3", ""))
        scope_entry = country_scope.get(iso3)
        condensed.append(_build_condensed_row(detailed, scope_entry, year))
    return condensed


def write_condensed_csv(
    *,
    output_path: Path,
    detailed_rows: list[dict[str, str]],
    country_scope: dict[str, CountryScopeEntry],
) -> Path:
    """Write the condensed CSV to ``output_path`` atomically.

    The function:

    1. Creates the parent directory if it does not exist.
    2. Builds the condensed rows in memory.
    3. Writes the file under a ``tempfile.NamedTemporaryFile``
       in the same directory, then renames atomically.
    4. Returns the resolved output path on success.

    The CSV header is the canonical
    :data:`CONDENSED_CSV_COLUMNS` order. The function does NOT
    add the ``#`` attribution comment block used by the detailed
    CSV (the condensed export is a "data only" artifact; the
    attribution block lives on the detailed CSV / SQLite). If a
    reader needs the per-source attribution, the canonical
    source-attributions doc is the durable record.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = build_condensed_rows(detailed_rows, country_scope)

    fd, tmp_name = tempfile.mkstemp(
        prefix=output_path.name + ".",
        suffix=".tmp",
        dir=str(output_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=list(CONDENSED_CSV_COLUMNS),
                lineterminator="\r\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in rows:
                normalized = {
                    col: _normalize_cell(row.get(col, "")) for col in CONDENSED_CSV_COLUMNS
                }
                writer.writerow(normalized)
        os.replace(tmp_path, output_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise
    return output_path


__all__ = [
    "CONDENSED_CSV_COLUMNS",
    "build_condensed_rows",
    "write_condensed_csv",
]
