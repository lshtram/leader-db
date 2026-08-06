from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from leaders_db.evidence_funnel.calibration_routing_stage import run_batched_routing
from leaders_db.evidence_funnel.calibration_stage_run import _validate_routing_batch
from leaders_db.evidence_funnel.config import load_evidence_funnel_config
from leaders_db.evidence_funnel.low_cost import RoutingDecisionBatch
from leaders_db.evidence_funnel.models import ChunkRoutingDecision, SourceDescriptor


def _decision(
    source: SourceDescriptor,
    chunk_id: str,
    adjacent_chunk_ids: tuple[str, ...] = (),
) -> ChunkRoutingDecision:
    return ChunkRoutingDecision(
        schema_version="chunk_routing_decision_v1",
        source_id=source.source_id,
        source_sha256=source.source_sha256,
        chunk_id=chunk_id,
        included=True,
        relevant_question_ids=("5B.3",),
        relevance_strength="material",
        adjacent_chunk_ids=adjacent_chunk_ids,
        explanation="Concrete fiscal evidence.",
    )


def _config(project_root: Path):
    config = load_evidence_funnel_config(
        project_root / "configs/evidence-funnel/amlo-2022-5b-v2.json"
    )
    return config.model_copy(
        update={
            "routing": config.routing.model_copy(
                update={"routing_batch_max_units": 2}
            )
        }
    )


def test_context_validator_rejects_unknown_adjacent_chunk(
    descriptor: SourceDescriptor,
) -> None:
    project_root = Path(__file__).parents[2]
    units = ({"chunk_id": "U0001", "locator": "page 1", "text": "fact"},)
    routing = RoutingDecisionBatch(
        decisions=(_decision(descriptor, "U0001", ("U9999",)),)
    )

    with pytest.raises(ValueError, match="unknown adjacent"):
        _validate_routing_batch(routing, descriptor, units, _config(project_root))


def test_batched_routing_merges_order_tokens_profiles_and_artifact(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(__file__).parents[2]
    units = tuple(
        {"chunk_id": f"U{number:04d}", "locator": f"page {number}", "text": "fact"}
        for number in range(1, 4)
    )
    roots: list[Path] = []

    def fake_stage(**kwargs):
        batch = kwargs["units"]
        roots.append(kwargs["source_root"])
        decisions = tuple(
            _decision(descriptor, str(item["chunk_id"])) for item in batch
        )
        number = len(roots)
        return RoutingDecisionBatch(decisions=decisions), f"profile-{number}", number

    monkeypatch.setattr(
        "leaders_db.evidence_funnel.calibration_routing_stage.run_routing_stage",
        fake_stage,
    )
    output = tmp_path / "source"
    result, profile, tokens = run_batched_routing(
        project_root=project_root,
        config=_config(project_root),
        source=descriptor,
        units=units,
        questions="questions",
        document_map=SimpleNamespace(),
        profiles_path=project_root / "configs/research-models.yaml",
        source_root=output,
    )

    assert tuple(item.chunk_id for item in result.decisions) == (
        "U0001",
        "U0002",
        "U0003",
    )
    assert roots == [
        output / "02-routing-batches/batch-001",
        output / "02-routing-batches/batch-002",
    ]
    assert profile == "batched-routing:profile-1,profile-2"
    assert tokens == 3
    persisted = json.loads(
        (output / "02-routing/normalized-output.json").read_text(encoding="utf-8")
    )
    assert [item["chunk_id"] for item in persisted["decisions"]] == [
        "U0001",
        "U0002",
        "U0003",
    ]


def test_batched_routing_rejects_incomplete_batch(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(__file__).parents[2]
    units = (
        {"chunk_id": "U0001", "locator": "page 1", "text": "fact"},
        {"chunk_id": "U0002", "locator": "page 2", "text": "fact"},
        {"chunk_id": "U0003", "locator": "page 3", "text": "fact"},
    )

    def fake_stage(**kwargs):
        chunk_id = "U0001" if kwargs["units"][0]["chunk_id"] == "U0001" else "U9999"
        result = RoutingDecisionBatch(decisions=(_decision(descriptor, chunk_id),))
        return result, "profile", 1

    monkeypatch.setattr(
        "leaders_db.evidence_funnel.calibration_routing_stage.run_routing_stage",
        fake_stage,
    )

    with pytest.raises(ValueError, match="complete frozen chunk order"):
        run_batched_routing(
            project_root=project_root,
            config=_config(project_root),
            source=descriptor,
            units=units,
            questions="questions",
            document_map=SimpleNamespace(),
            profiles_path=project_root / "configs/research-models.yaml",
            source_root=tmp_path / "source",
        )


def test_batched_routing_rejects_unknown_adjacent_chunk(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = Path(__file__).parents[2]
    units = ({"chunk_id": "U0001", "locator": "page 1", "text": "fact"},)

    def fake_stage(**_kwargs):
        result = RoutingDecisionBatch(
            decisions=(_decision(descriptor, "U0001", ("U9999",)),)
        )
        return result, "profile", 1

    monkeypatch.setattr(
        "leaders_db.evidence_funnel.calibration_routing_stage.run_routing_stage",
        fake_stage,
    )

    with pytest.raises(ValueError, match="unknown adjacent chunks"):
        run_batched_routing(
            project_root=project_root,
            config=_config(project_root),
            source=descriptor,
            units=units,
            questions="questions",
            document_map=SimpleNamespace(),
            profiles_path=project_root / "configs/research-models.yaml",
            source_root=tmp_path / "source",
        )
