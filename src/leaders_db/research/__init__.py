"""Research engine first-slice package."""

from .acquisition import acquired_evidence_to_observation
from .cited_evaluations import (
    CITED_EVALUATION_METHOD_VERSION,
    CitedEvaluation,
    CitedEvaluationCitation,
    build_cited_evaluation_template,
    cited_evaluation_json_schema,
    persist_cited_evaluations,
)
from .country_year_fact_answers import (
    COUNTRY_YEAR_FACTS_METHOD_VERSION,
    build_country_year_fact_answers,
    persist_country_year_fact_answers,
)
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
    "CITED_EVALUATION_METHOD_VERSION",
    "COUNTRY_YEAR_FACTS_METHOD_VERSION",
    "EFFECTIVENESS_8B_METHOD_VERSION",
    "CitedEvaluation",
    "CitedEvaluationCitation",
    "Effectiveness8BEvaluation",
    "EffectivenessCitation",
    "QuestionSpecReviewNeeded",
    "acquired_evidence_to_observation",
    "build_analytical_dataset",
    "build_cited_evaluation_template",
    "build_country_year_fact_answers",
    "cited_evaluation_json_schema",
    "expand_scope_filter",
    "get_question_spec_by_methodology_id",
    "list_question_specs",
    "persist_cited_evaluations",
    "persist_country_year_fact_answers",
    "persist_effectiveness_8b_evaluations",
    "plan_question",
    "question_from_classification",
    "run_research_question",
    "validate_question_classification",
]
