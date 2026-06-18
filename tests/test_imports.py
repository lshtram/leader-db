"""Package import smoke test.

Catches broken package layouts early. Runs in <100ms.
"""

from __future__ import annotations


def test_package_imports() -> None:
    import leaders_db

    assert leaders_db.__version__


def test_all_subpackages_import() -> None:
    # Each subpackage must be importable without raising.
    import leaders_db.cli  # noqa: F401
    import leaders_db.config  # noqa: F401
    import leaders_db.db  # noqa: F401
    import leaders_db.env  # noqa: F401
    import leaders_db.export  # noqa: F401
    import leaders_db.ingest  # noqa: F401
    import leaders_db.llm  # noqa: F401
    import leaders_db.normalize  # noqa: F401
    import leaders_db.paths  # noqa: F401
    import leaders_db.resolve  # noqa: F401
    import leaders_db.score  # noqa: F401
    import leaders_db.validate  # noqa: F401
