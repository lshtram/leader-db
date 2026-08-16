"""Deterministic corpus-reader batch result summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ._codex_worker_artifacts import read_codex_usage
from .corpus_reader_models import BoundEvidence
from .corpus_reading_plan import ReadingBatch


def build_batch_result(
    batch: ReadingBatch,
    evidence: list[BoundEvidence] | tuple[BoundEvidence, ...],
    batch_dir: Path,
    *,
    resumed: bool,
    elapsed_seconds: float,
    request_binding: Literal["verified_v1", "legacy_unbound"] = "verified_v1",
) -> dict[str, object]:
    usage = []
    for path in sorted(batch_dir.glob("*/events.jsonl")):
        item = read_codex_usage(path)
        usage.append(item.model_dump(mode="json") if item is not None else None)
    return {
        "batch_id": batch.batch_id,
        "source_ids": batch.source_ids,
        "estimated_source_tokens": batch.estimated_tokens,
        "evidence_count": len(evidence),
        "accepted_count": sum(item.verification_status != "rejected" for item in evidence),
        "resumed": resumed,
        "request_binding": request_binding,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "usage": usage,
    }


__all__ = ["build_batch_result"]
