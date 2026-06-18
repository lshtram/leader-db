"""Smoke test for the Typer CLI.

This test runs against the real CLI entrypoint. It exists to catch:
- Typer app wiring regressions.
- Callback / option metadata changes.
- ``--help`` enumeration regressions (every Stage 0–15 command should be
  visible in ``leaders-db --help``).
"""

from __future__ import annotations

from typer.testing import CliRunner

from leaders_db.cli import app


runner = CliRunner()


def test_cli_help_succeeds() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Leaders Database prototype" in result.stdout


def test_cli_version_succeeds() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "leaders-db" in result.stdout


def test_cli_lists_every_stage_command() -> None:
    expected_commands = [
        "init-data-lake",
        "init-db",
        "check-source-availability",
        "ingest-client-matrix",
        "ingest-source",
        "match-countries",
        "resolve-leaders",
        "extract-indicators",
        "score-category",
        "score-all",
        "compute-confidence",
        "compare-vs-client",
        "build-review-queue",
        "summary-report",
    ]
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    for cmd in expected_commands:
        assert cmd in help_result.stdout, f"missing command {cmd!r} in CLI help"


def test_init_data_lake_runs(isolated_data_lake) -> None:
    result = runner.invoke(app, ["init-data-lake"])
    assert result.exit_code == 0, result.stdout
    for sub in ("raw", "processed", "interim", "outputs", "logs", "metadata"):
        assert (isolated_data_lake / "data" / sub).is_dir()


def test_init_db_runs(isolated_data_lake, database_url: str, monkeypatch) -> None:
    # The CLI reads the database URL from the resolved config. We pass a
    # config that points at the test sqlite file.
    import yaml

    from leaders_db.config import RunConfig

    cfg = RunConfig()
    cfg.database.url = database_url
    config_path = isolated_data_lake / "cfg.yaml"
    # The CLI defaults to ``configs/prototype-2023.yaml`` at the project
    # root; override via ``LEADERSDB_PROJECT_ROOT`` (set by the fixture)
    # and a config path under the temp dir.
    config_path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["init-db", "--config", str(config_path)])
    assert result.exit_code == 0, result.stdout
    # ``default_sqlite_url`` puts the file at ``leaders_db.sqlite`` inside
    # the catalog dir; the test asserts that location, not the legacy
    # ``test.sqlite`` name.
    assert (isolated_data_lake / "data" / "catalog" / "leaders_db.sqlite").is_file()


def test_ingest_source_rejects_unknown_source(isolated_data_lake) -> None:
    result = runner.invoke(app, ["ingest-source", "--source", "nope"])
    assert result.exit_code != 0
