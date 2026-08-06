"""Strict JSON-dialect normalization for semantic review output."""

from __future__ import annotations

import json
import re
from typing import Any

from .low_cost import SemanticReview


def normalize_json_reviews(raw: str) -> list[SemanticReview]:
    """Normalize a JSON list or a fenced object containing ``reviews``."""

    payload = _json_payload(raw)
    if payload is None:
        return []
    rows = payload.get("reviews") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    reviews: list[SemanticReview] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("review JSON rows must be objects")
        evidence_id = row.get("evidence_id")
        verdict = _verdict_aliases(row)
        explanations = _explanation_aliases(row)
        explanation = explanations[0] if explanations else ""
        if not isinstance(evidence_id, str) or verdict not in {
            "accept",
            "accepted",
            "reject",
            "rejected",
            "escalate",
            "escalated",
        }:
            raise ValueError("review JSON row has invalid ID or verdict")
        if not explanation:
            raise ValueError("review JSON row lacks an explanation")
        unsupported = any(unsupported_issue(item) for item in explanations)
        status = (
            "rejected"
            if verdict in {"reject", "rejected"} or unsupported
            else "escalated"
            if verdict in {"escalate", "escalated"}
            else "accepted"
        )
        reviews.append(
            SemanticReview(
                evidence_id=evidence_id,
                status=status,
                explanation=explanation,
                unsupported_elements=(explanation,) if status == "rejected" else (),
            )
        )
    return reviews


def _verdict_aliases(row: dict[str, Any]) -> str:
    values: list[str] = []
    normalized = {
        "accepted": "accept",
        "rejected": "reject",
        "escalated": "escalate",
    }
    for name in ("status", "verdict", "review", "review_status"):
        if name not in row:
            continue
        value = row[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"review JSON {name} must be non-empty text")
        value = value.strip().lower()
        values.append(normalized.get(value, value))
    if len(set(values)) > 1:
        raise ValueError("review JSON verdict aliases conflict")
    return values[0] if values else ""


def _explanation_aliases(row: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for name in ("note", "explanation", "assessment", "reason", "review_note"):
        if name not in row:
            continue
        value = row[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"review JSON {name} must be non-empty text")
        values.append(value.strip())
    if len(set(values)) > 1:
        raise ValueError("review JSON explanation aliases conflict")
    return tuple(values)


def unsupported_issue(issue: str) -> bool:
    """Detect explicit support failures even under an ``accept`` label."""

    normalized = issue.lower()
    return any(
        phrase in normalized
        for phrase in (
            "not in excerpt",
            "not verbatim",
            "absent from excerpt",
            "not confirmed",
            "not supported",
            "unsupported",
            "absent from the bound",
            "does not contain",
            "doesn't contain",
            "cannot verify",
            "not visible",
            "partial acceptance",
            "partial support",
        )
    )


def _json_payload(raw: str) -> Any | None:
    candidates = [raw.strip()]
    fences = re.findall(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL | re.I)
    candidates.extend(fences)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    try:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    except json.JSONDecodeError:
        return None
