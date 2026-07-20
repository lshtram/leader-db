"""Parsing, validation, and profiling helpers for deep research artifacts."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .data import load
from .deep_models import DeepSession, DeepWorkflowConfig

_TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "utm_campaign", "utm_content",
    "utm_medium", "utm_source", "utm_term",
}


def canonical_url(raw: str) -> str:
    """Canonicalize a discovered HTTP(S) URL for parent-side counting."""

    cleaned = raw.rstrip(".,;:'\"`>")
    parts = urlsplit(cleaned)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"not an HTTP(S) URL: {raw}")
    host = parts.hostname.lower() if parts.hostname else ""
    port = f":{parts.port}" if parts.port else ""
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    query = urlencode(sorted(
        (key, value)
        for key, value in parse_qsl(parts.query)
        if key not in _TRACKING_QUERY_KEYS
    ))
    return urlunsplit((parts.scheme.lower(), host + port, path, query, ""))


def urls(text: str) -> set[str]:
    values: set[str] = set()
    for raw in re.findall(r"https?://[^\s)\]|<>]+", text):
        try:
            values.add(canonical_url(raw))
        except ValueError:
            continue
    return values


def candidate_ids(text: str, chapter_id: str) -> set[str]:
    pattern = rf"(?<![A-Z0-9])(?:{re.escape(chapter_id)}-)?C\d{{3}}(?![A-Z0-9])"
    return set(re.findall(pattern, text, flags=re.IGNORECASE))


def id_number(value: str) -> int:
    match = re.search(r"(\d+)$", value)
    return int(match.group(1)) if match else 0


def last_candidate_id(values: tuple[str, ...], chapter_id: str) -> str:
    return max(values, key=id_number) if values else f"{chapter_id}-C000"


def candidate_inventory(text: str, values: tuple[str, ...]) -> str:
    selected = [line for line in text.splitlines() if any(item in line for item in values)]
    return "\n".join(selected)


def chunks(values: tuple[str, ...], size: int) -> Iterable[tuple[str, ...]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def accepted_ledger(path: Path, chapter_id: str) -> dict[str, str]:
    records: dict[str, str] = {}
    table = re.compile(rf"^\|\s*`?({re.escape(chapter_id)}-S\d+)`?\s*\|", re.I)
    bullet = re.compile(
        rf"^-\s*`?({re.escape(chapter_id)}-S\d+)`?\s+\[[^]]+\]\((https?://[^)]+)\)",
        re.I,
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        table_match = table.match(line)
        bullet_match = bullet.match(line)
        if table_match:
            found = urls(line)
            if len(found) == 1:
                records[table_match.group(1).upper()] = found.pop()
        elif bullet_match:
            records[bullet_match.group(1).upper()] = canonical_url(bullet_match.group(2))
    return records


def final_ledger_valid(path: Path, chapter_id: str, workflow: DeepWorkflowConfig) -> bool:
    records = accepted_ledger(path, chapter_id)
    return (
        workflow.accepted_minimum <= len(records) <= workflow.accepted_maximum
        and len(set(records.values())) == len(records)
    )


def validate_final_ledger(path: Path, chapter_id: str, workflow: DeepWorkflowConfig) -> None:
    if final_ledger_valid(path, chapter_id, workflow):
        return
    records = accepted_ledger(path, chapter_id)
    raise ValueError(
        f"{chapter_id} final ledger violates accepted-source bounds or URL uniqueness: "
        f"{len(records)} parsed records, {len(set(records.values()))} unique URLs"
    )


def load_local_priors(
    path: Path, *, ruler: str, iso3: str, year: int
) -> list[dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError("local priors must be a non-empty JSON array")
    rows = [item for item in value if isinstance(item, dict)]
    if len(rows) != len(value):
        raise ValueError("every local-prior row must be an object")
    for row in rows:
        leader, country = row.get("leader"), row.get("country")
        if not isinstance(leader, dict) or not isinstance(country, dict):
            raise ValueError("local-prior identity is missing")
        if leader.get("name") != ruler or country.get("iso3") != iso3.upper():
            raise ValueError("local priors belong to a different ruler")
        period = row.get("period")
        if not isinstance(period, dict) or period.get("start_year") != year:
            raise ValueError("local priors belong to a different year")
        if row.get("client_matrix_policy") != "excluded_as_evidence":
            raise ValueError("local priors must exclude client-matrix evidence")
    return rows


def prior_summary(rows: list[dict[str, object]]) -> str:
    status: dict[str, int] = {}
    facts = 0
    for row in rows:
        key = str(row.get("status", "unknown"))
        status[key] = status.get(key, 0) + 1
        local_facts = row.get("local_facts")
        facts += len(local_facts) if isinstance(local_facts, list) else 0
    return json.dumps(
        {"methodology_rows": len(rows), "local_fact_rows": facts, "statuses": status},
        indent=2,
        sort_keys=True,
    )


def chapter_priors(rows: list[dict[str, object]], chapter_id: str) -> str:
    selected = [row for row in rows if str(row.get("methodology_id", "")).startswith(chapter_id)]
    return json.dumps(selected, ensure_ascii=False, indent=2)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(value.rstrip() + "\n", encoding="utf-8")
    os.replace(pending, path)


def write_profile(output: Path, session: DeepSession) -> Path:
    profiles = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((output / ".researcher").glob("turn-*.profile.json"))
    ]
    usage = _cumulative_usage(output / ".researcher")
    pricing = load("researchers.json")[session.researcher].get("pricing_per_million", {})
    chapters = {
        chapter_id: {
            "verified_candidate_urls": len(state.verified_candidate_urls),
            "candidate_ids": len(state.candidate_ids),
            "inspection_waves": state.inspection_waves_completed,
            "finalized": state.finalized,
        }
        for chapter_id, state in session.chapters.items()
    }
    path = output / "profile.json"
    atomic_text(path, json.dumps({
        "schema_version": "deep-chapter-profile-v1",
        "identity": {"ruler": session.ruler, "country": session.country,
                     "iso3": session.iso3, "year": session.year},
        "researcher": session.researcher,
        "completed_phases": len(session.completed_phases),
        "duration_seconds": round(sum(float(x.get("duration_seconds", 0)) for x in profiles), 3),
        "tool_calls": sum(sum(x.get("tool_calls", {}).values()) for x in profiles),
        "usage": usage,
        "estimated_cost_usd": _estimated_cost(usage, pricing),
        "chapters": chapters,
    }, indent=2, sort_keys=True))
    return path


def _cumulative_usage(work_dir: Path) -> dict[str, int]:
    latest: dict[str, dict[str, int]] = {}
    for path in sorted(work_dir.glob("turn-*.jsonl")):
        thread_id, usage = "", {}
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "thread.started":
                thread_id = str(event.get("thread_id", ""))
            if (
                isinstance(event, dict)
                and event.get("type") == "turn.completed"
                and isinstance(event.get("usage"), dict)
            ):
                usage = {str(k): int(v) for k, v in event["usage"].items() if isinstance(v, int)}
        if thread_id and usage:
            latest[thread_id] = usage
    totals: dict[str, int] = {}
    for usage in latest.values():
        for key, value in usage.items():
            totals[key] = totals.get(key, 0) + value
    return totals


def _estimated_cost(usage: dict[str, int], pricing: dict[str, object]) -> float | None:
    if not pricing:
        return None
    cached = usage.get("cached_input_tokens", 0)
    uncached = max(0, usage.get("input_tokens", 0) - cached)
    cost = (uncached * float(pricing["input"]) + cached * float(pricing["cached_input"])
            + usage.get("output_tokens", 0) * float(pricing["output"])) / 1_000_000
    return round(cost, 6)


__all__ = ["accepted_ledger", "atomic_text", "candidate_ids", "candidate_inventory",
           "canonical_url", "chapter_priors", "chunks", "final_ledger_valid", "id_number",
           "last_candidate_id", "load_local_priors", "prior_summary", "urls",
           "validate_final_ledger", "write_profile"]
