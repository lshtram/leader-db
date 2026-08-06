"""Tests for self-correcting chapter reading-list integrity."""

import pytest

from leaders_db.research.chapter_reading_list import (
    CritiqueIssue,
    ReadingListCritique,
    ReadingListDraft,
    ReadingListEntry,
    _reopen_ids,
    _validate_ids,
)
from tests.research.test_corpus_mapping_review import _evidence


def _entry(evidence_id: str, lenses: tuple[str, ...]) -> ReadingListEntry:
    return ReadingListEntry(
        evidence_id=evidence_id,
        reason_to_read="Material chapter evidence",
        role="mixed",
        supported_lenses=lenses,
    )


def test_reading_list_accepts_unique_in_chapter_ids() -> None:
    evidence = _evidence("E-1", "One material fact")

    _validate_ids("8B", {"E-1": evidence}, (_entry("E-1", ("8B.2",)),))


def test_reading_list_rejects_unknown_evidence() -> None:
    evidence = _evidence("E-1", "One material fact")

    with pytest.raises(ValueError, match="do not reconcile"):
        _validate_ids("8B", {"E-1": evidence}, (_entry("E-2", ("8B.2",)),))


def test_reading_list_rejects_cross_chapter_lens() -> None:
    evidence = _evidence("E-1", "One material fact")

    with pytest.raises(ValueError, match="out-of-chapter"):
        _validate_ids("8B", {"E-1": evidence}, (_entry("E-1", ("7B.2",)),))


def test_reopen_ids_adds_only_actionable_challenges() -> None:
    draft = ReadingListDraft(
        chapter_id="8B",
        chapter_overview="A sufficiently detailed chapter overview.",
        entries=(_entry("E-1", ("8B.1",)),),
    )
    critique = ReadingListCritique(
        chapter_id="8B",
        overall_assessment="A sufficiently detailed critique assessment.",
        issues=(
            CritiqueIssue(
                issue_type="material_omission",
                evidence_ids=("E-2",),
                explanation="A material omitted record.",
                recommended_action="add",
            ),
            CritiqueIssue(
                issue_type="irrelevant_selection",
                evidence_ids=("E-3",),
                explanation="An item recommended for removal.",
                recommended_action="remove",
            ),
        ),
    )

    assert _reopen_ids(draft, critique) == {"E-1", "E-2"}
