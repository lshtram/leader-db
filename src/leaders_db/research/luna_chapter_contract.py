"""Small output contracts for the Luna full-corpus experiment."""

from __future__ import annotations

import json
from pathlib import Path


def parse_shard_output(text: str) -> dict:
    """Parse compact shard JSON, tolerating only a trailing sentence period."""
    try:
        payload, offset = json.JSONDecoder().raw_decode(text.lstrip())
    except json.JSONDecodeError as error:
        raise RuntimeError("Luna returned truncated or malformed shard JSON") from error
    remainder = text.lstrip()[offset:].strip()
    if remainder not in {"", "."}:
        raise RuntimeError("Luna returned content after its shard JSON")
    if not isinstance(payload, dict):
        raise RuntimeError("Luna shard output is not a JSON object")
    return payload


def validate_shard_output(text: str) -> None:
    """Require the compact evidence/question/polarity tuple contract."""
    findings = parse_shard_output(text).get("findings")
    if not isinstance(findings, list):
        raise RuntimeError("Luna shard output has no findings list")
    for finding in findings:
        if (not isinstance(finding, list) or len(finding) != 3
                or not isinstance(finding[0], str) or not isinstance(finding[1], list)):
            raise RuntimeError("Luna shard output contains an invalid compact finding")


def synthesis_format(chapter_id: str) -> dict:
    """Return a bounded strict-JSON schema for a ten-question chapter brief."""
    answer = {
        "type": "object",
        "properties": {
            "question_id": {"type": "string", "enum": [
                f"{chapter_id}.{number}" for number in range(1, 11)
            ]},
            "answer": {"type": "string"},
            "supporting_ids": {"type": "array", "maxItems": 4,
                               "items": {"type": "string"}},
            "contrary_ids": {"type": "array", "maxItems": 4,
                             "items": {"type": "string"}},
            "uncertainty": {"type": "string"},
        },
        "required": ["question_id", "answer", "supporting_ids", "contrary_ids", "uncertainty"],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema", "name": f"chapter_{chapter_id.lower()}_brief", "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "const": chapter_id},
                "question_answers": {"type": "array", "minItems": 10,
                                     "maxItems": 10, "items": answer},
            },
            "required": ["chapter_id", "question_answers"],
            "additionalProperties": False,
        },
    }


def validate_synthesis(text: str, chapter_id: str) -> None:
    """Require exactly one answer for each chapter question."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError("Luna returned truncated or malformed synthesis JSON") from error
    answers = payload.get("question_answers")
    expected = {f"{chapter_id}.{number}" for number in range(1, 11)}
    actual = {item.get("question_id") for item in answers} if isinstance(answers, list) else set()
    if payload.get("chapter_id") != chapter_id or actual != expected:
        raise RuntimeError(f"Luna synthesis does not answer all ten {chapter_id} questions")


def normalize_synthesis_ids(text: str, valid_ids: set[str]) -> tuple[str, list[str]]:
    """Remove invented evidence IDs without guessing replacements."""
    payload = json.loads(text)
    removed = []
    for answer in payload.get("question_answers", []):
        for key in ("supporting_ids", "contrary_ids"):
            supplied = answer.get(key, [])
            removed.extend(evidence_id for evidence_id in supplied if evidence_id not in valid_ids)
            answer[key] = [evidence_id for evidence_id in supplied if evidence_id in valid_ids]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")), removed


def chapter_routed_ids(
    output_dir: Path, chapter_id: str, shard_count: int
) -> set[str]:
    """Collect the registry IDs actually supplied to one chapter synthesis."""
    routed = set()
    for number in range(1, shard_count + 1):
        path = output_dir / "shards" / f"S{number:02d}.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        for evidence_id, question_ids, _ in parse_shard_output(profile["output_text"])["findings"]:
            if any(question.startswith(chapter_id) for question in question_ids):
                routed.add(evidence_id)
    return routed
