"""Research engine first-slice package."""

from .acquisition import acquired_evidence_to_observation
from .dataset_builder import build_analytical_dataset
from .effectiveness_8b import (
    EFFECTIVENESS_8B_METHOD_VERSION,
    Effectiveness8BEvaluation,
    EffectivenessCitation,
    persist_effectiveness_8b_evaluations,
)
from .planner import (
    QuestionSpecReviewNeeded,
    expand_scope_filter,
    plan_question,
    question_from_classification,
    validate_question_classification,
)
from .registry import get_question_spec_by_methodology_id, list_question_specs
from .runner import run_research_question

__all__ = [
    "EFFECTIVENESS_8B_METHOD_VERSION",
    "Effectiveness8BEvaluation",
    "EffectivenessCitation",
    "QuestionSpecReviewNeeded",
    "acquired_evidence_to_observation",
    "build_analytical_dataset",
    "expand_scope_filter",
    "get_question_spec_by_methodology_id",
    "list_question_specs",
    "persist_effectiveness_8b_evaluations",
    "plan_question",
    "question_from_classification",
    "run_research_question",
    "validate_question_classification",
]
