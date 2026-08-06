"""Prompt builders for the bounded three-source calibration runner."""

from __future__ import annotations

import json

from .citation_models import LocatorIndex
from .models import EvidenceCandidate, SourceDescriptor

SHELL_SAFE_JSON_INSTRUCTION = (
    "Surround the JSON argument with single quotes and encode every apostrophe "
    r"inside a JSON string as \u0027 and every dollar sign as \u0024; the command "
    "must contain no literal apostrophe except the two shell delimiters and no "
    "literal dollar sign."
)


def question_text(
    question_payload: object,
    methodology_ids: tuple[str, ...] | None = None,
) -> str:
    """Serialize only the configured frozen questions without paraphrasing."""

    payload = question_payload
    if methodology_ids is not None:
        payload = _select_questions(question_payload, set(methodology_ids))
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _select_questions(payload: object, allowed: set[str]) -> object:
    if not isinstance(payload, dict) or not isinstance(payload.get("chapters"), list):
        raise ValueError("question contract must contain a chapters list")
    chapters = []
    found: set[str] = set()
    for chapter in payload["chapters"]:
        if not isinstance(chapter, dict) or not isinstance(chapter.get("questions"), list):
            continue
        questions = [
            question
            for question in chapter["questions"]
            if isinstance(question, dict) and question.get("id") in allowed
        ]
        if questions:
            selected = dict(chapter)
            selected["questions"] = questions
            chapters.append(selected)
            found.update(str(question["id"]) for question in questions)
    if found != allowed:
        raise ValueError(f"question contract lacks configured IDs: {sorted(allowed - found)}")
    selected_payload = dict(payload)
    selected_payload["chapters"] = chapters
    selected_payload["chapter_ids"] = [chapter["id"] for chapter in chapters]
    return selected_payload


def mapping_prompt(
    *,
    instruction: str,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    questions: str,
) -> str:
    """Build one source mapping request."""

    return (
        "You are the navigation mapper in a non-scoring evidence calibration.\n"
        f"{instruction}\n"
        "Return the supplied source metadata byte-for-byte in the source field. "
        "Use only actual locator boundaries. Do not treat the map as evidence.\n\n"
        f"QUESTIONS\n{questions}\n\n"
        f"SOURCE\n{source.model_dump_json(indent=2)}\n\n"
        f"UNITS\n{json.dumps(units, ensure_ascii=False, indent=2)}"
    )


def routing_prompt(
    *,
    instruction: str,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    questions: str,
    document_map: str,
) -> str:
    """Build one high-recall routing request."""

    return (
        "You are the high-recall router in a non-scoring evidence calibration.\n"
        f"{instruction}\n"
        "Return exactly one decision for every supplied chunk_id. Included chunks "
        "must cite every applicable 5B lens. Exclusions must be auditable.\n\n"
        f"QUESTIONS\n{questions}\n\nSOURCE\n{source.model_dump_json(indent=2)}"
        f"\n\nNAVIGATION MAP\n{document_map}\n\n"
        f"CHUNKS\n{json.dumps(units, ensure_ascii=False, indent=2)}"
    )


def extraction_prompt(
    *,
    instruction: str,
    source: SourceDescriptor,
    locator_indexes: tuple[LocatorIndex, ...],
    questions: str,
) -> str:
    """Build one intent-extraction request over code-indexed source text."""

    indexes = [item.model_dump(mode="json") for item in locator_indexes]
    return (
        "You are the evidence-intent extractor in a non-scoring calibration.\n"
        f"{instruction}\n"
        "Draft IDs must be sequential D0001, D0002, ... within this response. "
        "Each locator disposition must name an inspected locator exactly once. "
        "The code will copy every quote from the inclusive segment range. Select "
        "the narrowest contiguous range that fully supports the claim. Do not put "
        "quotation text in any semantic field.\n\n"
        f"QUESTIONS\n{questions}\n\nSOURCE\n{source.model_dump_json(indent=2)}"
        f"\n\nLOCATOR INDEXES\n{json.dumps(indexes, ensure_ascii=False, indent=2)}"
    )


def citation_cli_instructions(tool_surface: str) -> str:
    """Describe the four-action tool workflow without overstating guarantees."""

    return (
        "Use only the evidence tool surface shown below. The dedicated runner "
        "will ignore prose and final-message content; its accepted output is the "
        "validated citation ledger.\n\n"
        f"TOOL SURFACE\n{tool_surface}\n\n"
        "The only workflow actions are:\n"
        "Invoke exactly one of these four command forms after the CLI prefix:\n"
        "1. inspect SOURCE_ID LOCATOR\n"
        "2. record --json 'ONE_COMPACT_JSON_OBJECT'\n"
        "3. revise PROPOSAL_ID START_SEGMENT_ID END_SEGMENT_ID\n"
        "4. finish PROPOSAL_ID\n"
        "Copy the CLI prefix exactly; never retype, shorten, or alter any path. "
        "Run exactly one action in each command invocation. Never use a shell loop, "
        "pipeline, command list, variable, or wrapper to invoke multiple actions. "
        "To finish several proposals, issue a separate complete CLI command for "
        "each proposal.\n"
        "The inspect action returns code-indexed source segments. Record returns "
        "the exact excerpt copied by code. Revise changes only the inclusive segment "
        "range, with at most three total binding attempts. Finish persists the latest "
        "hash-bound candidate.\n\n"
        "Do not author quotation text. After record or revise, compare the returned "
        "excerpt with your intended claim. Finish only when you judge that the "
        "excerpt supports the claim. A separate reviewer will verify semantic "
        "support; the CLI guarantees source identity, exact span copying, hashes, "
        "attempt history, and stable persistence."
    )


def verification_prompt(
    *,
    instruction: str,
    candidates: tuple[EvidenceCandidate, ...],
    questions: str,
) -> str:
    """Build one fresh semantic review request."""

    payload = [item.model_dump(mode="json") for item in candidates]
    return (
        "You are a fresh no-search factual reviewer. The excerpts below were copied "
        "by code from frozen sources; never rewrite them or infer missing context.\n"
        f"{instruction}\n"
        "Return exactly one review per evidence_id. Accept only when the excerpt "
        "supports the complete claim, attribution, dates, quantities, legal status, "
        "and causal strength. Reject overstatement; escalate genuinely ambiguous "
        "legal or technical disputes. The reserved value "
        "'[not separately decomposed]' is missing extractor metadata, not a factual "
        "assertion; assess the atomic claim and any supplied components.\n\n"
        f"QUESTIONS\n{questions}\n\n"
        f"BOUND CANDIDATES\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


__all__ = [
    "citation_cli_instructions",
    "extraction_prompt",
    "mapping_prompt",
    "question_text",
    "routing_prompt",
    "verification_prompt",
]
