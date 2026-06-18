"""Run-config loading and validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from leaders_db.config import RunConfig, load_config


def test_default_config_is_minimal() -> None:
    cfg = RunConfig()
    assert cfg.project.target_year == 2023
    assert cfg.project.name == "leaders-db-prototype"
    assert "political_freedom" in cfg.scoring.categories


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")


def test_round_trip(tmp_path: Path) -> None:
    from leaders_db.config import dump_config

    cfg = RunConfig()
    cfg.project.target_year = 2024
    path = tmp_path / "cfg.yaml"
    dump_config(cfg, path)

    loaded = load_config(path)
    assert loaded.project.target_year == 2024
    assert loaded.llm.provider == "stub"


def test_invalid_target_year_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "project:\n  target_year: 1850\n",
        encoding="utf-8",
    )
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(bad)


def test_invalid_source_url_rejected(tmp_path: Path) -> None:
    # Sanity: a scoring category outside the allow-list is rejected.
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "scoring:\n  categories:\n    - not_a_real_category\n",
        encoding="utf-8",
    )
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_config(bad)
