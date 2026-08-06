"""Hash-bound window completion markers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import WindowMarker
from .registry import Registry


def window_binding(
    manifest: Path,
    config: Path,
    extracted_hash: str,
    original_hash: str | None,
) -> str:
    digest = hashlib.sha256()
    digest.update(manifest.read_bytes())
    digest.update(config.read_bytes())
    digest.update(extracted_hash.encode())
    digest.update((original_hash or "no-original").encode())
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def registry_digest(registry: Registry, fact_ids: tuple[str, ...]) -> str:
    states = registry.states()
    payload = [states[fact_id].model_dump(mode="json") for fact_id in fact_ids]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_marker(
    marker: WindowMarker,
    registry: Registry,
    *,
    source_id: str,
    start_sentence: int,
    end_sentence: int,
    original_sha256: str | None,
    extracted_sha256: str,
) -> None:
    identity = (
        marker.source_id,
        marker.start_sentence,
        marker.end_sentence,
        marker.original_sha256,
        marker.extracted_sha256,
    )
    expected = (
        source_id,
        start_sentence,
        end_sentence,
        original_sha256,
        extracted_sha256,
    )
    if identity != expected:
        raise ValueError("window marker identity changed")
    states = registry.states()
    missing = sorted(set(marker.fact_ids) - set(states))
    if missing:
        raise ValueError(f"window registry facts missing: {missing}")
    if any(
        states[fact_id].disposition not in {"accepted", "rejected"}
        for fact_id in marker.fact_ids
    ):
        raise ValueError("window registry contains unfinished facts")
    if registry_digest(registry, marker.fact_ids) != marker.registry_digest:
        raise ValueError("window registry state changed")


__all__ = ["registry_digest", "validate_marker", "window_binding"]
