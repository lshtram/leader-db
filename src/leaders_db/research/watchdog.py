"""Watchdog helpers for externally-run research shard artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

ShardStatus = Literal[
    "pending",
    "completed",
    "missing_output",
    "invalid_json",
    "record_count_mismatch",
    "missing_required_keys",
    "missing_citations",
    "timed_out_or_stuck",
    "progress_stale",
]

DEFAULT_REQUIRED_RECORD_KEYS = (
    "iso3",
    "country_name",
    "leader_id",
    "leader_name",
    "target_year_evidence",
    "near_period_context",
    "contrary_or_mitigating_evidence",
    "source_mix_note",
    "caveats",
    "citations",
)


def build_shard_status(
    *,
    input_path: Path,
    output_path: Path,
    expected_record_count: int,
    max_expected_minutes: int,
    max_progress_stale_minutes: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create the parent-owned status record for one shard."""

    started_at = _utc_now(now)
    return {
        "status": "pending",
        "started_at_utc": started_at.isoformat(),
        "deadline_at_utc": (started_at + timedelta(minutes=max_expected_minutes)).isoformat(),
        "last_progress_at_utc": started_at.isoformat(),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "expected_record_count": expected_record_count,
        "max_expected_minutes": max_expected_minutes,
        "max_progress_stale_minutes": max_progress_stale_minutes,
        "progress_events": [],
        "validation_errors": [],
    }


def record_shard_progress(
    status: dict[str, Any],
    *,
    message: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Update a shard status when a worker reports progress.

    The parent process owns the status file. Workers or human operators can call
    this helper through the CLI to make long-running shards observable without
    trusting a final text-only success report.
    """

    if not message.strip():
        raise ValueError("progress message must not be empty")
    updated_at = _utc_now(now)
    updated = dict(status)
    events = list(updated.get("progress_events") or [])
    events.append({"at_utc": updated_at.isoformat(), "message": message})
    updated["last_progress_at_utc"] = updated_at.isoformat()
    updated["progress_events"] = events[-20:]
    return updated


def write_shard_status(path: Path, status: dict[str, Any]) -> None:
    """Write shard status JSON with deterministic formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_shard_status(path: Path) -> dict[str, Any]:
    """Load a shard status JSON file."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("shard status JSON must be an object")
    return raw


def validate_shard_output(
    status: dict[str, Any],
    *,
    now: datetime | None = None,
    required_record_keys: tuple[str, ...] = DEFAULT_REQUIRED_RECORD_KEYS,
) -> dict[str, Any]:
    """Validate an externally-produced shard artifact and update its status."""

    checked_at = _utc_now(now)
    output_path = Path(str(status["output_path"]))
    errors: list[dict[str, Any]] = []
    status = dict(status)
    status["checked_at_utc"] = checked_at.isoformat()

    if not output_path.exists():
        status["status"] = _missing_status(status, checked_at)
        status["validation_errors"] = [
            {
                "code": status["status"],
                "message": f"output file not found: {output_path}",
            }
        ]
        return status

    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        status["status"] = "invalid_json"
        status["validation_errors"] = [
            {"code": "invalid_json", "message": f"{exc.msg} at line {exc.lineno}"}
        ]
        return status

    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        status["status"] = "invalid_json"
        status["validation_errors"] = [
            {"code": "missing_records", "message": "output JSON must contain records array"}
        ]
        return status

    expected = int(status["expected_record_count"])
    if len(records) != expected:
        errors.append(
            {
                "code": "record_count_mismatch",
                "message": f"expected {expected} records, found {len(records)}",
            }
        )

    missing_key_errors = _missing_key_errors(records, required_record_keys)
    errors.extend(missing_key_errors)
    missing_citation_errors = _missing_citation_errors(records)
    errors.extend(missing_citation_errors)

    if errors:
        status["status"] = _status_for_errors(errors)
    else:
        status["status"] = "completed"
    status["observed_record_count"] = len(records)
    status["validation_errors"] = errors
    return status


def validate_shard_status_file(
    status_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load, validate, persist, and return one shard status file."""

    status = validate_shard_output(load_shard_status(status_path), now=now)
    write_shard_status(status_path, status)
    return status


def _missing_status(status: dict[str, Any], checked_at: datetime) -> ShardStatus:
    stale_minutes = status.get("max_progress_stale_minutes")
    if stale_minutes is not None:
        last_progress_value = status.get("last_progress_at_utc") or status["started_at_utc"]
        last_progress = _parse_utc(str(last_progress_value))
        if checked_at - last_progress >= timedelta(minutes=int(stale_minutes)):
            return "progress_stale"
    deadline = datetime.fromisoformat(str(status["deadline_at_utc"]))
    deadline = _parse_utc(str(status["deadline_at_utc"]))
    return "timed_out_or_stuck" if checked_at >= deadline else "missing_output"


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _missing_key_errors(
    records: list[Any],
    required_record_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append(
                {"code": "missing_required_keys", "record_index": index, "missing": ["<object>"]}
            )
            continue
        missing = [key for key in required_record_keys if key not in record]
        if missing:
            errors.append(
                {"code": "missing_required_keys", "record_index": index, "missing": missing}
            )
    return errors


def _missing_citation_errors(records: list[Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        citations = record.get("citations") if isinstance(record, dict) else None
        if not isinstance(citations, list) or not citations:
            errors.append(
                {
                    "code": "missing_citations",
                    "record_index": index,
                    "message": "record must include at least one citation",
                }
            )
    return errors


def _status_for_errors(errors: list[dict[str, Any]]) -> ShardStatus:
    priority: tuple[ShardStatus, ...] = (
        "record_count_mismatch",
        "missing_required_keys",
        "missing_citations",
    )
    codes = {str(error["code"]) for error in errors}
    for status in priority:
        if status in codes:
            return status
    return "invalid_json"


def _utc_now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "DEFAULT_REQUIRED_RECORD_KEYS",
    "build_shard_status",
    "load_shard_status",
    "record_shard_progress",
    "validate_shard_output",
    "validate_shard_status_file",
    "write_shard_status",
]
