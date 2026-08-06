"""Matched-arm diagnostic comparison for the non-publication gate."""

from __future__ import annotations

from collections.abc import Callable

from .diagnostic_models import DiagnosticComparison, DiagnosticJudgment


def compare_diagnostic_judgments(
    closed_book: DiagnosticJudgment,
    reference: DiagnosticJudgment,
    *,
    fact_matches: Callable[[str, str], bool] | None = None,
    max_score_delta: float,
    rationale_consistent: bool,
    material_attribution_regression: bool,
) -> DiagnosticComparison:
    """Compare matched judgments without treating the result as a production score."""

    matcher = fact_matches or _exact_normalized_match
    missing_facts = tuple(
        fact
        for fact in reference.decisive_facts
        if not any(matcher(fact, candidate) for candidate in closed_book.decisive_facts)
    )
    missing_contrary = tuple(
        fact
        for fact in reference.contrary_evidence
        if not any(matcher(fact, candidate) for candidate in closed_book.contrary_evidence)
    )
    delta = closed_book.score_1_to_10 - reference.score_1_to_10
    if max_score_delta < 0:
        raise ValueError("max_score_delta cannot be negative")
    passed = (
        not missing_facts
        and not missing_contrary
        and not material_attribution_regression
        and rationale_consistent
        and abs(delta) <= max_score_delta
    )
    return DiagnosticComparison(
        schema_version="diagnostic_comparison_v1",
        closed_book=closed_book,
        reference=reference,
        score_delta=delta,
        missing_decisive_facts=missing_facts,
        missing_contrary_evidence=missing_contrary,
        material_attribution_regression=material_attribution_regression,
        rationale_consistent=rationale_consistent,
        gate_passed=passed,
        experimental_non_publication=True,
    )


def _exact_normalized_match(left: str, right: str) -> bool:
    return " ".join(left.casefold().split()) == " ".join(right.casefold().split())


__all__ = ["compare_diagnostic_judgments"]
