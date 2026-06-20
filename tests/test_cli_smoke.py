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


def test_score_category_help_uses_dispatcher_registered_language() -> None:
    """The scoring help must not hard-code stale supported categories."""
    result = runner.invoke(app, ["score-category", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "Stage 9 dispatcher" in result.stdout
    assert "currently 'social_wellbeing'" not in result.stdout
    assert "together with --category social_wellbeing" not in result.stdout


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


# ---------------------------------------------------------------------------
# Stage 9 narrow single-country seam: ``score-category --country``
# ---------------------------------------------------------------------------


def _write_test_config(
    isolated_data_lake, database_url: str
) -> str:
    """Persist a minimal RunConfig YAML under the isolated data lake."""
    import yaml

    from leaders_db.config import RunConfig

    cfg = RunConfig()
    cfg.database.url = database_url
    config_path = isolated_data_lake / "cfg.yaml"
    config_path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return str(config_path)


def test_score_category_without_country_prints_batch_not_implemented(
    isolated_data_lake, database_url: str
) -> None:
    """``score-category --category ... --year ...`` (no --country) keeps the stub."""
    from leaders_db.db.engine import init_database

    init_database(database_url)
    config_path = _write_test_config(isolated_data_lake, database_url)

    result = runner.invoke(
        app,
        [
            "score-category",
            "--category",
            "social_wellbeing",
            "--year",
            "2023",
            "--config",
            config_path,
        ],
    )
    assert result.exit_code == 0, result.stdout
    # The stub message must still be the canonical "not implemented
    # yet" line so existing callers do not see a behavior change.
    assert "[stub]" in result.stdout
    assert "not implemented yet" in result.stdout


def test_score_category_with_country_unsupported_category_fails(
    isolated_data_lake, database_url: str
) -> None:
    """``--country`` with an unsupported category fails with a clear error."""
    from leaders_db.db.engine import init_database

    init_database(database_url)
    config_path = _write_test_config(isolated_data_lake, database_url)

    result = runner.invoke(
        app,
        [
            "score-category",
            "--category",
            "corruption",
            "--year",
            "2023",
            "--country",
            "MEX",
            "--config",
            config_path,
        ],
    )
    # Typer raises BadParameter on bad option values — the runner
    # captures it and exits with a non-zero code (typically 2).
    assert result.exit_code != 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "corruption" in combined
    # The error must point at the supported set so the user can
    # pick the right category.
    assert "social_wellbeing" in combined


def test_score_category_with_country_missing_country_in_db_fails(
    isolated_data_lake, database_url: str
) -> None:
    """``--country ZZZ`` (not in DB) fails with a clear ValueError.

    The CLI delegates to the Stage 9 seam; the underlying bundle
    builder raises ``ValueError`` when the country is not in the
    DB. The test asserts the failure surfaces with a useful
    message rather than a silent success.
    """
    from leaders_db.db.engine import init_database

    init_database(database_url)
    config_path = _write_test_config(isolated_data_lake, database_url)

    result = runner.invoke(
        app,
        [
            "score-category",
            "--category",
            "social_wellbeing",
            "--year",
            "2023",
            "--country",
            "ZZZ",
            "--config",
            config_path,
        ],
    )
    assert result.exit_code != 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "ZZZ" in combined


def test_score_category_with_country_prints_score_summary(
    isolated_data_lake, database_url: str
) -> None:
    """``--country MEX`` with a seeded DB prints the Stage 9 score summary."""
    from leaders_db.db.engine import init_database
    from leaders_db.db.session import session_scope

    from ._resolve_indicators_factories import (
        COUNTRY_ISO3,
        TARGET_YEAR,
        UNDP_SOURCE_NAME,
        VDEM_SOURCE_NAME,
        WDI_SOURCE_NAME,
        WHO_SOURCE_NAME,
        add_observation,
        seed_country,
        upsert_source,
    )

    init_database(database_url)
    # Seed the minimum required rows for a real social_wellbeing
    # bundle. Four distinct sources so the result is a concrete
    # score, not an insufficient-data payload.
    with session_scope(database_url) as session:
        country = seed_country(session)
        undp = upsert_source(session, source_name=UNDP_SOURCE_NAME)
        who = upsert_source(session, source_name=WHO_SOURCE_NAME)
        wdi = upsert_source(session, source_name=WDI_SOURCE_NAME)
        vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)

        for var, value in (
            ("undp_hdi_hdi", 0.78),
            ("undp_hdi_life_expectancy", 0.70),
            ("undp_hdi_expected_years_schooling", 0.75),
            ("undp_hdi_mean_years_schooling", 0.65),
            ("undp_hdi_gni_per_capita", 0.70),
        ):
            add_observation(
                session,
                source_id=undp.id,
                country_id=country.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"undp_hdi:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        for var, value in (
            ("who_gho_under5_mortality", 0.85),
            ("who_gho_dtp3_immunization", 0.85),
        ):
            add_observation(
                session,
                source_id=who.id,
                country_id=country.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"who_gho_api:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        for var, value in (
            ("wdi_literacy_rate_adult", 0.95),
            ("wdi_gini_index", 0.60),
        ):
            add_observation(
                session,
                source_id=wdi.id,
                country_id=country.id,
                year=TARGET_YEAR,
                variable_name=var,
                raw_value=f"{value:.4f}",
                normalized_value=value,
                unit="index",
                source_row_reference=f"world_bank_wdi:{COUNTRY_ISO3}:{TARGET_YEAR}:{var}",
            )
        add_observation(
            session,
            source_id=vdem.id,
            country_id=country.id,
            year=TARGET_YEAR,
            variable_name="vdem_v2x_egal",
            raw_value="0.5500",
            normalized_value=0.55,
            unit="index",
            source_row_reference=f"vdem:{COUNTRY_ISO3}:{TARGET_YEAR}:v2x_egal",
        )

    config_path = _write_test_config(isolated_data_lake, database_url)
    result = runner.invoke(
        app,
        [
            "score-category",
            "--category",
            "social_wellbeing",
            "--year",
            "2023",
            "--country",
            "MEX",
            "--config",
            config_path,
        ],
    )
    assert result.exit_code == 0, result.stdout
    # The summary block must carry every field the Stage 9 path
    # is contracted to print (country/year/category/score,
    # observed/expected, human_review, observation_refs).
    assert "country:" in result.stdout
    assert "category:" in result.stdout
    assert "year:" in result.stdout
    assert "score:" in result.stdout
    assert "observed/expected:" in result.stdout
    assert "human_review:" in result.stdout
    assert "observation_refs:" in result.stdout
    # And the country/category/year values must appear too.
    assert "MEX" in result.stdout
    assert "social_wellbeing" in result.stdout
    assert "2023" in result.stdout
    # The seed is dense enough to emit a real score (not
    # insufficient_data); the score line carries the integer
    # 1..10 mapping.
    assert "/10" in result.stdout
