"""Session scope helpers.

The package uses a fresh session per CLI command (or per unit-of-work in a
future pipeline runner). Tests construct their own sessions via
:func:`make_session_factory`.

The session factory is configured for the prototype database URL taken
from ``RunConfig``. Direct ``Session()`` construction outside of a unit
test is a code smell — use :func:`session_scope` instead.

When no engine or URL is passed, the default URL resolves through
:func:`leaders_db.paths.project_root`, which honors the
``LEADERSDB_PROJECT_ROOT`` environment variable. This means the
production path uses ``<project_root>/data/catalog/leaders_db.sqlite``
and tests can override the project root with the env var (the
``isolated_data_lake`` test fixture does this).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..paths import catalog_dir
from .engine import build_engine


def default_sqlite_url() -> str:
    """Return the default SQLite URL resolved through :func:`project_root`.

    The URL points at ``<project_root>/data/catalog/leaders_db.sqlite``.
    If the catalog folder does not exist yet, it is created so the
    engine can open the file. The ``LEADERSDB_PROJECT_ROOT`` env var
    controls the resolution (test fixture sets it to a temp dir).
    """
    catalog_dir().mkdir(parents=True, exist_ok=True)
    db_path = catalog_dir() / "leaders_db.sqlite"
    # Use a POSIX path so the URL is portable across platforms.
    return f"sqlite:///{db_path.as_posix()}"


def make_session_factory(engine: Engine | str | None = None) -> sessionmaker[Session]:
    """Build a :class:`sessionmaker` bound to the given engine or URL.

    When ``engine`` is ``None``, the default SQLite URL from
    :func:`default_sqlite_url` is used (resolved through ``project_root``
    and honoring ``LEADERSDB_PROJECT_ROOT``).
    """
    if engine is None:
        engine = build_engine(default_sqlite_url())
    elif isinstance(engine, str):
        engine = build_engine(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(engine: Engine | str | None = None) -> Iterator[Session]:
    """Yield a session that is committed on success and rolled back on error.

    Usage::

        with session_scope() as session:
            session.add(row)
            # commit happens on context exit; rollback on exception.
    """
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Re-export so callers can ``from leaders_db.db.session import project_root``
# in tests that want to assert the env-var override took effect.
__all__ = ["default_sqlite_url", "make_session_factory", "session_scope"]
