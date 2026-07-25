from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from leaders_db.conversational_evidence.data import QuestionCatalog, load, questions
from leaders_db.research.question_lens_presentation import (
    QuestionLensPresentation,
    load_question_lens_presentation,
    render_evidence_category_key,
    render_lens_table,
)


def test_layered_catalog_covers_all_questions_with_known_categories() -> None:
    catalog = load_question_lens_presentation()

    assert {lens.id for lens in catalog.lenses} == {
        item["id"] for item in questions()
    }
    assert all(
        len(lens.priority_categories) <= catalog.max_priority_categories
        for lens in catalog.lenses
    )


def test_layered_catalog_rejects_duplicate_ids_from_config() -> None:
    configured = deepcopy(load("question_lens_presentation.json"))
    configured["lenses"].append(deepcopy(configured["lenses"][0]))

    with pytest.raises(ValidationError, match="IDs must be unique"):
        QuestionLensPresentation.model_validate(configured)


def test_question_catalog_rejects_a_short_chapter() -> None:
    configured = deepcopy(load("questions.json"))
    configured["chapters"][0]["questions"].pop()

    with pytest.raises(ValidationError, match="configured chapter/lens grid"):
        QuestionCatalog.model_validate(configured)


def test_question_catalog_rejects_a_removed_configured_chapter() -> None:
    configured = deepcopy(load("questions.json"))
    configured["chapters"].pop()

    with pytest.raises(ValidationError, match="configured chapter IDs"):
        QuestionCatalog.model_validate(configured)


def test_question_catalog_rejects_a_renamed_lens_id() -> None:
    configured = deepcopy(load("questions.json"))
    configured["chapters"][0]["questions"][0]["id"] += "-renamed"

    with pytest.raises(ValidationError, match="configured chapter/lens grid"):
        QuestionCatalog.model_validate(configured)


def test_layered_table_preserves_selection_order_without_sibling_lenses() -> None:
    catalog = load_question_lens_presentation()
    first, sibling, second = catalog.lenses[:3]
    table = render_lens_table([second.id, first.id])

    assert table.index("Simple question") < table.index("Detailed research question")
    assert table.index(f"{second.id} —") < table.index(f"{first.id} —")
    assert f"{sibling.id} —" not in table
    assert len(table.splitlines()) == 2 + len((second, first))


def test_category_key_defines_categories_once_without_source_exclusivity() -> None:
    catalog = load_question_lens_presentation()
    key = render_evidence_category_key()

    assert key.count("\n- **") + 1 == len(catalog.evidence_categories)
    assert all(
        f"**{category.name}:**" in key
        for category in catalog.evidence_categories.values()
    )
