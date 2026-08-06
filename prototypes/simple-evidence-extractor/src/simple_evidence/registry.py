"""Append-only fact registry and deterministic materialized views."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    FACT_TYPES,
    PERIOD_FITS,
    FactState,
    PreparedSource,
    parse_sentence_id,
    validate_chapters,
)
from .outputs import fact_id, materialized_state, write_jsonl
from .source import resolve_span
from .validation import require_numeric_support

MAXIMUM_ATTEMPTS = 3


class Registry:
    """Code-owned registry reconstructed from immutable JSONL events."""

    def __init__(self, path: Path, sources: dict[str, PreparedSource]) -> None:
        self.path = path
        self.sources = sources

    def show_source(
        self, source_id: str, start: int, end: int, window_id: str = ""
    ) -> dict[str, Any]:
        source = self._source(source_id)
        from .source import source_summary

        result = source_summary(source, start, end)
        with self._exclusive():
            self._append_unlocked(
                {
                    "event": "source_shown",
                    "source_id": source_id,
                    "start_sentence": start,
                    "end_sentence": end,
                    "window_id": window_id,
                }
            )
        return result

    def show_fact(self, fact_id: str) -> dict[str, Any]:
        return self._fact(fact_id).to_dict()

    def add(
        self,
        *,
        source_id: str,
        start: int,
        end: int | None,
        summary: str,
        chapters: list[str] | None = None,
        fact_type: str = "unknown",
        period_fit: str = "unknown",
        window_id: str = "",
    ) -> FactState:
        source = self._source(source_id)
        resolved_end = start if end is None else end
        locator, excerpt, start_char, end_char = resolve_span(source, start, resolved_end)
        clean_summary = _summary(summary)
        require_numeric_support(clean_summary, excerpt)
        _metadata(fact_type, period_fit)
        clean_chapters = validate_chapters(chapters or [])
        resolved_fact_id = fact_id(
            source.extracted_sha256,
            locator,
            start_char,
            end_char,
            clean_summary,
        )
        with self._exclusive():
            existing = self._states_unlocked().get(resolved_fact_id)
            if existing:
                self._append_unlocked(
                    {
                        "event": "fact_referenced",
                        "fact_id": resolved_fact_id,
                        "window_id": window_id,
                    }
                )
                return existing
            state = FactState(
                fact_id=resolved_fact_id,
                source_id=source_id,
                start_sentence=start,
                end_sentence=resolved_end,
                summary=clean_summary,
                excerpt=excerpt,
                locator=locator,
                start_char=start_char,
                end_char=end_char,
                source_sha256=source.extracted_sha256,
                fact_type=fact_type,
                period_fit=period_fit,
                chapters=clean_chapters,
            )
            self._append_unlocked(
                {
                    "event": "fact_added",
                    "state": state.to_dict(),
                    "window_id": window_id,
                }
            )
            return state

    def correct(
        self,
        fact_id: str,
        *,
        role: str = "extractor",
        start: int | None = None,
        end: int | None = None,
        summary: str | None = None,
        chapters: list[str] | None = None,
        fact_type: str | None = None,
        period_fit: str | None = None,
    ) -> FactState:
        with self._exclusive():
            current = self._fact_unlocked(fact_id)
            if current.disposition in {"accepted", "rejected"}:
                raise ValueError("finalized facts cannot be corrected")
            if role not in {"extractor", "reviewer"}:
                raise ValueError("correction role must be extractor or reviewer")
            role_attempts = (
                current.attempts
                if role == "extractor"
                else current.reviewer_attempts
            )
            if role_attempts >= MAXIMUM_ATTEMPTS:
                raise ValueError(
                    f"{fact_id} reached the {MAXIMUM_ATTEMPTS}-attempt {role} limit"
                )
            source = self._source(current.source_id)
            resolved_start = current.start_sentence if start is None else start
            resolved_end = current.end_sentence if end is None else end
            locator, excerpt, start_char, end_char = resolve_span(
                source, resolved_start, resolved_end
            )
            resolved_type = current.fact_type if fact_type is None else fact_type
            resolved_period = current.period_fit if period_fit is None else period_fit
            _metadata(resolved_type, resolved_period)
            updated = FactState(
                fact_id=fact_id,
                source_id=current.source_id,
                start_sentence=resolved_start,
                end_sentence=resolved_end,
                summary=current.summary if summary is None else _summary(summary),
                excerpt=excerpt,
                locator=locator,
                start_char=start_char,
                end_char=end_char,
                source_sha256=source.extracted_sha256,
                attempts=(
                    current.attempts + 1
                    if role == "extractor"
                    else current.attempts
                ),
                reviewer_attempts=(
                    current.reviewer_attempts + 1
                    if role == "reviewer"
                    else current.reviewer_attempts
                ),
                fact_type=resolved_type,
                period_fit=resolved_period,
                chapters=(
                    current.chapters
                    if chapters is None
                    else validate_chapters(chapters)
                ),
                extractor_confirmed=current.extractor_confirmed,
                reviewer_confirmed=current.reviewer_confirmed,
                disposition=current.disposition,
            )
            require_numeric_support(updated.summary, updated.excerpt)
            self._append_unlocked({"event": "fact_corrected", "state": updated.to_dict()})
            return updated

    def confirm(self, fact_id: str, role: str) -> FactState:
        with self._exclusive():
            current = self._fact_unlocked(fact_id)
            if role not in {"extractor", "reviewer"}:
                raise ValueError("EVIDENCE_ROLE must be extractor or reviewer")
            if current.disposition in {"accepted", "rejected"}:
                return current
            if role == "extractor":
                if current.extractor_confirmed:
                    return current
                current.extractor_confirmed = True
                current.disposition = "ready_for_review"
            else:
                if not current.extractor_confirmed:
                    raise ValueError(
                        "reviewer cannot confirm an unconfirmed extractor fact"
                    )
                if current.reviewer_confirmed:
                    return current
                current.reviewer_confirmed = True
                current.disposition = (
                    "rejected" if current.fact_type == "rejected" else "accepted"
                )
            self._append_unlocked(
                {
                    "event": "fact_confirmed",
                    "role": role,
                    "fact_id": fact_id,
                    "disposition": current.disposition,
                }
            )
            return current

    def states(self) -> dict[str, FactState]:
        with self._shared():
            return self._states_unlocked()

    def facts_for_window(self, window_id: str) -> set[str]:
        with self._shared():
            return {
                str(event["fact_id"])
                if event["event"] == "fact_referenced"
                else str(event["state"]["fact_id"])
                for event in self._events_unlocked()
                if event.get("event") in {"fact_added", "fact_referenced"}
                and event.get("window_id") == window_id
            }

    def _states_unlocked(self) -> dict[str, FactState]:
        states: dict[str, FactState] = {}
        for event in self._events_unlocked():
            kind = event.get("event")
            if kind in {"fact_added", "fact_corrected"}:
                state = _state(event["state"])
                states[state.fact_id] = state
            elif kind == "fact_confirmed":
                state = states.get(str(event.get("fact_id")))
                if state is None:
                    raise ValueError("registry confirmation precedes fact creation")
                if event.get("role") == "extractor":
                    state.extractor_confirmed = True
                else:
                    state.reviewer_confirmed = True
                state.disposition = str(event.get("disposition"))
        for state in states.values():
            self._validate_state(state)
        return states

    def events(self) -> tuple[dict[str, Any], ...]:
        with self._shared():
            return self._events_unlocked()

    def _events_unlocked(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        events = []
        for number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid registry JSON at line {number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"registry line {number} is not an object")
            events.append(value)
        return tuple(events)

    def materialize(self, output_dir: Path) -> dict[str, int]:
        output_dir.mkdir(parents=True, exist_ok=True)
        states = tuple(self.states().values())
        groups = {
            "evidence.jsonl": [item for item in states if item.disposition == "accepted"],
            "rejected.jsonl": [item for item in states if item.disposition == "rejected"],
            "pending.jsonl": [
                item
                for item in states
                if item.disposition not in {"accepted", "rejected"}
            ],
        }
        for filename, items in groups.items():
            write_jsonl(
                output_dir / filename,
                [materialized_state(item, self.sources[item.source_id]) for item in items],
            )
        return {
            "accepted": len(groups["evidence.jsonl"]),
            "rejected": len(groups["rejected.jsonl"]),
            "pending": len(groups["pending.jsonl"]),
        }

    def _source(self, source_id: str) -> PreparedSource:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise ValueError(f"unknown manifest source: {source_id}") from exc

    def _fact(self, fact_id: str) -> FactState:
        try:
            return self.states()[fact_id]
        except KeyError as exc:
            raise ValueError(f"unknown fact ID: {fact_id}") from exc

    def _fact_unlocked(self, fact_id: str) -> FactState:
        try:
            return self._states_unlocked()[fact_id]
        except KeyError as exc:
            raise ValueError(f"unknown fact ID: {fact_id}") from exc

    def _validate_state(self, state: FactState) -> None:
        source = self._source(state.source_id)
        locator, excerpt, start_char, end_char = resolve_span(
            source, state.start_sentence, state.end_sentence
        )
        if (
            state.source_sha256 != source.extracted_sha256
            or state.locator != locator
            or state.excerpt != excerpt
            or state.start_char != start_char
            or state.end_char != end_char
        ):
            raise ValueError(f"registry source binding changed for {state.fact_id}")

    def _append_unlocked(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "schema_version": "simple_evidence_registry_event_v1",
            "recorded_at": datetime.now(UTC).isoformat(),
            **event,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @contextmanager
    def _exclusive(self):
        with self._lock(fcntl.LOCK_EX):
            yield

    @contextmanager
    def _shared(self):
        with self._lock(fcntl.LOCK_SH):
            yield

    @contextmanager
    def _lock(self, mode: int):
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), mode)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _state(value: dict[str, Any]) -> FactState:
    payload = dict(value)
    payload["start_sentence"] = parse_sentence_id(payload["start_sentence"])
    payload["end_sentence"] = parse_sentence_id(payload["end_sentence"])
    return FactState.model_validate(payload)


def _summary(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("summary must be non-empty")
    if len(cleaned) > 1200:
        raise ValueError("summary must not exceed 1200 characters")
    return cleaned


def _metadata(fact_type: str, period_fit: str) -> None:
    if fact_type not in FACT_TYPES:
        raise ValueError(f"invalid fact type: {fact_type}")
    if period_fit not in PERIOD_FITS:
        raise ValueError(f"invalid period fit: {period_fit}")


__all__ = ["MAXIMUM_ATTEMPTS", "Registry"]
