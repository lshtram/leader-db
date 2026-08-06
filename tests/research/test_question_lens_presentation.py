from __future__ import annotations

from copy import deepcopy
from pathlib import Path

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


def test_methodology_v2_keeps_six_categories_and_corrects_nuclear_exception() -> None:
    question_catalog = load("questions.json")
    presentation = load_question_lens_presentation()
    first_question = question_catalog["chapters"][0]["questions"][0]

    assert question_catalog["schema_version"] == "ruler-quality-questions-v2"
    assert presentation.version == "layered_lenses_v2"
    assert len(presentation.evidence_categories) == 6
    assert "adverse unless modernization" in first_question["text"]
    assert "accounts of arsenal size" not in render_evidence_category_key().lower()


def test_all_eighty_lenses_match_every_published_methodology_table(
    project_root: Path,
) -> None:
    presentation = load_question_lens_presentation()
    questions_by_id = {item["id"]: item["text"] for item in questions()}
    published = (
        project_root / "docs/methodology/ranking-evaluation-criteria.md",
        project_root / "docs/methodology/pipeline-agent-questions-and-prompts.md",
    )

    for lens in presentation.lenses:
        guide = next(
            (project_root / "docs/methodology/chapter-guides").glob(
                f"{lens.id.split('.', maxsplit=1)[0].lower()}-*.md"
            )
        ).read_text(encoding="utf-8")
        expected = (
            f"**{lens.id} — {lens.title}** | {lens.simple_question} | "
            f"{questions_by_id[lens.id]}"
        )
        assert expected in guide
        for path in published:
            assert expected in path.read_text(encoding="utf-8")


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
