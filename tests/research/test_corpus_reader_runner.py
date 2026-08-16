"""Tests for corpus-reader transport partitioning and completion gates."""

import json
from pathlib import Path

import pytest

from leaders_db.research.corpus_reader_models import (
    BatchVerification,
    BoundEvidence,
    EvidenceVerdict,
)
from leaders_db.research.corpus_reader_runner import (
    _partition_verification,
    run_corpus_reading,
)
from leaders_db.research.corpus_verification import (
    VERIFICATION_BATCH_CHARACTERS,
    verification_prompt,
)
from leaders_db.research.corpus_verification_request import (
    load_bound_verification_result,
)


def _evidence(evidence_id: str, excerpt: str) -> BoundEvidence:
    return BoundEvidence(
        evidence_id=evidence_id,
        source_id="SRC-1",
        url="https://example.test/source",
        title="Source",
        publisher="Publisher",
        raw_sha256="a" * 64,
        fact_summary="One material factual account.",
        question_ids=("1B.1",),
        polarity="context",
        period_fit="2023",
        ruler_attribution="direct",
        limitations=(),
        start_unit=1,
        end_unit=1,
        locator="unit 1",
        exact_excerpt=excerpt,
        excerpt_sha256="b" * 64,
    )


def test_verification_partition_preserves_every_record_once() -> None:
    evidence = tuple(
        _evidence(f"E-{number}", "x" * 80_000) for number in range(1, 6)
    )

    groups = _partition_verification(evidence)

    assert len(groups) == 3
    assert tuple(item for group in groups for item in group) == evidence
    assert all(
        len(verification_prompt(group)) <= VERIFICATION_BATCH_CHARACTERS
        for group in groups
    )


def test_verification_partition_rejects_one_unsplittable_record() -> None:
    with pytest.raises(ValueError, match="exceeds verification transport budget"):
        _partition_verification((_evidence("E-1", "x" * 230_000),))


def test_multipart_verification_reconciles_parts_and_root(tmp_path: Path) -> None:
    groups = ((_evidence("E-1", "first"),), (_evidence("E-2", "second"),))
    output_dir = tmp_path / "verification"
    verdicts = []
    for number, evidence_id in enumerate(("E-1", "E-2"), start=1):
        verdict = EvidenceVerdict(
            evidence_id=evidence_id,
            status="accepted",
            notes=(),
            citation_span_ids=(),
        )
        verdicts.append(verdict)
        part = output_dir / f"part-{number:03d}"
        part.mkdir(parents=True)
        (part / "output.json").write_text(
            BatchVerification(verdicts=(verdict,)).model_dump_json()
        )
    combined = BatchVerification(verdicts=tuple(verdicts))
    assert load_bound_verification_result(
        output_dir=output_dir, groups=groups, require_complete=False
    ) is None
    (output_dir / "output.json").write_text(combined.model_dump_json())

    assert load_bound_verification_result(
        output_dir=output_dir, groups=groups, require_complete=True
    ) == combined

    swapped = BatchVerification(verdicts=(verdicts[1],))
    (output_dir / "part-001/output.json").write_text(swapped.model_dump_json())
    with pytest.raises(ValueError, match="partition evidence IDs"):
        load_bound_verification_result(
            output_dir=output_dir, groups=groups, require_complete=True
        )

    (output_dir / "part-001/output.json").write_text(
        BatchVerification(verdicts=(verdicts[0],)).model_dump_json()
    )
    (output_dir / "output.json").write_text(
        BatchVerification(verdicts=tuple(reversed(verdicts))).model_dump_json()
    )
    with pytest.raises(ValueError, match="differs from its partitions"):
        load_bound_verification_result(
            output_dir=output_dir, groups=groups, require_complete=True
        )


def test_corpus_run_persists_failure_and_refuses_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "ruler_name": "Test Ruler",
                "period_start_year": 2023,
                "period_end_year": 2023,
                "config": {},
                "documents": [],
                "batches": [
                    {
                        "batch_id": "BATCH-0001",
                        "source_ids": [],
                        "unit_ranges": {},
                        "chapter_ids": ["1B"],
                        "estimated_tokens": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_batch(**_kwargs):
        raise RuntimeError("synthetic reader failure")

    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner._run_batch", fail_batch
    )
    output = tmp_path / "reading"
    with pytest.raises(RuntimeError, match="corpus reading is incomplete"):
        run_corpus_reading(
            project_root=Path.cwd(),
            acquisition_dir=tmp_path / "acquisition",
            plan_path=plan,
            output_dir=output,
            profile_name="openai-luna-candidate",
            profiles_path=Path("configs/research-models.yaml"),
            parallel_batches=1,
        )
    manifest = json.loads(
        (output / "reading-run-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["failed_batch_ids"] == ["BATCH-0001"]
