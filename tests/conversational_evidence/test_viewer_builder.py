"""Tests for release-selectable conversational viewer judgments."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "build_conversational_results_viewer.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("conversational_viewer_builder", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_judgment_manifest_overrides_only_selected_chapter(tmp_path: Path) -> None:
    module = _module()
    (tmp_path / "viewer-judgments.json").write_text(
        json.dumps({"chapter_judgments": {"3B": "judgments-3b-v4/3B/judgment.json"}}),
        encoding="utf-8",
    )

    paths = module._judgment_paths(tmp_path, ("2B", "3B", "4B"))

    assert paths["2B"] == tmp_path / "judgments-v2/2B/judgment.json"
    assert paths["3B"] == (tmp_path / "judgments-3b-v4/3B/judgment.json").resolve()
    assert paths["4B"] == tmp_path / "judgments-v2/4B/judgment.json"


def test_2022_batch_metadata_is_not_hard_coded_to_2024() -> None:
    module = _module()
    batch_dir = (
        PROJECT_ROOT
        / "research/conversational-evidence/hybrid-experiment/2022-top20-v2"
    )

    payload = module.build_payload(batch_dir)

    assert payload["target_year"] == 2022
    assert payload["release_id"] == "2022-top20-hybrid-v2"
    assert payload["overall_scored_cells"] == 155
    assert all(
        ruler["source_run"] == "2022 conversational evidence"
        for ruler in payload["rulers"]
    )
