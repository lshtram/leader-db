"""Read explicit structured handoffs from immutable Codex event ledgers."""

from __future__ import annotations

import json
from pathlib import Path

from .routing import extract_json_object_with_trace


def latest_intent_event_payload(stage_root: Path) -> dict[str, object] | None:
    """Return the latest non-empty intent registry emitted as an agent message."""

    for path in reversed(sorted(stage_root.glob("attempt-*/events.jsonl"))):
        candidates: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") != "agent_message":
                continue
            text = item.get("text")
            if not isinstance(text, str):
                continue
            try:
                payload, _ = extract_json_object_with_trace(text)
            except ValueError:
                continue
            rows = (
                payload.get("intents")
                or payload.get("drafts")
                or payload.get("draft_intents")
                or payload.get("extracted_intents")
            )
            if isinstance(rows, list) and rows:
                candidates.append(payload)
        if candidates:
            return candidates[-1]
    return None


def intent_event_messages(stage_root: Path) -> tuple[str, ...]:
    """Return agent messages newest-first for deterministic Markdown adaptation."""

    messages: list[str] = []
    for path in reversed(sorted(stage_root.glob("attempt-*/events.jsonl"))):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    messages.append(text)
    return tuple(reversed(messages))


__all__ = ["intent_event_messages", "latest_intent_event_payload"]
