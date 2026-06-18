"""SQLAlchemy engine factory and migration runner.

SQLite is the default for the prototype (REQ-DB-001). PostgreSQL is
supported via the ``postgresql+psycopg://`` URL scheme.

The migration runner applies every ``.sql`` file under
``migrations/`` whose filename matches ``[0-9]{4}_*.sql`` in lexicographic
order. It is idempotent: each file is wrapped in a transaction and skipped
if its filename is already recorded in the ``schema_migrations`` table.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_NAME_RE = re.compile(r"^\d{4}_.+\.sql$")


def build_engine(url: str, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine with sensible defaults.

    SQLite is given ``check_same_thread=False`` so the engine is usable
    from background threads (Typer jobs, future pipelines).
    """
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, echo=echo, future=True, connect_args=connect_args)


def init_database(url: str, *, echo: bool = False) -> None:
    """Apply every checked-in migration to the configured database.

    The runner is idempotent — re-running it does not duplicate work.
    """
    engine = build_engine(url, echo=echo)
    migrations = list(_migration_files(_MIGRATIONS_DIR))
    if not migrations:
        return

    with engine.begin() as conn:
        _ensure_migrations_table(conn)

    with engine.begin() as conn:
        applied = {
            row[0]
            for row in conn.execute(text("SELECT filename FROM schema_migrations")).all()
        }
        for path in migrations:
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            for statement in _split_sql(sql):
                conn.execute(text(statement))
            conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:f)"),
                {"f": path.name},
            )


def _migration_files(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if _MIGRATION_NAME_RE.match(p.name))


def _ensure_migrations_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _split_sql(sql: str) -> list[str]:
    """Split a SQL script into individual statements.

    Strips ``--`` line comments first so a semicolon embedded in a comment
    does not break the split, then splits on ``;``. Empty / whitespace-only
    fragments are dropped. This is a pragmatic splitter — it is not a full
    SQL parser. If we ever need stored procedures, dollar-quoted strings,
    or other constructs, swap in ``sqlparse``.
    """
    cleaned_lines: list[str] = []
    for line in sql.splitlines():
        # Drop full-line comments. Inline comments after code (e.g.
        # ``SELECT 1 -- note``) are uncommon in DDL; the splitter drops
        # any ``--`` segment after the first whitespace too, which is
        # good enough for our migration files.
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        # Also drop any trailing inline comment.
        if "--" in line:
            line = line.split("--", 1)[0]
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    statements: list[str] = []
    for raw in cleaned.split(";"):
        stmt = raw.strip()
        if stmt:
            statements.append(stmt)
    return statements
