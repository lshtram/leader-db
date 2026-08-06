"""Isolated Codex/MiniMax worker orchestration around the evidence CLI."""

from __future__ import annotations

import json
import stat
import time
from pathlib import Path
from typing import Any

from .broker import Broker, registry_broker
from .model_runner import configured_profiles, invoke_model
from .models import AccessScope, WindowMarker, WorkerConfig
from .prompts import extractor_prompt, reviewer_prompt
from .registry import Registry
from .resume import registry_digest, validate_marker, window_binding
from .source import load_manifest, load_sources


def run_evidence_job(
    *,
    manifest_path: Path,
    config_path: Path,
    output_dir: Path,
    source_filter: tuple[str, ...] = (),
    maximum_windows: int | None = None,
) -> dict[str, Any]:
    """Read every selected source window, review facts, and materialize outputs."""

    config = _load_config(config_path)
    sources = load_sources(manifest_path)
    selected = source_filter or tuple(sources)
    unknown = sorted(set(selected) - set(sources))
    if unknown:
        raise ValueError(f"unknown selected sources: {unknown}")
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = output_dir / "registry.jsonl"
    registry = Registry(registry_path, sources)
    worker_dir = output_dir / "worker"
    worker_dir.mkdir(exist_ok=True)
    socket_path = worker_dir / "evidence.sock"
    _write_worker_cli(worker_dir)
    calls: list[dict[str, Any]] = []
    started = time.monotonic()
    completed_windows = 0
    with registry_broker(
        socket_path=socket_path,
        manifest_path=manifest_path,
        registry_path=registry_path,
    ) as broker:
        for source_id in selected:
            source = sources[source_id]
            for start, end in _windows(
                len(source.sentences),
                config.window_sentences,
                config.overlap_sentences,
            ):
                if maximum_windows is not None and completed_windows >= maximum_windows:
                    break
                window_id = f"{source_id}:{start:06d}-{end:06d}"
                marker = (
                    output_dir
                    / "windows"
                    / f"{source_id}-{start:06d}-{end:06d}.json"
                )
                binding = window_binding(
                    manifest_path,
                    config_path,
                    source.extracted_sha256,
                    source.original_sha256,
                )
                if marker.exists():
                    saved = WindowMarker.model_validate_json(
                        marker.read_text(encoding="utf-8")
                    )
                    if saved.binding != binding:
                        raise ValueError(f"window resume mismatch: {marker}")
                    validate_marker(
                        saved,
                        registry,
                        source_id=source_id,
                        start_sentence=start,
                        end_sentence=end,
                        original_sha256=source.original_sha256,
                        extracted_sha256=source.extracted_sha256,
                    )
                    completed_windows += 1
                    continue
                extraction_calls = _run_until_inspected(
                    role="extractor",
                    manifest_path=manifest_path,
                    registry_path=registry_path,
                    output_dir=output_dir,
                    source_id=source_id,
                    start=start,
                    end=end,
                    config=config,
                    worker_dir=worker_dir,
                    socket_path=socket_path,
                    window_id=window_id,
                    broker=broker,
                )
                calls.extend(extraction_calls)
                states = registry.states()
                owned = registry.facts_for_window(window_id)
                ready = [
                    fact_id
                    for fact_id in sorted(owned)
                    if states[fact_id].extractor_confirmed
                    and not states[fact_id].reviewer_confirmed
                ]
                if ready:
                    review_calls = _run_until_reviewed(
                        manifest_path=manifest_path,
                        registry_path=registry_path,
                        output_dir=output_dir,
                        fact_ids=tuple(ready),
                        config=config,
                        worker_dir=worker_dir,
                        socket_path=socket_path,
                        window_id=window_id,
                        broker=broker,
                    )
                    calls.extend(review_calls)
                marker.parent.mkdir(parents=True, exist_ok=True)
                fact_ids = tuple(sorted(owned))
                saved = WindowMarker(
                    schema_version="simple_evidence_window_v2",
                    binding=binding,
                    registry_digest=registry_digest(registry, fact_ids),
                    source_id=source_id,
                    original_sha256=source.original_sha256,
                    extracted_sha256=source.extracted_sha256,
                    start_sentence=start,
                    end_sentence=end,
                    fact_ids=fact_ids,
                )
                marker.write_text(
                    saved.model_dump_json(indent=2)
                    + "\n",
                    encoding="utf-8",
                )
                completed_windows += 1
            if maximum_windows is not None and completed_windows >= maximum_windows:
                break
    counts = registry.materialize(output_dir)
    report = {
        "schema_version": "simple_evidence_run_report_v1",
        "ruler": load_manifest(manifest_path).ruler,
        "target_period": load_manifest(manifest_path).target_period,
        "sources_selected": list(selected),
        "windows_completed": completed_windows,
        "model_calls": calls,
        "tokens": sum(int(item.get("total_tokens", 0)) for item in calls),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        **counts,
    }
    (output_dir / "run-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _run_until_inspected(
    *,
    role: str,
    manifest_path: Path,
    registry_path: Path,
    output_dir: Path,
    source_id: str,
    start: int,
    end: int,
    config: WorkerConfig,
    worker_dir: Path,
    socket_path: Path,
    window_id: str,
    broker: Broker,
) -> list[dict[str, Any]]:
    calls = []
    profiles = configured_profiles(config)
    registry = Registry(registry_path, load_sources(manifest_path))
    initial_event_count = len(registry.events())
    if _is_inspected(registry, window_id, source_id, start, end):
        return calls
    for attempt, profile in enumerate(profiles, start=1):
        current_registry = Registry(registry_path, load_sources(manifest_path))
        owned = current_registry.facts_for_window(window_id)
        pending = tuple(
            sorted(
                fact_id
                for fact_id in owned
                if not current_registry.states()[fact_id].extractor_confirmed
            )
        )
        prompt = extractor_prompt(
            source_id, start, end, pending=pending, reminder=attempt > 1
        )
        scope = AccessScope(
            role="extractor",
            window_id=window_id,
            source_id=source_id,
            start_sentence=start,
            end_sentence=end,
            fact_ids=frozenset(owned),
        )
        capability = broker.grant(scope)
        try:
            call = invoke_model(
                profile=profile,
                prompt=prompt,
                role=role,
                manifest_path=manifest_path,
                registry_path=registry_path,
                output_dir=output_dir,
                worker_dir=worker_dir,
                socket_path=socket_path,
                capability=capability,
                label=f"extract-{source_id}-{start:06d}-{attempt:02d}",
                timeout=config.timeout_seconds,
            )
        finally:
            broker.revoke(capability)
        calls.append(call)
        current_registry = Registry(registry_path, load_sources(manifest_path))
        events = current_registry.events()
        shown = _was_shown(
            events[initial_event_count:], window_id, source_id, start, end
        )
        states = current_registry.states()
        owned = current_registry.facts_for_window(window_id)
        if shown and all(states[fact_id].extractor_confirmed for fact_id in owned):
            return calls
    raise RuntimeError(f"models did not inspect {source_id} S{start:06d}-S{end:06d}")


def _run_until_reviewed(
    *,
    manifest_path: Path,
    registry_path: Path,
    output_dir: Path,
    fact_ids: tuple[str, ...],
    config: WorkerConfig,
    worker_dir: Path,
    socket_path: Path,
    window_id: str,
    broker: Broker,
) -> list[dict[str, Any]]:
    calls = []
    for attempt, profile in enumerate(configured_profiles(config), start=1):
        states = Registry(registry_path, load_sources(manifest_path)).states()
        first = states[fact_ids[0]]
        scope = AccessScope(
            role="reviewer",
            window_id=window_id,
            source_id=first.source_id,
            start_sentence=min(states[item].start_sentence for item in fact_ids),
            end_sentence=max(states[item].end_sentence for item in fact_ids),
            fact_ids=frozenset(fact_ids),
        )
        capability = broker.grant(scope)
        try:
            call = invoke_model(
                profile=profile,
                prompt=reviewer_prompt(fact_ids, reminder=attempt > 1),
                role="reviewer",
                manifest_path=manifest_path,
                registry_path=registry_path,
                output_dir=output_dir,
                worker_dir=worker_dir,
                socket_path=socket_path,
                capability=capability,
                label=f"review-{fact_ids[0]}-{attempt:02d}",
                timeout=config.timeout_seconds,
            )
        finally:
            broker.revoke(capability)
        calls.append(call)
        states = Registry(registry_path, load_sources(manifest_path)).states()
        if all(states[item].reviewer_confirmed for item in fact_ids):
            return calls
    raise RuntimeError(f"models did not review facts: {list(fact_ids)}")


def _is_inspected(
    registry: Registry, window_id: str, source_id: str, start: int, end: int
) -> bool:
    owned = registry.facts_for_window(window_id)
    states = registry.states()
    return _was_shown(registry.events(), window_id, source_id, start, end) and all(
        states[fact_id].extractor_confirmed for fact_id in owned
    )


def _was_shown(
    events: list[dict[str, Any]],
    window_id: str,
    source_id: str,
    start: int,
    end: int,
) -> bool:
    return any(
        event.get("event") == "source_shown"
        and event.get("source_id") == source_id
        and int(event.get("start_sentence", 0)) <= start
        and int(event.get("end_sentence", 0)) >= end
        and event.get("window_id") == window_id
        for event in events
    )


def _windows(total: int, maximum: int, overlap: int) -> tuple[tuple[int, int], ...]:
    if maximum < 1 or overlap < 0 or overlap >= maximum:
        raise ValueError("window settings require 0 <= overlap < maximum")
    result = []
    start = 1
    while start <= total:
        end = min(total, start + maximum - 1)
        result.append((start, end))
        if end == total:
            break
        start = end - overlap + 1
    return tuple(result)


def _write_worker_cli(output_dir: Path) -> None:
    path = output_dir / "evidence"
    content = (
        "#!/bin/sh\n"
        'exec "$SIMPLE_EVIDENCE_PYTHON" -m simple_evidence.cli "$@"\n'
    )
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError(f"worker CLI changed: {path}")
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _load_config(path: Path) -> WorkerConfig:
    return WorkerConfig.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = ["run_evidence_job"]
