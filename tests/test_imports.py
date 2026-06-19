"""Package import smoke test.

Catches broken package layouts early. Runs in <100ms.
"""

from __future__ import annotations


def test_package_imports() -> None:
    import leaders_db

    assert leaders_db.__version__


def test_all_subpackages_import() -> None:
    # Each subpackage must be importable without raising.
    import leaders_db.cli
    import leaders_db.config
    import leaders_db.db
    import leaders_db.env
    import leaders_db.export
    import leaders_db.ingest
    import leaders_db.llm
    import leaders_db.normalize
    import leaders_db.paths
    import leaders_db.resolve
    import leaders_db.score
    import leaders_db.validate  # noqa: F401
