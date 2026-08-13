import pytest

from leaders_db.research.chapter_analysis_models import (
    ChapterAnalysisQuality,
    CorrectedLensAnswer,
    LensQuality,
)
from leaders_db.research.chapter_coverage_models import (
    CoveragePlan,
    CoverageRequirement,
    RepairedLensAnswer,
    RequirementDisposition,
    RequirementMapping,
    RoutedRequirementDisposition,
    validate_routed_dispositions,
)
from leaders_db.research.chapter_coverage_repair import (
    _drop_unknown_evidence_ids,
    _requirements,
    _validate_plan,
    _validate_repair,
)


def _quality() -> ChapterAnalysisQuality:
    return ChapterAnalysisQuality(
        chapter_id="3B",
        lens_quality=(
            LensQuality(
                question_id="3B.1",
                factual_support_1_to_5=4,
                completeness_1_to_5=3,
                balance_1_to_5=4,
                attribution_and_period_1_to_5=4,
                judge_usefulness_1_to_5=4,
                material_omissions=("Add omitted protection evidence.",),
            ),
        ),
        overall_verdict="pass_with_corrections",
        strengths=(),
        systemic_problems=(),
        concrete_corrections_required=("Clarify 3B.1 and 3B.2 separately.",),
        safe_for_judge_use=False,
        rationale="The chapter needs bounded corrections before judge use.",
    )


def test_requirements_preserve_lens_and_global_corrections() -> None:
    requirements = _requirements("3B", _quality())

    assert [item.requirement_id for item in requirements] == ["REQ-001", "REQ-002"]
    assert requirements[0].question_ids == ("3B.1",)
    assert requirements[1].question_ids == ("3B.1", "3B.2")


def test_plan_rejects_missing_requirement() -> None:
    requirements = (
        CoverageRequirement(
            requirement_id="REQ-001", question_ids=("3B.1",), instruction="Add it."
        ),
    )
    plan = CoveragePlan(chapter_id="3B", mappings=())

    with pytest.raises(ValueError, match="preserve every requirement"):
        _validate_plan(
            "3B", requirements, [{"id": "3B.1"}], {"E-1": object()}, plan
        )


def test_repair_requires_one_disposition_per_requirement() -> None:
    result = RepairedLensAnswer(
        answer=CorrectedLensAnswer(
            question_id="3B.1",
            answer=" ".join(["Evidence"] * 450),
            supporting_evidence_ids=("E-1",),
            contrary_or_qualifying_evidence_ids=(),
        ),
        dispositions=(
            RequirementDisposition(
                requirement_id="REQ-001",
                action="incorporated",
                explanation="The omitted evidence is now discussed.",
            ),
        ),
    )

    _validate_repair(result, "3B.1", {"E-1"}, {"REQ-001"})
    with pytest.raises(ValueError, match="every requirement"):
        _validate_repair(result, "3B.1", {"E-1"}, {"REQ-001", "REQ-002"})


def test_plan_rejects_invented_evidence() -> None:
    requirement = CoverageRequirement(
        requirement_id="REQ-001", question_ids=("3B.1",), instruction="Add it."
    )
    plan = CoveragePlan(
        chapter_id="3B",
        mappings=(
            RequirementMapping(
                requirement_id="REQ-001",
                question_ids=("3B.1",),
                evidence_ids=("E-2",),
                rationale="The record would address the correction.",
            ),
        ),
    )

    with pytest.raises(ValueError, match="invented an evidence ID"):
        _validate_plan(
            "3B", (requirement,), [{"id": "3B.1"}], {"E-1": object()}, plan
        )


def test_plan_normalization_drops_only_unknown_evidence_ids() -> None:
    plan = CoveragePlan(
        chapter_id="3B",
        mappings=(
            RequirementMapping(
                requirement_id="REQ-001",
                question_ids=("3B.1",),
                evidence_ids=("E-1", "INVENTED", "E-2"),
                rationale="Use the available records.",
            ),
        ),
    )

    normalized = _drop_unknown_evidence_ids(
        plan, {"E-1": object(), "E-2": object()}
    )

    assert normalized.mappings[0].evidence_ids == ("E-1", "E-2")
    assert normalized.mappings[0].question_ids == ("3B.1",)


def test_plan_cannot_reassign_an_immutable_question_route() -> None:
    requirement = CoverageRequirement(
        requirement_id="REQ-001", question_ids=("3B.1",), instruction="Add it."
    )
    plan = CoveragePlan(
        chapter_id="3B",
        mappings=(
            RequirementMapping(
                requirement_id="REQ-001",
                question_ids=("3B.2",),
                evidence_ids=("E-1",),
                rationale="The model selected another question.",
            ),
        ),
    )

    with pytest.raises(ValueError, match="immutable question route"):
        _validate_plan(
            "3B",
            (requirement,),
            [{"id": "3B.1"}, {"id": "3B.2"}],
            {"E-1": object()},
            plan,
        )


def test_final_dispositions_reconcile_each_requirement_question_route() -> None:
    disposition = RequirementDisposition(
        requirement_id="REQ-001",
        action="incorporated",
        explanation="The requirement was incorporated into this answer.",
    )
    routed = (
        RoutedRequirementDisposition(question_id="3B.1", disposition=disposition),
    )

    validate_routed_dispositions({("REQ-001", "3B.1")}, routed)
    with pytest.raises(ValueError, match="does not reconcile"):
        validate_routed_dispositions(
            {("REQ-001", "3B.1"), ("REQ-001", "3B.2")}, routed
        )
    with pytest.raises(ValueError, match="does not reconcile"):
        validate_routed_dispositions({("REQ-001", "3B.1")}, routed + routed)
