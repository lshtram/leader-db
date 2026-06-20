"""CLI tests for the ``score-category`` error and default-output paths.

The Stage 9 ``--all-countries`` batch path has a happy-path
sibling at :mod:`tests.test_cli_score_category_batch` and an
attribution-block sibling at
:mod:`tests.test_cli_score_category_batch_attribution`; this
file is the third sibling that covers the error paths and the
default no-flag batch stub.

The tests cover:

- ``--all-countries --category <unsupported>`` fails with the
  supported set listed in the error message so a future caller
  can pick the right key without reading the CLI source;
- ``--country`` + ``--all-countries`` together fail with a clear
  mutual-exclusion error (the two paths have different shapes:
  one row per country vs. one row per the explicit
  ``--country`` value);
- the no-args, no-``--country``, no-``--all-countries`` path
  preserves the existing "not implemented yet" stub so existing
  callers see no behaviour change.

The error tests do not seed any observations — they only call
``init_database`` so the CLI does not fail on the missing-table
boundary before the targeted error path fires.
"""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.config import RunConfig
from leaders_db.db.engine import init_database

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


# ---------------------------------------------------------------------------
# Unsupported category
# ---------------------------------------------------------------------------


def test_score_category_all_countries_unsupported_category_fails(
    isolated_data_lake, database_url: str
) -> None:
    """An unsupported category fails with the supported set listed."""
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
            "--all-countries",
            "--config",
            config_path,
        ],
    )
    assert result.exit_code != 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "corruption" in combined
    assert "social_wellbeing" in combined


# ---------------------------------------------------------------------------
# Mutual exclusion
# ---------------------------------------------------------------------------


def test_score_category_country_and_all_countries_are_mutually_exclusive(
    isolated_data_lake, database_url: str
) -> None:
    """``--country`` and ``--all-countries`` together fail with a clear error."""
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
            "MEX",
            "--all-countries",
            "--config",
            config_path,
        ],
    )
    assert result.exit_code != 0, result.stdout
    combined = result.stdout + (result.stderr or "")
    assert "mutually exclusive" in combined


# ---------------------------------------------------------------------------
# Stub path (no --country, no --all-countries) — kept for coverage
# ---------------------------------------------------------------------------


def test_score_category_without_country_or_all_countries_keeps_stub(
    isolated_data_lake, database_url: str
) -> None:
    """No ``--country`` and no ``--all-countries`` keeps the batch stub.

    This is the existing behaviour preserved by the new ``--all-countries``
    path. The stub message must stay stable so existing callers do
    not see a behaviour change.
    """
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
    assert "[stub]" in result.stdout
    assert "not implemented yet" in result.stdout


__all__ = [
    "_write_test_config",
    "test_score_category_all_countries_unsupported_category_fails",
    "test_score_category_country_and_all_countries_are_mutually_exclusive",
    "test_score_category_without_country_or_all_countries_keeps_stub",
]
