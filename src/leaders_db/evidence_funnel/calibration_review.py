"""Normalize explicit fresh-review verdicts from M2.7 prose."""

from __future__ import annotations

import re
from pathlib import Path

from .calibration_review_json import normalize_json_reviews, unsupported_issue
from .low_cost import SemanticReview, SemanticReviewBatch
from .models import EvidenceCandidate

_SECTION = re.compile(
    r"### (EF-E[0-9a-f]{12})\s+—\s+\*\*(.+?)\*\*(.*?)(?=\n---|\n### Summary)",
    flags=re.DOTALL,
)
_SUMMARY_ROW = re.compile(
    r"^\|[ \t]*(EF-E[0-9a-f]{12})[ \t]*\|[ \t]*"
    r"\*\*(ACCEPT|REJECT|ESCALATE)\*\*[ \t]*\|[ \t]*(.*?)[ \t]*\|$",
    flags=re.MULTILINE,
)
_ARROW_VERDICT = re.compile(
    r"^\*\*(EF-E[0-9a-f]{12})[ \t]+→[ \t]+"
    r"(ACCEPT|REJECT|ESCALATE)\*\*[ \t]*$\n"
    r"(.*?)(?=\n---|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_SIMPLE_SECTION = re.compile(
    r"^### (EF-E[0-9a-f]{12})[ \t]*$\n+"
    r"\*\*Verdict:[ \t]*(ACCEPT|REJECT|ESCALATE)(?:[^*]*)\*\*\n+"
    r"(.*?)(?=^---[ \t]*$|^### EF-E[0-9a-f]{12}|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_BOLD_REVIEW_SECTION = re.compile(
    r"^\*\*(EF-E[0-9a-f]{12})\*\*[ \t]*$\n"
    r"(.*?)(?=^\*\*EF-E[0-9a-f]{12}\*\*|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_BOLD_TITLED_SECTION = re.compile(
    r"^\*\*(EF-E[0-9a-f]{12})\*\*[^\n]*\n"
    r"(.*?)(?=^\*\*EF-E[0-9a-f]{12}\*\*|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_BOLD_INLINE_SECTION = re.compile(
    r"^\*\*(EF-E[0-9a-f]{12})\s+—\s+"
    r"(ACCEPT|REJECT|ESCALATE)(?:[^*]*)\*\*[ \t]*$\n"
    r"(.*?)(?=^\*\*EF-E[0-9a-f]{12}\s+—|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_HEADING_ARROW_SECTION = re.compile(
    r"^## (EF-E[0-9a-f]{12})\s+→\s+\*\*"
    r"(ACCEPT|REJECT|ESCALATE)\*\*[ \t]*$\n"
    r"(.*?)(?=^---[ \t]*$|^## EF-E[0-9a-f]{12}|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_GENERIC_VERDICT_SECTION = re.compile(
    r"^[^\n]*(EF-E[0-9a-f]{12})[^\n]*?"
    r"\b(ACCEPT|REJECT|ESCALATE)\b[^\n]*\n"
    r"(.*?)(?=^[^\n]*EF-E[0-9a-f]{12}[^\n]*"
    r"\b(?:ACCEPT|REJECT|ESCALATE)\b|\Z)",
    flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
)
_HEADING_ASSESSMENT = re.compile(
    r"^### (EF-E[0-9a-f]{12})[ \t]*$\n"
    r"(.*?)(?=^---[ \t]*$|^### EF-E[0-9a-f]{12}|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_INLINE_VERDICT = re.compile(
    r"(?:\*{0,2}Verdict:\*{0,2}[ \t]*|"
    r"\*{0,2}Assessment:\*{0,2}[ \t]*)"
    r"`?(ACCEPT|REJECT|ESCALATE|PARTIAL)`?(?!\w)",
    flags=re.IGNORECASE,
)
_BARE_BOLD_VERDICT = re.compile(
    r"^\*\*(ACCEPT|REJECT|ESCALATE|PARTIAL)\.?\*\*[ \t]*$",
    flags=re.MULTILINE | re.IGNORECASE,
)


def normalize_review_report(  # noqa: PLR0912
    *,
    raw_path: Path,
    candidates: tuple[EvidenceCandidate, ...],
) -> SemanticReviewBatch:
    """Convert explicit per-ID verdicts; caveated support is rejected, not repaired."""

    raw = raw_path.read_text(encoding="utf-8")
    expected = {item.evidence_id for item in candidates}
    reviews = normalize_json_reviews(raw)
    for evidence_id, verdict, body in _SECTION.findall(raw):
        normalized = verdict.lower()
        labelled_status = (
            "accepted"
            if normalized.strip() == "accept"
            else "rejected"
            if "accept" in normalized
            or "reject" in normalized
            or "partial" in normalized
            else "escalated"
        )
        issue = _issue(body)
        status = (
            "rejected"
            if labelled_status == "accepted" and unsupported_issue(issue)
            else labelled_status
        )
        reviews.append(
            SemanticReview(
                evidence_id=evidence_id,
                status=status,
                explanation=issue,
                unsupported_elements=(issue,) if status == "rejected" else (),
            )
        )
    if not reviews:
        for evidence_id, verdict, issue in _SUMMARY_ROW.findall(raw):
            unsupported = unsupported_issue(issue)
            status = (
                "rejected"
                if verdict == "REJECT" or unsupported
                else "escalated"
                if verdict == "ESCALATE"
                else "accepted"
            )
            explanation = issue.strip() or "Reviewer found the bound claim supported."
            reviews.append(
                SemanticReview(
                    evidence_id=evidence_id,
                    status=status,
                    explanation=explanation,
                    unsupported_elements=(explanation,) if status == "rejected" else (),
                )
            )
    if {item.evidence_id for item in reviews} != expected:
        reviews = []
    if not reviews:
        for evidence_id, verdict, body in _ARROW_VERDICT.findall(raw):
            issue = re.sub(r"\s+", " ", body).strip()[:2000]
            unsupported = unsupported_issue(issue)
            status = (
                "rejected"
                if verdict == "REJECT" or unsupported
                else "escalated"
                if verdict == "ESCALATE"
                else "accepted"
            )
            reviews.append(
                SemanticReview(
                    evidence_id=evidence_id,
                    status=status,
                    explanation=issue or "Reviewer supplied an explicit verdict.",
                    unsupported_elements=(issue,) if status == "rejected" else (),
                )
            )
    if not reviews:
        for evidence_id, verdict, body in _SIMPLE_SECTION.findall(raw):
            issue = re.sub(r"\s+", " ", body).strip()[:2000]
            unsupported = unsupported_issue(issue)
            status = (
                "rejected"
                if verdict == "REJECT" or unsupported
                else "escalated"
                if verdict == "ESCALATE"
                else "accepted"
            )
            reviews.append(
                SemanticReview(
                    evidence_id=evidence_id,
                    status=status,
                    explanation=issue or "Reviewer supplied an explicit verdict.",
                    unsupported_elements=(issue,) if status == "rejected" else (),
                )
            )
    if not reviews:
        for pattern in (
            _BOLD_REVIEW_SECTION,
            _BOLD_TITLED_SECTION,
            _HEADING_ASSESSMENT,
        ):
            reviews.extend(_labelled_section_reviews(raw, pattern))
            if reviews:
                break
    if not reviews:
        for evidence_id, verdict, body in _BOLD_INLINE_SECTION.findall(raw):
            issue = re.sub(r"\s+", " ", body).strip()[:2000]
            unsupported = unsupported_issue(issue)
            status = (
                "rejected"
                if verdict == "REJECT" or unsupported
                else "escalated"
                if verdict == "ESCALATE"
                else "accepted"
            )
            reviews.append(
                SemanticReview(
                    evidence_id=evidence_id,
                    status=status,
                    explanation=issue or "Reviewer supplied an explicit verdict.",
                    unsupported_elements=(issue,) if status == "rejected" else (),
                )
            )
    if not reviews:
        for evidence_id, verdict, body in _HEADING_ARROW_SECTION.findall(raw):
            issue = re.sub(r"\s+", " ", body).strip()[:2000]
            unsupported = unsupported_issue(issue)
            normalized = verdict.lower()
            status = (
                "rejected"
                if normalized == "reject" or unsupported
                else "escalated"
                if normalized == "escalate"
                else "accepted"
            )
            reviews.append(
                SemanticReview(
                    evidence_id=evidence_id,
                    status=status,
                    explanation=issue or "Reviewer supplied an explicit verdict.",
                    unsupported_elements=(issue,) if status == "rejected" else (),
                )
            )
    if not reviews:
        for evidence_id, verdict, body in _GENERIC_VERDICT_SECTION.findall(raw):
            issue = re.sub(r"\s+", " ", body).strip()[:2000]
            unsupported = unsupported_issue(issue)
            normalized = verdict.lower()
            status = (
                "rejected"
                if normalized == "reject" or unsupported
                else "escalated"
                if normalized == "escalate"
                else "accepted"
            )
            reviews.append(
                SemanticReview(
                    evidence_id=evidence_id,
                    status=status,
                    explanation=issue or "Reviewer supplied an explicit verdict.",
                    unsupported_elements=(issue,) if status == "rejected" else (),
                )
            )
    actual = {item.evidence_id for item in reviews}
    if actual != expected:
        raise ValueError(
            f"review report accounting mismatch; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
    return SemanticReviewBatch(reviews=tuple(reviews))


def _labelled_section_reviews(
    raw: str,
    pattern: re.Pattern[str],
) -> list[SemanticReview]:
    reviews: list[SemanticReview] = []
    for evidence_id, body in pattern.findall(raw):
        verdicts = [
            match.group(1).lower()
            for verdict_pattern in (_INLINE_VERDICT, _BARE_BOLD_VERDICT)
            for match in verdict_pattern.finditer(body)
        ]
        if not verdicts:
            continue
        if len(set(verdicts)) > 1:
            raise ValueError(f"{evidence_id}: explicit review verdicts conflict")
        verdict = verdicts[0]
        issue = re.sub(r"\s+", " ", body).strip()[:2000]
        unsupported = unsupported_issue(issue)
        status = (
            "rejected"
            if verdict in {"reject", "partial"} or unsupported
            else "escalated"
            if verdict == "escalate"
            else "accepted"
        )
        reviews.append(
            SemanticReview(
                evidence_id=evidence_id,
                status=status,
                explanation=issue,
                unsupported_elements=(issue,) if status == "rejected" else (),
            )
        )
    return reviews


def latest_complete_review(
    stage_root: Path,
    candidates: tuple[EvidenceCandidate, ...],
) -> Path:
    """Return the latest report that accounts for every candidate."""

    for path in reversed(sorted(stage_root.glob("attempt-*/output.json"))):
        if not path.stat().st_size:
            continue
        try:
            normalize_review_report(raw_path=path, candidates=candidates)
        except ValueError:
            continue
        return path
    raise ValueError(f"no complete semantic review report exists: {stage_root}")


def reconcile_complete_reviews(
    stage_root: Path,
    candidates: tuple[EvidenceCandidate, ...],
) -> SemanticReviewBatch:
    """Reconcile every complete attempt and escalate conflicting verdicts."""

    reports: list[SemanticReviewBatch] = []
    for path in sorted(stage_root.glob("attempt-*/output.json")):
        if not path.stat().st_size:
            continue
        try:
            reports.append(normalize_review_report(raw_path=path, candidates=candidates))
        except ValueError:
            continue
    if not reports:
        raise ValueError(f"no complete semantic review report exists: {stage_root}")
    reconciled: list[SemanticReview] = []
    for candidate in candidates:
        attempts = tuple(
            next(
                review
                for review in report.reviews
                if review.evidence_id == candidate.evidence_id
            )
            for report in reports
        )
        statuses = {attempt.status for attempt in attempts}
        if len(statuses) == 1:
            reconciled.append(attempts[-1])
            continue
        explanation = "Reviewer attempts disagreed: " + " | ".join(
            f"{attempt.status}: {attempt.explanation}" for attempt in attempts
        )
        reconciled.append(
            SemanticReview(
                evidence_id=candidate.evidence_id,
                status="escalated",
                explanation=explanation,
                unsupported_elements=tuple(
                    element
                    for attempt in attempts
                    for element in attempt.unsupported_elements
                ),
            )
        )
    return SemanticReviewBatch(reviews=tuple(reconciled))


def _issue(body: str) -> str:
    verdict = re.search(
        r"\*\*Verdict:\*\*\s*(.*?)(?=\n\n|\Z)",
        body,
        flags=re.DOTALL,
    )
    value = verdict.group(1) if verdict else body
    return re.sub(r"\s+", " ", value).strip()[:2000]


__all__ = [
    "latest_complete_review",
    "normalize_review_report",
    "reconcile_complete_reviews",
]
