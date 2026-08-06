"""Conservative evidence clustering and question-indexed judge package assembly."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .corpus_reader_models import BoundEvidence

_WORDS = re.compile(r"\w+", re.UNICODE)


class CorpusClaimCluster(BaseModel):
    """Conservative group of verified records expressing the same normalized fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str
    canonical_fact: str
    member_evidence_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    publishers: tuple[str, ...]
    question_ids: tuple[str, ...]
    polarities: tuple[str, ...]


class JudgeQuestionIndex(BaseModel):
    """All verified clusters relevant to one methodology lens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    methodology_id: str
    cluster_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    favorable_cluster_ids: tuple[str, ...]
    adverse_cluster_ids: tuple[str, ...]
    mixed_or_context_cluster_ids: tuple[str, ...]
    source_publishers: tuple[str, ...]


class CorpusJudgePackage(BaseModel):
    """Verified ledger, clusters, and many-to-many question mappings for judges."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["corpus_judge_package_v1"] = "corpus_judge_package_v1"
    evidence: tuple[BoundEvidence, ...]
    clusters: tuple[CorpusClaimCluster, ...]
    questions: tuple[JudgeQuestionIndex, ...]


def build_corpus_judge_package(
    reading_dir: Path,
    output_path: Path,
    *,
    mapping_review_path: Path | None = None,
    additional_reading_dirs: tuple[Path, ...] = (),
) -> Path:
    """Preserve verified evidence once and index it across every mapped question."""

    if mapping_review_path is None:
        evidence = _load_evidence((reading_dir, *additional_reading_dirs))
        fact_keys: dict[str, str] = {}
    else:
        review = json.loads(mapping_review_path.read_text(encoding="utf-8"))
        evidence = tuple(BoundEvidence.model_validate(item) for item in review["evidence"])
        fact_keys = {str(key): str(value) for key, value in review["underlying_fact_keys"].items()}
    accepted = tuple(item for item in evidence if item.verification_status != "rejected")
    clusters = _clusters(accepted, fact_keys=fact_keys)
    questions = tuple(
        _question_index(methodology_id, accepted, clusters)
        for methodology_id in (
            f"{chapter}B.{question}"
            for chapter in range(1, 9)
            for question in range(1, 11)
        )
    )
    package = CorpusJudgePackage(
        evidence=accepted,
        clusters=clusters,
        questions=questions,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def _load_evidence(reading_dirs: tuple[Path, ...]) -> tuple[BoundEvidence, ...]:
    evidence = []
    for reading_dir in reading_dirs:
        for path in sorted(reading_dir.glob("BATCH-*/verified-evidence.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            evidence.extend(BoundEvidence.model_validate(item) for item in payload)
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("verified corpus contains duplicate evidence IDs")
    return tuple(evidence)


def _clusters(
    evidence: tuple[BoundEvidence, ...], *, fact_keys: dict[str, str]
) -> tuple[CorpusClaimCluster, ...]:
    grouped: dict[str, list[BoundEvidence]] = defaultdict(list)
    for item in evidence:
        grouped[_fact_key(fact_keys.get(item.evidence_id, item.fact_summary))].append(item)
    return tuple(
        CorpusClaimCluster(
            cluster_id=f"CC-{sha256(key.encode()).hexdigest()[:16]}",
            canonical_fact=members[0].fact_summary,
            member_evidence_ids=tuple(item.evidence_id for item in members),
            source_ids=tuple(sorted({item.source_id for item in members})),
            publishers=tuple(sorted({item.publisher for item in members})),
            question_ids=tuple(
                sorted({question for item in members for question in item.question_ids})
            ),
            polarities=tuple(sorted({item.polarity for item in members})),
        )
        for key, members in sorted(grouped.items())
    )


def _question_index(
    methodology_id: str,
    evidence: tuple[BoundEvidence, ...],
    clusters: tuple[CorpusClaimCluster, ...],
) -> JudgeQuestionIndex:
    relevant = tuple(cluster for cluster in clusters if methodology_id in cluster.question_ids)
    evidence_by_id = {item.evidence_id: item for item in evidence}
    evidence_ids = tuple(
        dict.fromkeys(
            evidence_id
            for cluster in relevant
            for evidence_id in cluster.member_evidence_ids
        )
    )
    return JudgeQuestionIndex(
        methodology_id=methodology_id,
        cluster_ids=tuple(item.cluster_id for item in relevant),
        evidence_ids=evidence_ids,
        favorable_cluster_ids=tuple(
            item.cluster_id for item in relevant if "favorable" in item.polarities
        ),
        adverse_cluster_ids=tuple(
            item.cluster_id for item in relevant if "adverse" in item.polarities
        ),
        mixed_or_context_cluster_ids=tuple(
            item.cluster_id
            for item in relevant
            if set(item.polarities) & {"mixed", "context", "exculpatory"}
        ),
        source_publishers=tuple(
            sorted({evidence_by_id[item].publisher for item in evidence_ids})
        ),
    )


def _fact_key(value: str) -> str:
    return " ".join(_WORDS.findall(value.casefold()))


__all__ = ["CorpusJudgePackage", "build_corpus_judge_package"]
