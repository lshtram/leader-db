import hashlib

import pytest

from leaders_db.research.chapter_analysis_models import ChapterQualityReviewBinding
from leaders_db.research.ruler_html_report import (
    _chapters,
    _linked_answer,
    _safe_href,
    _validate_review_binding,
)
from leaders_db.research.ruler_report_profile import usage_row


def test_linked_answer_links_only_supplied_evidence_ids() -> None:
    rendered = _linked_answer(
        "Supported by E-1 but not by E-2.",
        ("E-1",),
    )

    assert 'href="#ev-E-1"' in rendered
    assert 'href="#ev-E-2"' not in rendered


def test_usage_row_ignores_calls_without_completed_usage() -> None:
    row = usage_row(
        "stage",
        [
            None,
            {
                "input_tokens": 100,
                "cached_input_tokens": 20,
                "output_tokens": 10,
                "reasoning_output_tokens": 3,
            },
        ],
    )

    assert row == {
        "phase": "stage",
        "calls": 1,
        "input": 100,
        "cached": 20,
        "output": 10,
        "reasoning": 3,
    }


def test_safe_href_rejects_active_non_web_schemes() -> None:
    assert _safe_href("https://example.org/report") == "https://example.org/report"
    assert _safe_href("javascript:alert(1)") == "#"


def test_chapters_rejects_an_incomplete_approval_manifest(tmp_path) -> None:
    manifest = {"chapters": [{"chapter_id": "1B"}]}

    with pytest.raises(ValueError, match="chapters 1B through 8B"):
        _chapters(tmp_path, manifest, set())


def test_chapters_requires_independent_full_index_review_contract(tmp_path) -> None:
    manifest = {
        "chapters": [{"chapter_id": f"{index}B"} for index in range(1, 9)]
    }

    with pytest.raises(ValueError, match="independent full-index review"):
        _chapters(tmp_path, manifest, set())


def test_review_must_be_bound_to_selected_analysis_hash(tmp_path) -> None:
    analysis_path = tmp_path / "analysis.json"
    review_path = tmp_path / "review.json"
    package_path = tmp_path / "package.json"
    binding_path = tmp_path / "binding.json"
    analysis_path.write_text("selected analysis", encoding="utf-8")
    review_path.write_text("independent review", encoding="utf-8")
    package_path.write_text("full candidate index", encoding="utf-8")

    def digest(path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    binding = ChapterQualityReviewBinding(
        contract="independent-full-index-v1",
        chapter_id="1B",
        analysis_sha256=digest(analysis_path),
        judge_package_sha256=digest(package_path),
        review_sha256=digest(review_path),
    )
    binding_path.write_text(binding.model_dump_json(), encoding="utf-8")
    item = {
        "chapter_id": "1B",
        "review_binding_path": binding_path.name,
        "review_binding_sha256": digest(binding_path),
    }
    _validate_review_binding(
        item, tmp_path, analysis_path, review_path, package_path
    )

    analysis_path.write_text("different analysis", encoding="utf-8")
    with pytest.raises(ValueError, match="not bound"):
        _validate_review_binding(
            item, tmp_path, analysis_path, review_path, package_path
        )
