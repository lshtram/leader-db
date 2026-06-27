import pytest

from leaders_db.research.models import ResearchQuestion, ScopeFilter
from leaders_db.research.planner import plan_question


def test_unsupported_question_key_raises_clear_error() -> None:
    question = ResearchQuestion(
        question_id="unknown",
        question_key="unknown_question",
        display_text="Unknown question.",
        concepts=("unknown_concept",),
        scope_filter=ScopeFilter(filters=()),
        analyses=("coverage",),
    )

    with pytest.raises(ValueError, match="Unsupported research question_key"):
        plan_question(question)
