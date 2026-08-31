"""Trusted and explicitly legacy recovery for completed corpus-reader batches."""

from __future__ import annotations

import json
from pathlib import Path

from .corpus_evidence_bind import bind_batch_evidence
from .corpus_reader_models import BatchFactOutput, BatchVerification, BoundEvidence
from .corpus_reader_normalize import normalize_reader_output, reconcile_reader
from .corpus_reading_plan import CorpusReadingPlan, ReadingBatch
from .corpus_verification import (
    apply_verification,
    build_verification_candidates,
    partition_verification,
)
from .corpus_verification_request import (
    bind_verification_request,
    load_bound_verification_result,
)


def recover_batch_evidence(
    *,
    acquisition_dir: Path,
    plan: CorpusReadingPlan,
    batch: ReadingBatch,
    batch_dir: Path,
    profile=None,
    profile_name: str | None = None,
    profile_config_sha256: str | None = None,
) -> tuple[BoundEvidence, ...] | None:
    evidence_path = batch_dir / "verified-evidence.json"
    reader_path = batch_dir / "reader/output.json"
    if not evidence_path.is_file() or not reader_path.is_file():
        return None
    try:
        try:
            reader = BatchFactOutput.model_validate_json(reader_path.read_text())
        except ValueError:
            reader = normalize_reader_output(reader_path, set(batch.source_ids))
        reader = reconcile_reader(reader, batch)
        reader_request_path = batch_dir / "reader-request.json"
        reader_version = (
            json.loads(reader_request_path.read_text(encoding="utf-8")).get(
                "prompt_config_version", 0
            )
            if reader_request_path.is_file()
            else 0
        )
        if reader_version >= 2 and any(item.citation_span_ids for item in reader.facts):
            raise ValueError("whole-unit discovery must not select paragraph citations")
        bound = bind_batch_evidence(
            acquisition_dir=acquisition_dir, plan=plan, batch=batch, reader_output=reader
        )
        expected = _recover_verification(
            acquisition_dir, plan, batch_dir, bound,
            profile, profile_name, profile_config_sha256,
        ) if bound else ()
        stored_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        stored = tuple(BoundEvidence.model_validate(item) for item in stored_payload)
    except (OSError, ValueError):
        return None
    return stored if stored == expected else None


def _recover_verification(
    acquisition_dir: Path,
    plan: CorpusReadingPlan,
    batch_dir: Path,
    bound: tuple[BoundEvidence, ...],
    profile,
    profile_name: str | None,
    profile_config_sha256: str | None,
) -> tuple[BoundEvidence, ...]:
    candidates = build_verification_candidates(
        acquisition_dir=acquisition_dir, plan=plan, evidence=bound
    )
    verification_dir = batch_dir / "verification"
    if not (verification_dir / "request-manifest.json").is_file():
        reader_request_path = batch_dir / "reader-request.json"
        reader_version = (
            json.loads(reader_request_path.read_text(encoding="utf-8")).get(
                "prompt_config_version", 0
            )
            if reader_request_path.is_file()
            else 0
        )
        if reader_version >= 2:
            raise ValueError("current verifier output lacks its request binding")
        verification = BatchVerification.model_validate_json(
            (verification_dir / "output.json").read_text(encoding="utf-8")
        )
        return apply_verification(bound, verification)
    if profile is None or profile_name is None or profile_config_sha256 is None:
        raise ValueError("verification request profile binding is unavailable")
    groups = partition_verification(bound, candidates)
    bind_verification_request(
        output_dir=verification_dir,
        groups=groups,
        candidates=candidates,
        profile_name=profile_name,
        profile_config_sha256=profile_config_sha256,
        model=profile.model,
        create=False,
    )
    verification = load_bound_verification_result(
        output_dir=verification_dir, groups=groups, require_complete=True
    )
    assert verification is not None
    return apply_verification(bound, verification, candidates)


__all__ = ["recover_batch_evidence"]
