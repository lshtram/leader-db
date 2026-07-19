"""Regression tests for the static 2023 client-results viewer payload."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts/build_client_results_viewer.py"
CONFIG = PROJECT_ROOT / "configs/client-viewers/2023-top20-v1.yaml"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_client_results_viewer", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mse_excludes_missing_scores() -> None:
    module = _module()
    automated = {chapter: None for chapter in module.CHAPTER_TITLES}
    client = {chapter: 5.0 for chapter in module.CHAPTER_TITLES}
    automated["1B"] = 7.0

    assert module._mse(automated, client) == (4.0, 1)


def test_reader_abstract_does_not_duplicate_anchor_reasoning() -> None:
    module = _module()
    judgment = {
        "ruler_name": "Example Ruler",
        "period_start_year": 2024,
        "period_end_year": 2024,
        "score_1_to_10": 6.0,
        "higher_anchor_rejected": "I did not go higher because serious failures remain.",
        "lower_anchor_rejected": "Real protections remained in place.",
    }

    abstract = module._reader_abstract(
        judgment,
        chapter_title="Domestic safety",
        evidence_by_id={},
    )

    assert "because I did not" not in abstract
    assert "I did not go higher because serious failures remain." in abstract
    assert "I did not go lower because real protections remained in place." in abstract


def test_2023_payload_joins_scores_dossiers_and_all_lenses() -> None:
    module = _module()
    payload = module.build_payload(module.load_config(CONFIG))

    assert len(payload["rulers"]) == 20
    assert payload["overall_comparable_cells"] == 144
    assert payload["overall_mse"] == 1.571
    assert "corrected evidence-preservation" in payload["methodology_update"]

    usa = next(row for row in payload["rulers"] if row["iso3"] == "USA")
    assert usa["source_run"] == "repair"
    assert usa["automated_scores"]["1B"] == 7.0
    assert usa["client_scores"]["1B"] == 7.0
    assert len(usa["chapters"]) == 8
    assert all(len(chapter["lenses"]) == 10 for chapter in usa["chapters"])
    assert any(
        evidence.get("url", "").startswith("http")
        for chapter in usa["chapters"]
        for evidence in chapter["evidence"]
    )

    scholz = next(row for row in payload["rulers"] if row["iso3"] == "DEU")
    integrity = next(
        chapter for chapter in scholz["chapters"] if chapter["chapter_id"] == "7B"
    )
    abstract = integrity["judge"]["reader_abstract"]
    assert abstract.startswith(
        "Overall, Olaf Scholz's record on integrity in 2023 was assessed as mixed"
    )
    assert "Scholz recalled a 2017 Warburg meeting" in abstract
    assert "Whistleblower Protection Act" in abstract
    assert "score of 5.5 out of 10" in abstract

    hasina = next(row for row in payload["rulers"] if row["iso3"] == "BGD")
    hasina_integrity = next(
        chapter for chapter in hasina["chapters"] if chapter["chapter_id"] == "7B"
    )
    assert hasina_integrity["judge"]["score_1_to_10"] == 3.5
    assert any(
        item["evidence_id"] == "S7B-BGD-01"
        for item in hasina_integrity["evidence"]
    )

    thailand = next(row for row in payload["rulers"] if row["iso3"] == "THA")
    assert thailand["automated_scores"]["4B"] == 4.5
    assert thailand["automated_scores"]["6B"] == 5.5
    assert thailand["automated_scores"]["1B"] is None
    assert thailand["automated_scores"]["7B"] == 5.0

    non_nuclear_nulls = [
        chapter
        for ruler in payload["rulers"]
        for chapter in ruler["chapters"]
        if chapter["chapter_id"] != "1B"
        and chapter["judge"]["score_1_to_10"] is None
    ]
    assert non_nuclear_nulls == []

    vietnam = next(row for row in payload["rulers"] if row["iso3"] == "VNM")
    social = next(
        chapter for chapter in vietnam["chapters"] if chapter["chapter_id"] == "6B"
    )
    assert social["judge"]["score_1_to_10"] == 5.5
    assert any(item["evidence_id"] == "S6B-VNM-02" for item in social["evidence"])


def test_viewer_assets_reference_payload_and_interaction() -> None:
    page = (PROJECT_ROOT / "docs/client-results/2023-top20/index.html").read_text()
    script = (PROJECT_ROOT / "docs/client-results/2023-top20/viewer.js").read_text()

    assert "Rulers × chapters" in page
    assert 'fetch("data.json")' in script
    assert 'class="chapter"' in script
    assert "judge.reader_abstract" in script
    assert "Pending corrected-flow review" in script
    assert 'id="methodology-update"' in page
    assert "renderRecord(button.dataset.iso3, button.dataset.chapter)" in script
