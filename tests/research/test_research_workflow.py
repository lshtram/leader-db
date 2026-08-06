from pathlib import Path

import pytest

from leaders_db.research.research_workflow import ResearchWorkflow, load_research_workflow


def test_repository_workflow_is_sequential_and_allows_three_review_rounds() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = load_research_workflow(root / "configs/research-workflow.yaml")

    assert workflow.chapter_order == tuple(f"{index}B" for index in range(1, 9))
    assert workflow.max_review_rounds == 3
    assert workflow.minimum_source_claim_units_per_chapter == 5
    assert workflow.maximum_source_claim_units_per_chapter == 20
    assert workflow.chapter_research_turns_enabled is True
    assert workflow.chapter_candidate_document_target == 30
    assert workflow.chapter_opened_document_target == 12
    assert workflow.researcher_receives_compact_briefing is True
    assert workflow.complete_local_package_stays_parent_owned is True
    assert workflow.researcher_session_scope == "one_ruler_period"
    assert workflow.chapter_session_mode == "persistent_thread"
    assert workflow.continuation_minimum_expected_new_units_per_selected_chapter == 2
    assert workflow.continuation_marginal_value_policy_enabled is True
    assert workflow.supervisor_takeover_enabled is True
    assert workflow.supervisor_takeover_after_research_attempts == 2


def test_workflow_rejects_missing_or_reordered_chapters() -> None:
    with pytest.raises(ValueError, match="chapter_order"):
        ResearchWorkflow(
            version=1,
            chapter_order=("2B", "1B"),
            max_review_rounds=3,
        )


def test_workflow_rejects_session_scope_mode_mismatch() -> None:
    with pytest.raises(ValueError, match="researcher_session_scope"):
        ResearchWorkflow(
            version=1,
            chapter_order=tuple(f"{index}B" for index in range(1, 9)),
            researcher_session_scope="one_ruler_period",
            chapter_session_mode="fresh_compact_context",
        )
