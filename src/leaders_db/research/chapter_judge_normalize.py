"""Conservative normalization for chapter-judge candidate output."""

from __future__ import annotations

from typing import Any

from .chapter_projection import RulerChapterProjection


def _is_duplicate_placeholder(evaluation: dict[str, Any]) -> bool:
    """Recognize an explicit non-judgment duplicate row without guessing."""

    reason = str(evaluation.get("insufficient_evidence_reason") or "").casefold()
    return evaluation.get("score_1_to_10") is None and "duplicate placeholder" in reason


def _normalize_judgment_envelope(evaluation: dict[str, Any]) -> None:
    """Canonicalize null fields or scored review taxonomy without changing substance."""

    if "score_1_to_10" not in evaluation:
        return
    if evaluation["score_1_to_10"] is not None:
        if (
            evaluation.get("manual_review_required") is True
            and evaluation.get("manual_review_reason_type") == "recoverable_null"
        ):
            evaluation["manual_review_reason_type"] = "decisive_source"
        return
    reason = str(evaluation.get("insufficient_evidence_reason") or "").strip()
    if not reason:
        reason = "The judge returned no defensible score; see the chapter rationale."
    evaluation["insufficient_evidence_reason"] = reason
    evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}
    evaluation["manual_review_required"] = True
    evaluation["manual_review_reason_type"] = "recoverable_null"
    if not str(evaluation.get("manual_review_reason") or "").strip():
        evaluation["manual_review_reason"] = (
            "Release is blocked pending targeted evidence recovery or explicit "
            "confirmation that the chapter remains unjudgeable."
        )


def _normalize_calibration_references(
    evaluation: dict[str, Any], *, available_dossier_keys: set[str]
) -> None:
    """Rebind uniquely identified ruler-year references to canonical job keys.

    A judge can preserve the correct ``year:ISO:ruler_year_id`` while copying a
    stale run prefix from another cohort. That formatting defect is safe to repair
    only when the suffix resolves uniquely. Unknown references remain in place so
    strict validation rejects them. A singleton prose sentinel becomes empty.
    """

    values = evaluation.get("calibrated_against")
    if not isinstance(values, list):
        return
    if len(available_dossier_keys) == 1:
        evaluation["calibrated_against"] = list(
            dict.fromkeys(str(value) for value in values if str(value) in available_dossier_keys)
        )
        return
    canonical_by_suffix = {":".join(key.rsplit(":", 3)[-3:]): key for key in available_dossier_keys}
    normalized = []
    for value in values:
        reference = str(value)
        suffix = ":".join(reference.rsplit(":", 3)[-3:])
        normalized.append(
            reference
            if reference in available_dossier_keys
            else canonical_by_suffix.get(suffix, reference)
        )
    evaluation["calibrated_against"] = list(dict.fromkeys(normalized))


def _ensure_bias_assessment(evaluation: dict[str, Any], *, valid_evidence_ids: set[str]) -> None:
    """Retain an otherwise usable judgment while exposing missing bias reasoning."""

    assessment = evaluation.get("bias_assessment")
    if isinstance(assessment, dict):
        findings = assessment.get("material_biases")
        retained_findings: list[dict[str, Any]] = []
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                raw_ids = finding.get("supporting_evidence_ids")
                valid_ids = (
                    [
                        str(evidence_id)
                        for evidence_id in raw_ids
                        if str(evidence_id) in valid_evidence_ids
                    ]
                    if isinstance(raw_ids, list)
                    else []
                )
                if not valid_ids:
                    continue
                finding["supporting_evidence_ids"] = list(dict.fromkeys(valid_ids))
                retained_findings.append(finding)
        if retained_findings:
            assessment["material_biases"] = retained_findings
            return
        evaluation.pop("bias_assessment", None)
        existing = str(evaluation.get("manual_review_reason") or "").strip()
        suffix = (
            "Producer bias findings had no same-dossier evidence references; "
            "a conservative fallback assessment was applied."
        )
        evaluation["manual_review_reason"] = f"{existing} {suffix}".strip()
        evaluation["manual_review_required"] = True
        evaluation["manual_review_reason_type"] = "projection_integrity"
    if not valid_evidence_ids:
        evaluation["bias_assessment"] = {
            "material_biases": [],
            "confidence_and_range_effect": (
                "No same-dossier evidence was available to support a material bias "
                "finding; confidence remains minimal and the full range is retained."
            ),
            "remaining_uncertainty": (
                "The evidence environment cannot be assessed with cited chapter evidence."
            ),
            "report_volume_not_used_as_severity": True,
            "no_blanket_regime_correction": True,
        }
        return
    evidence_id = sorted(valid_evidence_ids)[0]
    evaluation["bias_assessment"] = {
        "material_biases": [
            {
                "bias": "Bias assessment omitted by the producer",
                "supporting_evidence_ids": [evidence_id],
                "likely_direction": "uncertain",
                "interpretation_effect": (
                    "No result-changing interpretation adjustment was inferred."
                ),
            }
        ],
        "confidence_and_range_effect": (
            "Confidence is capped and the range widened pending bias review."
        ),
        "remaining_uncertainty": "The omitted bias assessment remains unresolved.",
        "report_volume_not_used_as_severity": True,
        "no_blanket_regime_correction": True,
    }
    confidence = evaluation.get("confidence_score")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        evaluation["confidence_score"] = min(float(confidence), 50.0)
    score_range = evaluation.get("plausible_score_range")
    if isinstance(score_range, dict):
        lower = score_range.get("lower")
        upper = score_range.get("upper")
        if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
            score_range["lower"] = max(1, float(lower) - 1)
            score_range["upper"] = min(10, float(upper) + 1)


def _normalize_lens_lists(evaluation: dict[str, Any], *, valid_methodology_ids: set[str]) -> None:
    """Keep free-form gap observations without treating them as methodology IDs."""

    qualitative_gaps: list[str] = []
    supported: set[str] = set()
    for field in ("supported_lenses", "missing_or_weak_lenses"):
        values = evaluation.get(field)
        if not isinstance(values, list):
            continue
        normalized_values = [
            (_lens_id_from_value(value, valid_methodology_ids), str(value)) for value in values
        ]
        valid_values = [lens_id for lens_id, _ in normalized_values if lens_id]
        if field == "supported_lenses":
            supported = set(valid_values)
        if field == "missing_or_weak_lenses":
            qualitative_gaps.extend(
                original
                for lens_id, original in normalized_values
                if not lens_id or original != lens_id
            )
            overlap = list(dict.fromkeys(value for value in valid_values if value in supported))
            if overlap:
                qualitative_gaps.append(
                    "Partially supported but weak lenses: " + ", ".join(overlap)
                )
            valid_values = [value for value in valid_values if value not in supported]
        evaluation[field] = list(dict.fromkeys(valid_values))
    if qualitative_gaps:
        existing = str(evaluation.get("manual_review_reason") or "").strip()
        suffix = "Additional weak areas: " + "; ".join(qualitative_gaps)
        evaluation["manual_review_reason"] = f"{existing} {suffix}".strip()


def _lens_id_from_value(value: object, valid_methodology_ids: set[str]) -> str:
    """Recover a valid lens ID from an exact value or a descriptive prefix."""

    text = str(value).strip()
    if text in valid_methodology_ids:
        return text
    prefix = text.split(maxsplit=1)[0].rstrip(":;,-") if text else ""
    return prefix if prefix in valid_methodology_ids else ""


def _normalize_evidence_reference_lists(
    evaluation: dict[str, Any], *, valid_evidence_ids: set[str]
) -> None:
    """Drop unverifiable decisive references without guessing replacement IDs."""

    dropped: list[str] = []
    for field in (
        "decisive_positive_evidence",
        "decisive_negative_evidence",
        "contrary_evidence",
    ):
        values = evaluation.get(field)
        if not isinstance(values, list):
            continue
        retained: list[object] = []
        for value in values:
            if not isinstance(value, dict):
                retained.append(value)
                continue
            evidence_id = str(value.get("evidence_id", ""))
            if evidence_id not in valid_evidence_ids:
                dropped.append(evidence_id or "<missing>")
                continue
            retained.append(value)
        evaluation[field] = retained
    if dropped:
        existing = str(evaluation.get("manual_review_reason") or "").strip()
        suffix = (
            "Dropped out-of-projection evidence references during normalization: "
            + ", ".join(dict.fromkeys(dropped))
            + "."
        )
        evaluation["manual_review_reason"] = f"{existing} {suffix}".strip()
        evaluation["manual_review_required"] = True
        evaluation["manual_review_reason_type"] = "projection_integrity"


def _normalize_local_evidence_reference_lists(
    evaluation: dict[str, Any],
    *,
    valid_local_evidence_ids: set[str],
) -> None:
    """Drop local references not present in the parent-built package."""

    dropped: list[str] = []
    for field in ("decisive_local_evidence", "contextual_local_evidence"):
        values = evaluation.get(field)
        if values is None:
            evaluation[field] = []
            continue
        if not isinstance(values, list):
            dropped.append(f"{field}:<non-list>")
            evaluation[field] = []
            continue
        retained: list[object] = []
        for value in values:
            if not isinstance(value, dict):
                dropped.append(f"{field}:<non-object>")
                continue
            evidence_id = str(value.get("local_evidence_id", ""))
            if evidence_id not in valid_local_evidence_ids:
                dropped.append(evidence_id or "<missing>")
                continue
            retained.append(value)
        evaluation[field] = retained
    if dropped:
        existing = str(evaluation.get("manual_review_reason") or "").strip()
        suffix = (
            "Dropped out-of-package local evidence references during normalization: "
            + ", ".join(dict.fromkeys(dropped))
            + "."
        )
        evaluation["manual_review_reason"] = f"{existing} {suffix}".strip()
        evaluation["manual_review_required"] = True
        evaluation["manual_review_reason_type"] = "projection_integrity"


def _local_evidence_ids(projection: RulerChapterProjection) -> set[str]:
    """Return local fact and signal IDs available to one judge projection."""

    package = projection.local_evidence.package
    if package is None:
        return set()
    return {
        *(fact.fact_id for fact in package.facts),
        *(signal.signal_id for signal in package.longitudinal_signals),
    }


def _normalize_confidence_scale(evaluations: list[object], *, candidate: dict[str, Any]) -> None:
    """Normalize an unambiguous batch-wide 0-1 confidence scale to 0-100."""

    values: list[float] = []
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            return
        value = evaluation.get("confidence_score")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        values.append(float(value))
    if not values or not all(0 <= value <= 1 for value in values):
        return
    if not any(0 < value < 1 for value in values):
        return
    for evaluation in evaluations:
        assert isinstance(evaluation, dict)
        evaluation["confidence_score"] = round(float(evaluation["confidence_score"]) * 100, 6)
    note = "Confidence scores normalized from a batch-wide 0-1 scale to 0-100."
    notes = candidate.get("batch_notes")
    if isinstance(notes, list):
        if note not in notes:
            notes.append(note)
    else:
        candidate["batch_notes"] = [note]
