"""SQLite export for the Country-Year Chronicle slice.

This module is the optional artifact complement to
:mod:`leaders_db.chronicle.csv_writer`. The default Chronicle
run writes a CSV; this module adds a small SQLite database
export alongside (or instead of) the CSV.

The SQLite artifact is a single ``country_year_chronicle`` table
with one row per chronicle record and column types chosen so a
``sqlite3`` CLI user can read it without surprises:

- ``year``, ``iso3``, ``country_name``, ``country_status``,
  ``region``, ``subregion``, ``ruler_*``, ``political_regime_*``,
  ``system_type_*``, ``population_source``, ``gdp_unit``,
  ``gdp_source``, ``military_spend_unit``, ``military_spend_source``,
  ``area_source``, ``data_quality_flags``, ``provenance_summary``
  are stored as TEXT (the canonical string form from the CSV).
- Numeric values that are guaranteed integer / float in the CSV
  (``population``, ``gdp``, ``gdp_per_capita``, ``military_spend``,
  ``country_area_km2``, ``controlled_area_km2``, ``row_confidence``,
  ``ruler_confidence``, ``political_regime_raw_score``,
  ``political_regime_confidence``, ``system_type_confidence``,
  ``ruler_source_year_used``, ``political_regime_source_year_used``,
  ``population_source_year_used``, ``gdp_source_year_used``,
  ``military_spend_source_year_used``, ``area_source_year_used``)
  are stored as INTEGER / REAL when the row value is parseable,
  otherwise NULL. The empty string is normalized to NULL.

Attribution + source-metadata sidecar. The schema stays small and
deterministic per the workplan ("Keep CSV behavior intact"). The
attribution block lives in a separate ``source_attributions`` table
with one row per source key. This makes the table easy to JOIN to
the chronicle rows without forcing comments inside SQL DDL (SQLite
does not support table comments).

The write is atomic: the SQLite file is built in a temp file under
the same directory as the destination and renamed via
:class:`os.replace`. A crash mid-write leaves the destination
untouched.

The module is intentionally small: it does not try to be a full
ORM mapping or to interop with the main prototype catalog. It is a
deterministic artifact for the chronicle slice and nothing else.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
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
)

_logger = logging.getLogger(__name__)


#: SQLite storage class per chronicle column. Keys are
#: ``CHRONICLE_CSV_COLUMNS`` entries; values are ``"TEXT"``,
#: ``"INTEGER"``, or ``"REAL"``. Columns not listed here fall back
#: to TEXT (the safe default for a column whose CSV cell may be
#: blank or contain arbitrary string content).
CHRONICLE_COLUMN_TYPES: dict[str, str] = {
    "year": "INTEGER",
    "population": "REAL",
    "population_source_year_used": "INTEGER",
    "gdp": "REAL",
    "gdp_per_capita": "REAL",
    "military_spend": "REAL",
    "country_area_km2": "REAL",
    "controlled_area_km2": "REAL",
    "ruler_source_year_used": "INTEGER",
    "ruler_confidence": "INTEGER",
    "political_regime_raw_score": "REAL",
    "political_regime_source_year_used": "INTEGER",
    "political_regime_confidence": "INTEGER",
    "system_type_confidence": "INTEGER",
    "gdp_source_year_used": "INTEGER",
    "military_spend_source_year_used": "INTEGER",
    "area_source_year_used": "INTEGER",
    "row_confidence": "INTEGER",
}


#: Schema for the canonical attribution sidecar table. Each
#: statement is a complete SQL statement terminated with ``;`` so
#: :func:`write_chronicle_sqlite` can execute them one at a time
#: via the :class:`sqlite3.Cursor.execute` API (which does not
#: accept multi-statement scripts).
SOURCE_ATTRIBUTIONS_SCHEMA: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS source_attributions ("
    "source_key TEXT PRIMARY KEY, attribution_text TEXT NOT NULL)",
)


def _coerce_sqlite_value(value: object, column: str) -> object:
    """Coerce a CSV-cell value to its SQLite storage class.

    Empty strings map to NULL. Integer columns parse as ``int``;
    REAL columns parse as ``float``; TEXT columns pass through.
    The function never raises: a value that fails to parse as
    INTEGER / REAL becomes NULL with the original string still
    recoverable from the canonical CSV companion artifact.
    """
    column_type = CHRONICLE_COLUMN_TYPES.get(column, "TEXT")

    def _text_value() -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return None if text == "" else text

    text = _text_value()
    if text is None:
        return None
    if column_type == "INTEGER":
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None
    if column_type == "REAL":
        try:
            return float(text)
        except (TypeError, ValueError):
            return None
    return text


def _sanitize_identifier(name: str) -> str:
    """Return a safe SQLite identifier for ``name``.

    SQLite is lenient about unquoted identifiers but we still
    validate to avoid surprises if a column name changes. The
    canonical columns are simple ASCII; if a future column has
    spaces / non-ASCII we quote it.
    """
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return name
    return f'"{name}"'


def _build_create_table_sql(table_name: str) -> str:
    """Build the ``CREATE TABLE`` statement for the chronicle table."""
    columns_sql = []
    for col in CHRONICLE_CSV_COLUMNS:
        col_type = CHRONICLE_COLUMN_TYPES.get(col, "TEXT")
        columns_sql.append(f"    {_sanitize_identifier(col)} {col_type}")
    columns_block = ",\n".join(columns_sql)
    return (
        f"CREATE TABLE IF NOT EXISTS "
        f"{_sanitize_identifier(table_name)} (\n"
        f"{columns_block}\n)"
    )


def _build_chronicle_insert_sql(table_name: str) -> tuple[str, tuple[str, ...]]:
    """Build the ``INSERT INTO`` statement for the chronicle table.

    Returns ``(sql_template, columns_tuple)``. Callers bind the
    values in column order.
    """
    cols = list(CHRONICLE_CSV_COLUMNS)
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(_sanitize_identifier(c) for c in cols)
    sql = (
        f"INSERT INTO {_sanitize_identifier(table_name)} "
        f"({col_list}) VALUES ({placeholders})"
    )
    return sql, tuple(cols)


#: Source-key -> attribution text map for the source_attributions
#: sidecar table. This is the byte-for-byte canonical mapping; the
#: drift-guard tests in :mod:`tests.test_chronicle_constants`
#: confirm each line is a substring of
#: ``docs/source-attributions.md``.
SOURCE_ATTRIBUTIONS: dict[str, str] = {
    "archigos": ARCHIGOS_ATTRIBUTION,
    "cshapes": CSHAPES_ATTRIBUTION,
    "maddison_project": MADDISON_PROJECT_ATTRIBUTION,
    "reign": REIGN_ATTRIBUTION,
    "sipri_milex": SIPRI_MILEX_ATTRIBUTION,
    "soviet_leaders_curated": SOVIET_LEADERS_CURATED_ATTRIBUTION,
    "vdem": VDEM_ATTRIBUTION,
    "wdi": WDI_ATTRIBUTION,
}


def default_sqlite_path(
    *, project_root: Path | None = None,
    basename: str | None = None,
) -> Path:
    """Return the canonical SQLite artifact path for the slice.

    Resolves to
    ``<project_root>/data/outputs/country-year-chronicle/<basename>``.
    Default ``basename`` is ``pilot.sqlite`` per the Increment 2
    contract.
    """
    from ..paths import project_root as _project_root
    from .constants import CHRONICLE_OUTPUT_DIR_NAME

    root = project_root if project_root is not None else _project_root()
    base = basename or "pilot.sqlite"
    return root / "data" / "outputs" / CHRONICLE_OUTPUT_DIR_NAME / base


def write_chronicle_sqlite(
    *,
    output_path: Path,
    rows: list[dict[str, object]],
    sources_used: Iterable[str],
    table_name: str = "country_year_chronicle",
) -> Path:
    """Write the chronicle rows to ``output_path`` as a SQLite database.

    Parameters
    ----------
    output_path:
        Destination SQLite path. The parent directory is
        created if missing. The file is built atomically: a
        crash mid-write leaves the destination untouched.
    rows:
        One dict per chronicle record, keys matching
        :data:`CHRONICLE_CSV_COLUMNS`. Missing keys become NULL.
    sources_used:
        Iterable of source tags that contributed data; each tag
        is recorded in the ``source_attributions`` sidecar table
        along with the canonical attribution text.
    table_name:
        Name of the main chronicle table. Defaults to
        ``country_year_chronicle`` per the Increment 2 contract.

    Returns
    -------
    Path
        The resolved output path on success.
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
        os.close(fd)
        conn = sqlite3.connect(str(tmp_path))
        try:
            cur = conn.cursor()
            cur.execute(_build_create_table_sql(table_name))
            for schema_stmt in SOURCE_ATTRIBUTIONS_SCHEMA:
                cur.execute(schema_stmt)
            insert_sql, columns = _build_chronicle_insert_sql(table_name)
            for row in rows:
                values = tuple(
                    _coerce_sqlite_value(row.get(col), col)
                    for col in columns
                )
                cur.execute(insert_sql, values)
            # Sidecar table: one row per source used.
            for source_key in sorted(set(sources_used)):
                attribution = SOURCE_ATTRIBUTIONS.get(source_key)
                if not attribution:
                    continue
                cur.execute(
                    "INSERT OR REPLACE INTO source_attributions "
                    "(source_key, attribution_text) VALUES (?, ?)",
                    (source_key, attribution),
                )
            conn.commit()
        finally:
            conn.close()
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
    "CHRONICLE_COLUMN_TYPES",
    "SOURCE_ATTRIBUTIONS",
    "SOURCE_ATTRIBUTIONS_SCHEMA",
    "default_sqlite_path",
    "write_chronicle_sqlite",
]
