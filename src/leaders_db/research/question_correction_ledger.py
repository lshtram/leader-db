"""Durable exactly-once ledger for the bounded question-correction phase."""

from __future__ import annotations

import fcntl
import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .control_flow import load_question_correction_policy

_FINAL_PREFLIGHT_CAPABILITY = object()
_CORRECTION_PREFLIGHT_CAPABILITY = object()


class CorrectionPhaseLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["question_correction_phase_ledger_v1"]
    policy_sha256: str
    source_run_result_sha256: str
    question_ids: tuple[str, ...]
    claimed_actions: tuple[str, ...] = ()
    correction_preflight_sha256: str | None = None
    correction_request_sha256s: dict[str, str] = Field(default_factory=dict)
    final_review_preflight_sha256: str | None = None
    final_review_request_sha256s: dict[str, str] = Field(default_factory=dict)


def initialize_correction_ledger(
    *, ledger_path: Path, policy_path: Path, run_result_path: Path, question_ids: tuple[str, ...]
) -> Path:
    """Create the immutable phase identity before any correction call."""

    load_question_correction_policy(policy_path)
    if len(question_ids) != len(set(question_ids)) or not question_ids:
        raise ValueError("correction ledger requires unique question IDs")
    payload = CorrectionPhaseLedger(
        schema_version="question_correction_phase_ledger_v1",
        policy_sha256=_sha256(policy_path),
        source_run_result_sha256=_sha256(run_result_path),
        question_ids=tuple(sorted(question_ids)),
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("x", encoding="utf-8") as handle:
        handle.write(payload.model_dump_json(indent=2) + "\n")
    return ledger_path


def claim_phase_action(
    *,
    ledger_path: Path,
    policy_path: Path,
    question_id: str,
    action: Literal["correct", "review"],
    request_sha256: str | None = None,
) -> None:
    """Atomically consume the sole permitted action for one question."""

    load_question_correction_policy(policy_path)
    with ledger_path.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        ledger = CorrectionPhaseLedger.model_validate_json(handle.read())
        if ledger.policy_sha256 != _sha256(policy_path) or question_id not in ledger.question_ids:
            raise ValueError("correction action differs from the frozen phase identity")
        key = f"{question_id}:{action}:1"
        if key in ledger.claimed_actions:
            raise ValueError(f"correction phase action already consumed: {key}")
        if (
            action == "correct"
            and ledger.correction_request_sha256s.get(question_id) != request_sha256
        ):
            raise ValueError("correction request is not authorized by the exact preflight")
        if action == "review" and f"{question_id}:correct:1" not in ledger.claimed_actions:
            raise ValueError("final review cannot precede the sole correction")
        if (
            action == "review"
            and ledger.final_review_request_sha256s.get(question_id) != request_sha256
        ):
            raise ValueError("final review request is not authorized by the exact preflight")
        updated = ledger.model_copy(update={"claimed_actions": (*ledger.claimed_actions, key)})
        handle.seek(0)
        handle.truncate()
        handle.write(updated.model_dump_json(indent=2) + "\n")
        handle.flush()


def _authorize_corrections(
    *, ledger_path: Path, preflight_path: Path, capability: object
) -> None:
    """Bind the eligible correction request inventory before any model call."""

    if capability is not _CORRECTION_PREFLIGHT_CAPABILITY:
        raise ValueError("correction authorization requires a trusted preflight capability")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "eligible_for_corrections":
        raise ValueError("correction preflight is not eligible")
    hashes = {
        item["question_id"]: item["complete_request_sha256"]
        for item in preflight.get("requests", ())
    }
    with ledger_path.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        ledger = CorrectionPhaseLedger.model_validate_json(handle.read())
        if set(hashes) != set(ledger.question_ids) or ledger.correction_preflight_sha256:
            raise ValueError("correction preflight does not match the frozen phase inventory")
        updated = ledger.model_copy(
            update={
                "correction_preflight_sha256": _sha256(preflight_path),
                "correction_request_sha256s": hashes,
            }
        )
        handle.seek(0)
        handle.truncate()
        handle.write(updated.model_dump_json(indent=2) + "\n")
        handle.flush()


def _authorize_final_reviews(
    *, ledger_path: Path, preflight_path: Path, capability: object
) -> None:
    """Bind one eligible exact final-review preflight to the phase ledger."""

    if capability is not _FINAL_PREFLIGHT_CAPABILITY:
        raise ValueError("final-review authorization requires a trusted preflight capability")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "eligible":
        raise ValueError("final-review preflight is not eligible")
    requests = preflight.get("requests", ())
    hashes = {item["question_id"]: item["complete_request_sha256"] for item in requests}
    with ledger_path.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        ledger = CorrectionPhaseLedger.model_validate_json(handle.read())
        expected_claims = {f"{item}:correct:1" for item in ledger.question_ids}
        if not expected_claims.issubset(ledger.claimed_actions) or set(hashes) != set(
            ledger.question_ids
        ):
            raise ValueError("final-review preflight does not cover completed corrections")
        if ledger.final_review_preflight_sha256 is not None:
            raise ValueError("final-review preflight is already bound")
        updated = ledger.model_copy(
            update={
                "final_review_preflight_sha256": _sha256(preflight_path),
                "final_review_request_sha256s": hashes,
            }
        )
        handle.seek(0)
        handle.truncate()
        handle.write(updated.model_dump_json(indent=2) + "\n")
        handle.flush()


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = ["claim_phase_action", "initialize_correction_ledger"]
