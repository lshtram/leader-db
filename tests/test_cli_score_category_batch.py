"""CLI tests for the Stage 9 ``--all-countries`` batch happy path on
``score-category``.

These tests live in a sibling test file so the canonical
``test_cli_smoke.py`` stays under the 400-line convention while
still covering every CLI surface. The Stage 9 narrow single-
country path tests stay in ``test_cli_smoke.py``; this file is
the equivalent surface for the all-countries batch happy path.
The error / mutual-exclusion / default-output tests live in
:mod:`tests.test_cli_score_category_batch_errors`; the
attribution-block CLI test lives in
:mod:`tests.test_cli_score_category_batch_attribution`.

The tests cover:

- ``--all-countries`` writes a CSV to the resolved output path
  with one row per ``Country`` and prints the concise summary;
- ``--all-countries --output <path>`` honours the override and
  creates parent directories.

The unsupported-category / mutual-exclusion / no-flag-batch-stub
paths are covered by :mod:`tests.test_cli_score_category_batch_errors`
so this file stays focused on the happy-path CLI surface.
"""

from __future__ import annotations

import csv

import yaml
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.config import RunConfig
from leaders_db.db.engine import init_database
from leaders_db.db.models import Country
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

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_test_config(
    isolated_data_lake, database_url: str
) -> str:
    """Persist a minimal RunConfig YAML under the isolated data lake."""
    cfg = RunConfig()
    cfg.database.url = database_url
    config_path = isolated_data_lake / "cfg.yaml"
    config_path.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return str(config_path)


def _seed_two_countries(database_url: str) -> None:
    """Seed MEX (dense) + BRA (no observations)."""
    init_database(database_url)
    with session_scope(database_url) as session:
        mexico = seed_country(session)
        brazil = Country(
            iso3="BRA",
            country_name="Brazil",
            country_name_normalized="brazil",
            region="LAC",
        )
        session.add(brazil)
        session.flush()

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
                country_id=mexico.id,
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
                country_id=mexico.id,
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
                country_id=mexico.id,
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
            country_id=mexico.id,
            year=TARGET_YEAR,
            variable_name="vdem_v2x_egal",
            raw_value="0.5500",
            normalized_value=0.55,
            unit="index",
            source_row_reference=f"vdem:{COUNTRY_ISO3}:{TARGET_YEAR}:v2x_egal",
        )


# ---------------------------------------------------------------------------
# All-countries batch path — happy path
# ---------------------------------------------------------------------------


def test_score_category_all_countries_default_output_path(
    isolated_data_lake, database_url: str
) -> None:
    """``--all-countries`` writes to ``data/outputs/<category>_<year>_scores.csv``."""
    _seed_two_countries(database_url)
    config_path = _write_test_config(isolated_data_lake, database_url)

    result = runner.invoke(
        app,
        [
            "score-category",
            "--category",
            "social_wellbeing",
            "--year",
            "2023",
            "--all-countries",
            "--config",
            config_path,
        ],
    )
    assert result.exit_code == 0, result.stdout

    expected = isolated_data_lake / "data" / "outputs" / "social_wellbeing_2023_scores.csv"
    assert expected.is_file()

    with expected.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    # Strip the ``# Attribution: ...`` comment block the writer
    # emits at the top of the CSV per AGENTS.md rule #15; the
    # remaining rows are the stable data header + one row per
    # :class:`ScoreResult` (BRA + MEX in iso3 order).
    data_rows = [row for row in rows if not (row and row[0].startswith("#"))]
    # Header + 2 country rows (BRA + MEX in iso3 order).
    assert len(data_rows) == 3
    assert "iso3" in data_rows[0]
    iso3s = [row[data_rows[0].index("iso3")] for row in data_rows[1:]]
    assert iso3s == ["BRA", "MEX"]


def test_score_category_all_countries_prints_summary(
    isolated_data_lake, database_url: str
) -> None:
    """The summary echoes rows, scored_count, insufficient_count, output path."""
    _seed_two_countries(database_url)
    config_path = _write_test_config(isolated_data_lake, database_url)

    result = runner.invoke(
        app,
        [
            "score-category",
            "--category",
            "social_wellbeing",
            "--year",
            "2023",
            "--all-countries",
            "--config",
            config_path,
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Done. Summary:" in result.stdout
    assert "rows:              2" in result.stdout
    assert "scored_count:      1" in result.stdout
    assert "insufficient_count: 1" in result.stdout
    assert "output_path:" in result.stdout
    assert "social_wellbeing_2023_scores.csv" in result.stdout


def test_score_category_all_countries_output_override_creates_parents(
    isolated_data_lake, database_url: str
) -> None:
    """``--output <path>`` overrides the default and creates parent dirs."""
    _seed_two_countries(database_url)
    config_path = _write_test_config(isolated_data_lake, database_url)
    output_path = isolated_data_lake / "nested" / "dir" / "scores.csv"

    result = runner.invoke(
        app,
        [
            "score-category",
            "--category",
            "social_wellbeing",
            "--year",
            "2023",
            "--all-countries",
            "--output",
            str(output_path),
            "--config",
            config_path,
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output_path.is_file()


__all__ = [
    "_seed_two_countries",
    "_write_test_config",
    "test_score_category_all_countries_default_output_path",
    "test_score_category_all_countries_output_override_creates_parents",
    "test_score_category_all_countries_prints_summary",
]
