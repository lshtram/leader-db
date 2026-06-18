"""Database layer — SQLAlchemy 2.x ORM for the 11 prototype tables.

Module map:

- ``engine``  — engine factory, ``init_database`` migration runner.
- ``session`` — session factory and scoped session helpers.
- ``models``  — declarative ORM models for ``countries``, ``leaders``, etc.
- ``migrations/0001_initial.sql`` — canonical DDL, checked in for clarity.

The canonical schema is normative: see ``docs/database-schema.md``. Schema
changes require a new migration file under ``migrations/`` plus an
update to ``models`` in the same commit.
"""

from __future__ import annotations

from .engine import build_engine, init_database
from .session import session_scope

__all__ = ["build_engine", "init_database", "session_scope"]
