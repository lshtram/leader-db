"""Corpus-wide conservative adjudication of repeated underlying facts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .corpus_mapping_review import _evidence_digest
from .corpus_reader_models import BoundEvidence
from .corpus_reader_runner import execute_json_model
from .model_profiles import load_research_model_profiles


class ClusterMember(BaseModel):
    """Identity-bound membership in a repeated-fact group."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{12}$")


class DuplicateGroup(BaseModel):
    """Records that report the same underlying event, policy, or finding."""

    model_config = ConfigDict(extra="forbid")

    canonical_fact_key: str = Field(min_length=3)
    members: tuple[ClusterMember, ...] = Field(min_length=2)


class ClusterReviewOutput(BaseModel):
    """Only high-confidence duplicate groups; omitted records remain singletons."""

    model_config = ConfigDict(extra="forbid")

    duplicate_groups: tuple[DuplicateGroup, ...]


def run_cluster_review(
    *,
    project_root: Path,
    mapping_review_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
) -> Path:
    """Adjudicate duplicates once across the complete verified evidence ledger."""

    payload = json.loads(mapping_review_path.read_text(encoding="utf-8"))
    evidence = tuple(BoundEvidence.model_validate(item) for item in payload["evidence"])
    records = [
        {
            "evidence_id": item.evidence_id,
            "evidence_digest": _evidence_digest(item),
            "fact_summary": item.fact_summary,
            "publisher": item.publisher,
            "period_fit": item.period_fit,
        }
        for item in evidence
    ]
    prompt = (
        "Identify only high-confidence repeated coverage of the same concrete event, "
        "policy action, quantitative release, adjudication, or institutional finding. "
        "Group records even when their interpretations or polarities differ, but never "
        "group facts merely because they concern the same theme, institution, ruler, "
        "or broad period. A record may appear in at most one group. Copy each ID and "
        "digest exactly. Omit all uncertain groups and all singletons. Do not score or "
        "rewrite evidence. Return only the schema output.\n\nEVIDENCE:\n"
        + json.dumps(records, ensure_ascii=False)
    )
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    result = execute_json_model(
        project_root, profile, prompt, ClusterReviewOutput, output_dir
    )
    retained, rejected_group_count = _retain_valid_groups(evidence, result)
    keys = dict(payload["underlying_fact_keys"])
    for group in retained.duplicate_groups:
        for member in group.members:
            keys[member.evidence_id] = group.canonical_fact_key
    output_path = output_dir / "cluster-reviewed-evidence.json"
    output_path.write_text(
        json.dumps(
            {
                **payload,
                "schema_version": "cluster_reviewed_evidence_v1",
                "underlying_fact_keys": keys,
                "duplicate_groups": [
                    group.model_dump(mode="json") for group in retained.duplicate_groups
                ],
                "rejected_duplicate_group_count": rejected_group_count,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _retain_valid_groups(
    evidence: tuple[BoundEvidence, ...], result: ClusterReviewOutput
) -> tuple[ClusterReviewOutput, int]:
    """Keep only identity-exact, non-overlapping groups; uncertain records stay singletons."""

    expected = {item.evidence_id: _evidence_digest(item) for item in evidence}
    seen: set[str] = set()
    retained = []
    for group in result.duplicate_groups:
        member_ids = [item.evidence_id for item in group.members]
        valid = (
            len(member_ids) == len(set(member_ids))
            and not seen.intersection(member_ids)
            and all(
                expected.get(item.evidence_id) == item.evidence_digest
                for item in group.members
            )
        )
        if not valid:
            continue
        retained.append(group)
        seen.update(member_ids)
    return (
        ClusterReviewOutput(duplicate_groups=tuple(retained)),
        len(result.duplicate_groups) - len(retained),
    )


def _validate_groups(
    evidence: tuple[BoundEvidence, ...], result: ClusterReviewOutput
) -> None:
    expected = {item.evidence_id: _evidence_digest(item) for item in evidence}
    seen: set[str] = set()
    for group in result.duplicate_groups:
        for member in group.members:
            if member.evidence_id in seen:
                raise ValueError("evidence appears in more than one duplicate group")
            if expected.get(member.evidence_id) != member.evidence_digest:
                raise ValueError("cluster reviewer altered evidence identity")
            seen.add(member.evidence_id)


__all__ = ["run_cluster_review"]
