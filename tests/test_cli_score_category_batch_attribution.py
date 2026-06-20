"""CLI tests for the ``score-category --all-countries`` source
attribution block (AGENTS.md rule #15 — CLI output path).

The CLI ``score-category --all-countries`` writes the same CSV
the direct :func:`leaders_db.score.stage9.write_score_results_csv`
helper writes, so the CLI output path inherits the same
attribution contract. This is the runtime proof that AGENTS.md
rule #15 ("carry source attribution forward in every public
output") is satisfied end-to-end through the CLI surface, not
just through the in-process helper.

The happy-path CLI surface tests live in
:mod:`tests.test_cli_score_category_batch` and the error /
default-output tests live in
:mod:`tests.test_cli_score_category_batch_errors`; this file
is the third sibling that focuses on the AGENTS.md rule #15
attribution block at the CLI surface.
"""

from __future__ import annotations

from pathlib import Path

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
    """Seed MEX (dense) + BRA (no observations).

    Mirror of the helper in :mod:`tests.test_cli_score_category_batch`;
    the seeds are duplicated here so the attribution test file is
    standalone (no private import from a sibling).
    """
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


def _read_csv_attribution_lines(path: Path) -> list[str]:
    """Return the ``# Attribution: ...`` lines from ``path``.

    Local mirror of the helper in :mod:`tests.test_score_stage9_attribution`
    so this file stays self-contained and does not import a
    private helper from the batch test module.
    """
    lines: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.rstrip("\r\n")
            if stripped.startswith("#"):
                lines.append(stripped)
            else:
                break
    return lines


# ---------------------------------------------------------------------------
# Attribution block — runtime proof of AGENTS.md rule #15
# ---------------------------------------------------------------------------


def test_score_category_all_countries_csv_carries_attribution(
    isolated_data_lake, database_url: str
) -> None:
    """The CLI-generated CSV opens with the source attribution block.

    This is the CLI output path test for AGENTS.md rule #15:
    the :func:`leaders_db.cli._run_score_category_all_countries`
    helper must pass the category through to
    :func:`write_score_results_csv` so the attribution block
    is emitted on the actual ``data/outputs/<category>_<year>_scores.csv``
    file a human reviews. ``client_existing`` is never listed
    in the attribution (AGENTS.md rule #6).
    """
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

    attribution_lines = _read_csv_attribution_lines(expected)
    # Exactly one attribution line per expected social_wellbeing
    # source; the CLI passes ``category="social_wellbeing"``
    # explicitly so the block is present even though the
    # dispatcher could in principle resolve it from the first
    # :class:`ScoreResult`.
    assert len(attribution_lines) == 4
    expected_phrases = [
        "UNDP HDR 2023-24",
        "WHO Global Health Observatory",
        "World Bank WDI",
        "V-Dem v16",
    ]
    for phrase in expected_phrases:
        assert any(phrase in line for line in attribution_lines), (
            f"missing attribution for {phrase!r} in CLI-generated CSV "
            f"(attribution lines: {attribution_lines!r})"
        )
    # ``client_existing`` must NOT appear in the deterministic
    # attribution block (AGENTS.md rule #6).
    joined = " ".join(attribution_lines)
    assert "client" not in joined.lower()


__all__ = [
    "_read_csv_attribution_lines",
    "_seed_two_countries",
    "_write_test_config",
    "test_score_category_all_countries_csv_carries_attribution",
]
