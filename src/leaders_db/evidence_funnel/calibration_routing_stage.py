"""Batched long-document routing with exact merged accounting."""

from __future__ import annotations

from pathlib import Path

from .artifacts import ArtifactStore
from .calibration_stage_run import run_routing_stage
from .config import EvidenceFunnelConfig
from .low_cost import RoutingDecisionBatch
from .models import DocumentSectionMap, SourceDescriptor


def run_batched_routing(
    *,
    project_root: Path,
    config: EvidenceFunnelConfig,
    source: SourceDescriptor,
    units: tuple[dict[str, object], ...],
    questions: str,
    document_map: DocumentSectionMap,
    profiles_path: Path,
    source_root: Path,
) -> tuple[RoutingDecisionBatch, str, int]:
    """Route bounded unit groups and merge them in frozen source order."""

    decisions = []
    profiles = []
    total_tokens = 0
    maximum = config.routing.routing_batch_max_units
    for number, start in enumerate(range(0, len(units), maximum), start=1):
        unit_batch = units[start : start + maximum]
        batch_root = source_root / "02-routing-batches" / f"batch-{number:03d}"
        result, profile, tokens = run_routing_stage(
            project_root=project_root,
            config=config,
            source=source,
            units=unit_batch,
            questions=questions,
            document_map=document_map,
            profiles_path=profiles_path,
            source_root=batch_root,
        )
        decisions.extend(result.decisions)
        profiles.append(profile)
        total_tokens += tokens
    merged = RoutingDecisionBatch(decisions=tuple(decisions))
    expected = tuple(str(item["chunk_id"]) for item in units)
    actual = tuple(item.chunk_id for item in merged.decisions)
    if actual != expected:
        raise ValueError("batched routing did not preserve the complete frozen chunk order")
    expected_set = set(expected)
    unknown_adjacent = sorted(
        {
            adjacent
            for decision in merged.decisions
            for adjacent in decision.adjacent_chunk_ids
            if adjacent not in expected_set
        }
    )
    if unknown_adjacent:
        raise ValueError(f"routing contains unknown adjacent chunks: {unknown_adjacent}")
    ArtifactStore(source_root).write_immutable(
        "02-routing/normalized-output.json",
        merged,
    )
    profile_label = "batched-routing:" + ",".join(profiles)
    return merged, profile_label, total_tokens


__all__ = ["run_batched_routing"]
