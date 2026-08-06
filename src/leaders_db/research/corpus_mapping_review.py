"""No-search review of evidence-to-question mappings and semantic fact keys."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .corpus_reader_models import BoundEvidence
from .corpus_reader_runner import execute_json_model
from .model_profiles import load_research_model_profiles


class MappingVerdict(BaseModel):
    """Narrow mapping decision and package-global semantic clustering hint."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{12}$")
    question_ids: tuple[str, ...]
    underlying_fact_key: str = Field(min_length=3)

    @field_validator("question_ids")
    @classmethod
    def validate_questions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {
            f"{chapter}B.{question}"
            for chapter in range(1, 9)
            for question in range(1, 11)
        }
        if not set(value).issubset(allowed):
            raise ValueError("mapping review emitted an unknown question ID")
        return tuple(sorted(set(value)))


class MappingReviewOutput(BaseModel):
    """One verdict for every evidence record in a review batch."""

    model_config = ConfigDict(extra="forbid")

    verdicts: tuple[MappingVerdict, ...]


def run_mapping_review(
    *,
    project_root: Path,
    evidence_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
    batch_size: int = 40,
    parallel_batches: int = 5,
) -> Path:
    """Review mapping relevance without reopening or changing factual citations."""

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    raw_evidence = payload.get("evidence", payload)
    evidence = tuple(BoundEvidence.model_validate(item) for item in raw_evidence)
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    batches = [
        evidence[index : index + batch_size]
        for index in range(0, len(evidence), batch_size)
    ]
    verdicts: dict[str, MappingVerdict] = {}
    with ThreadPoolExecutor(max_workers=parallel_batches) as executor:
        futures = {
            executor.submit(
                _review_batch,
                project_root,
                profile,
                batch,
                output_dir / f"BATCH-{number:03d}",
            ): batch
            for number, batch in enumerate(batches, start=1)
        }
        for future in as_completed(futures):
            output = future.result()
            batch = futures[future]
            if not _identity_matches(batch, output):
                output = _repair_batch_identity(
                    project_root,
                    profile,
                    batch,
                    output,
                    output_dir / "identity-repairs",
                )
            if not _identity_matches(batch, output):
                raise ValueError("mapping reviewer shifted or altered evidence identity")
            verdicts.update({item.evidence_id: item for item in output.verdicts})
    revised = tuple(
        item.model_copy(update={"question_ids": verdicts[item.evidence_id].question_ids})
        for item in evidence
    )
    path = output_dir / "mapping-reviewed-evidence.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "mapping_reviewed_evidence_v1",
                "evidence": [item.model_dump(mode="json") for item in revised],
                "underlying_fact_keys": {
                    item.evidence_id: verdicts[item.evidence_id].underlying_fact_key
                    for item in evidence
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _review_batch(
    project_root: Path,
    profile,
    evidence: tuple[BoundEvidence, ...],
    output_dir: Path,
) -> MappingReviewOutput:
    output_path = output_dir / "output.json"
    if output_path.is_file():
        return MappingReviewOutput.model_validate_json(output_path.read_text(encoding="utf-8"))
    questions = json.loads(
        (
            project_root
            / "src/leaders_db/conversational_evidence/data/questions.json"
        ).read_text(encoding="utf-8")
    )
    records = [
        {
            "evidence_id": item.evidence_id,
            "evidence_digest": _evidence_digest(item),
            "fact_summary": item.fact_summary,
            "publisher": item.publisher,
            "period_fit": item.period_fit,
            "ruler_attribution": item.ruler_attribution,
            "current_question_ids": item.question_ids,
        }
        for item in evidence
    ]
    prompt = (
        "Review only evidence-to-question relevance. Do not change facts, citations, "
        "polarity, or attribution and do not score. Retain a question ID only when the "
        "fact materially helps answer that exact lens; thematic association is not "
        "enough. Empty question_ids is permitted for irrelevant/context-only material. "
        "Use cross-chapter mapping only when the same concrete fact directly informs "
        "both chapter purposes. Give each record a short normalized underlying_fact_key "
        "describing the event/policy/finding, using names and dates where available so "
        "repeated coverage receives comparable keys. Return one verdict per ID.\n\n"
        f"QUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}\n\n"
        f"EVIDENCE:\n{json.dumps(records, ensure_ascii=False)}"
    )
    return execute_json_model(
        project_root,
        profile,
        prompt,
        MappingReviewOutput,
        output_dir,
    )


def _evidence_digest(evidence: BoundEvidence) -> str:
    identity = "\x1f".join(
        (evidence.evidence_id, evidence.fact_summary, evidence.excerpt_sha256)
    )
    return sha256(identity.encode()).hexdigest()[:12]


def _identity_matches(
    evidence: tuple[BoundEvidence, ...], output: MappingReviewOutput
) -> bool:
    expected = {item.evidence_id: _evidence_digest(item) for item in evidence}
    received = {item.evidence_id: item.evidence_digest for item in output.verdicts}
    return received == expected


def _repair_batch_identity(
    project_root: Path,
    profile,
    evidence: tuple[BoundEvidence, ...],
    output: MappingReviewOutput,
    output_dir: Path,
) -> MappingReviewOutput:
    """Retain exact verdicts and retry only missing or identity-shifted records."""

    valid, repair = _partition_identity(evidence, output)
    verdicts = dict(valid)
    for item in repair:
        repaired = _review_batch(
            project_root,
            profile,
            (item,),
            output_dir / item.evidence_id,
        )
        if not _identity_matches((item,), repaired):
            raise ValueError(f"mapping identity repair failed for {item.evidence_id}")
        verdicts[item.evidence_id] = repaired.verdicts[0]
    return MappingReviewOutput(
        verdicts=tuple(verdicts[item.evidence_id] for item in evidence)
    )


def _partition_identity(
    evidence: tuple[BoundEvidence, ...], output: MappingReviewOutput
) -> tuple[dict[str, MappingVerdict], tuple[BoundEvidence, ...]]:
    """Separate unambiguous exact verdicts from records requiring isolated repair."""

    received: dict[str, list[MappingVerdict]] = {}
    for verdict in output.verdicts:
        received.setdefault(verdict.evidence_id, []).append(verdict)
    valid: dict[str, MappingVerdict] = {}
    repair = []
    for item in evidence:
        candidates = received.get(item.evidence_id, [])
        if len(candidates) == 1 and candidates[0].evidence_digest == _evidence_digest(item):
            valid[item.evidence_id] = candidates[0]
        else:
            repair.append(item)
    return valid, tuple(repair)


__all__ = ["run_mapping_review"]
