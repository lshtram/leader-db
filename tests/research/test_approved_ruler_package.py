from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from leaders_db.research.approved_chapter_projection import (
    _bounded_transport_text,
    build_approved_chapter_projection,
)
from leaders_db.research.approved_ruler_package import (
    build_approved_ruler_package,
    load_approved_ruler_package,
)
from leaders_db.research.batch_manifest import (
    ResearchBatchCase,
    ResearchBatchManifest,
    compute_resolved_content_sha256,
)
from leaders_db.research.chapter_analysis_models import (
    ChapterAnalysisCritique,
    ChapterAnalysisDraft,
    ChapterAnalysisQuality,
    ChapterQualityReviewBinding,
    CorrectedLensAnswer,
    LensQuality,
    ResolvedChapterAnalysis,
)
from leaders_db.research.corpus_judge_package import (
    CorpusJudgePackage,
    JudgeQuestionIndex,
)
from leaders_db.research.corpus_reader_models import BoundEvidence
from leaders_db.research.deep_corpus_release import load_deep_corpus_release
from leaders_db.research.production_run import build_production_run_manifest
from tests.research.test_chapter_projection import _dossier


def test_bounded_transport_text_marks_and_preserves_source_ends() -> None:
    excerpt = "A" * 4_000 + "B" * 4_000

    bounded = _bounded_transport_text(excerpt, limit=800)

    assert bounded.startswith("A" * 100)
    assert bounded.endswith("B" * 100)
    assert "TRANSPORT ELISION sha256=" in bounded
    assert len(bounded) <= 800


def test_production_release_requires_hash_bound_approved_corpus() -> None:
    release = load_deep_corpus_release(
        Path("configs/evidence-funnel/production-2023-v4.yaml")
    )

    assert release.target_year == 2023
    assert release.status == "production"
    assert release.pipeline_version_id == "leaders-db-production-pipeline-2023-v4"
    assert len(release.stage_versions) == 12
    assert release.judge_contract.require_approved_corpus_package is True
    assert release.judge_contract.allow_legacy_dossier_fallback is False


def test_approved_package_binds_full_corpus_and_builds_v2_projection(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    dossier = _dossier().model_copy(update={"period_start_year": 2019})
    dossier_path = tmp_path / "dossier.json"
    dossier_path.write_text(dossier.model_dump_json(), encoding="utf-8")
    evidence = _bound_evidence()
    corpus = CorpusJudgePackage(
        evidence=(evidence,),
        clusters=(),
        questions=tuple(
            JudgeQuestionIndex(
                methodology_id=f"{chapter}B.{question}",
                cluster_ids=(),
                evidence_ids=(evidence.evidence_id,),
                favorable_cluster_ids=(),
                adverse_cluster_ids=(),
                mixed_or_context_cluster_ids=(),
                source_publishers=(evidence.publisher,),
            )
            for chapter in range(1, 9)
            for question in range(1, 11)
        ),
    )
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json(), encoding="utf-8")
    reading_plan_path = tmp_path / "reading-plan.json"
    reading_plan_path.write_text(
        json.dumps(
            {
                "ruler_name": dossier.ruler_name,
                "period_start_year": dossier.period_start_year,
                "period_end_year": dossier.period_end_year,
                "config": {},
                "documents": [
                    {
                        "source_id": evidence.source_id,
                        "url": evidence.url,
                        "title": evidence.title,
                        "publisher": evidence.publisher,
                        "document_type": "report",
                        "chapter_ids": [f"{chapter}B" for chapter in range(1, 9)],
                        "status": "queued",
                        "extracted_path": "extracted/source.json",
                        "raw_sha256": evidence.raw_sha256,
                        "estimated_tokens": 100,
                    }
                ],
                "batches": [],
            }
        ),
        encoding="utf-8",
    )
    reading_manifest_path = tmp_path / "reading-run-manifest.json"
    reading_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "corpus_reading_run_v1",
                "profile": "test-reader",
                "model": "test-model",
                "batches": [],
                "evidence_count": 0,
                "failed_batch_ids": [],
            }
        ),
        encoding="utf-8",
    )
    selected = []
    for chapter in range(1, 9):
        chapter_id = f"{chapter}B"
        artifact_dir = tmp_path / chapter_id
        artifact_dir.mkdir()
        analysis = _analysis(chapter_id, evidence)
        quality = _quality(chapter_id)
        analysis_path = artifact_dir / "analysis.json"
        review_path = artifact_dir / "review.json"
        binding_path = artifact_dir / "binding.json"
        analysis_path.write_text(analysis.model_dump_json(), encoding="utf-8")
        review_path.write_text(quality.model_dump_json(), encoding="utf-8")
        binding = ChapterQualityReviewBinding(
            contract="independent-full-index-v1",
            chapter_id=chapter_id,
            analysis_sha256=_digest(analysis_path),
            judge_package_sha256=_digest(corpus_path),
            review_sha256=_digest(review_path),
        )
        binding_path.write_text(binding.model_dump_json(), encoding="utf-8")
        selected.append(
            {
                "chapter_id": chapter_id,
                "analysis_path": str(analysis_path.relative_to(tmp_path)),
                "analysis_sha256": _digest(analysis_path),
                "review_path": str(review_path.relative_to(tmp_path)),
                "review_sha256": _digest(review_path),
                "review_binding_path": str(binding_path.relative_to(tmp_path)),
                "review_binding_sha256": _digest(binding_path),
            }
        )
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "ruler_name": dossier.ruler_name,
                "target_year": dossier.period_end_year,
                "complete_ruler_safe_for_judge_use": True,
                "quality_review_contract": "independent-full-index-v1",
                "chapters": selected,
            }
        ),
        encoding="utf-8",
    )
    approval_path = tmp_path / "approved.json"
    release_dir = tmp_path / "configs" / "evidence-funnel"
    release_dir.mkdir(parents=True)
    release_path = release_dir / "production-2023-v4.yaml"
    release_payload = yaml.safe_load(
        Path("configs/evidence-funnel/production-2023-v4.yaml").read_text()
    )
    release_payload["target_year"] = dossier.period_end_year
    release_path.write_text(yaml.safe_dump(release_payload), encoding="utf-8")
    (release_dir / "methodology-2026-08-v2.freeze.yaml").write_text(
        yaml.safe_dump(
            {
                "release_id": "methodology-2026-08-v2",
                "file_hashes": {},
                "aggregate_sha256": hashlib.sha256(b"").hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    batch = ResearchBatchManifest(
        version=1,
        batch_id="test-approved-package",
        year=dossier.period_end_year,
        rationale="Synthetic production approval boundary test.",
        resolved_content_sha256="0" * 64,
        cases=(
            ResearchBatchCase(
                ruler_year_id=dossier.ruler_year_id,
                ruler_id=1,
                iso3=dossier.iso3,
                ruler_name=dossier.ruler_name,
            ),
        ),
    )
    batch = batch.model_copy(
        update={"resolved_content_sha256": compute_resolved_content_sha256(batch)}
    )
    batch_dir = tmp_path / "configs" / "research-batches"
    batch_dir.mkdir(parents=True)
    batch_path = batch_dir / "test.yaml"
    batch_path.write_text(
        yaml.safe_dump(batch.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    production_run_path = tmp_path / "research" / "runs" / "test" / "run.yaml"
    build_production_run_manifest(
        project_root=tmp_path,
        run_id="test-approved-package",
        batch_manifest_path=batch_path,
        release_config_path=release_path,
        output_path=production_run_path,
    )
    build_approved_ruler_package(
        project_root=tmp_path,
        dossier_path=dossier_path,
        corpus_package_path=corpus_path,
        reading_plan_path=reading_plan_path,
        reading_manifest_path=reading_manifest_path,
        selection_manifest_path=selection_path,
        production_run_manifest_path=production_run_path,
        output_path=approval_path,
    )

    approved = load_approved_ruler_package(approval_path, project_root=tmp_path)
    projection = build_approved_chapter_projection(
        dossier,
        chapter_id="4B",
        dossier_path=dossier_path,
        approval_manifest_path=approval_path,
        project_root=tmp_path,
        target_year=dossier.period_end_year,
    )

    assert approved.dossier_job_key == dossier.job_key
    assert approved.schema_version == "approved_ruler_evidence_package_v3"
    assert (
        approved.pipeline_provenance.pipeline_version_id
        == "leaders-db-production-pipeline-2023-v4"
    )
    assert projection.schema_version == "ruler_chapter_projection_v2"
    assert len(projection.approved_question_answers) == 10
    assert [item.evidence_id for item in projection.evidence] == ["E000001"]
    assert {item.relation for item in projection.mappings} == {"supports"}
    assert projection.approved_corpus_provenance is not None

    with pytest.raises(ValueError, match="target year differs"):
        build_approved_chapter_projection(
            dossier,
            chapter_id="4B",
            dossier_path=dossier_path,
            approval_manifest_path=approval_path,
            project_root=tmp_path,
            target_year=2019,
        )

    original_corpus = corpus_path.read_text(encoding="utf-8")
    original_approval = approval_path.read_text(encoding="utf-8")
    corpus_payload = json.loads(original_corpus)
    corpus_payload["questions"].pop()
    corpus_path.write_text(json.dumps(corpus_payload), encoding="utf-8")
    approval_payload = json.loads(original_approval)
    approval_payload["corpus_package_sha256"] = _digest(corpus_path)
    approval_path.write_text(json.dumps(approval_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="eighty methodology questions"):
        load_approved_ruler_package(approval_path, project_root=tmp_path)
    corpus_path.write_text(original_corpus, encoding="utf-8")
    approval_path.write_text(original_approval, encoding="utf-8")

    original_reading_manifest = reading_manifest_path.read_text(encoding="utf-8")
    incomplete = json.loads(original_reading_manifest)
    incomplete["failed_batch_ids"] = ["BATCH-0001"]
    reading_manifest_path.write_text(json.dumps(incomplete), encoding="utf-8")
    approval_payload = json.loads(original_approval)
    approval_payload["reading_manifest_sha256"] = _digest(reading_manifest_path)
    approval_path.write_text(json.dumps(approval_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="failed batches"):
        load_approved_ruler_package(approval_path, project_root=tmp_path)
    reading_manifest_path.write_text(original_reading_manifest, encoding="utf-8")
    approval_path.write_text(original_approval, encoding="utf-8")

    review_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_approved_ruler_package(approval_path, project_root=tmp_path)


def _bound_evidence() -> BoundEvidence:
    return BoundEvidence(
        evidence_id="BATCH-1-E001",
        source_id="SRC-1",
        url="https://example.test/report",
        title="Report",
        publisher="Publisher",
        raw_sha256="a" * 64,
        fact_summary="A verified material finding from the complete corpus.",
        question_ids=tuple(
            f"{chapter}B.{question}"
            for chapter in range(1, 9)
            for question in range(1, 11)
        ),
        polarity="mixed",
        period_fit="target year",
        ruler_attribution="Government responsibility is documented.",
        limitations=("Personal direction is not established.",),
        start_unit=1,
        end_unit=1,
        locator="page 1",
        exact_excerpt="This is the exact source passage supporting the finding.",
        excerpt_sha256="b" * 64,
        verification_status="accepted",
    )


def _analysis(chapter_id: str, evidence: BoundEvidence) -> ResolvedChapterAnalysis:
    answers = tuple(
        CorrectedLensAnswer(
            question_id=f"{chapter_id}.{index}",
            answer=(
                "The complete corpus contains a verified finding relevant to this lens, "
                "with attribution and limitations preserved for a skeptical judge."
            ),
            supporting_evidence_ids=(evidence.evidence_id,),
            contrary_or_qualifying_evidence_ids=(),
        )
        for index in range(1, 11)
    )
    return ResolvedChapterAnalysis(
        chapter_id=chapter_id,
        answers=answers,
        evidence=(evidence,),
        omitted_candidate_ids=(),
        draft=ChapterAnalysisDraft(chapter_id=chapter_id, answers=()),
        critique=ChapterAnalysisCritique(
            chapter_id=chapter_id,
            issues=(),
            overall_assessment="The synthetic complete-corpus analysis has no issue.",
        ),
    )


def _quality(chapter_id: str) -> ChapterAnalysisQuality:
    return ChapterAnalysisQuality(
        chapter_id=chapter_id,
        lens_quality=tuple(
            LensQuality(
                question_id=f"{chapter_id}.{index}",
                factual_support_1_to_5=5,
                completeness_1_to_5=5,
                balance_1_to_5=5,
                attribution_and_period_1_to_5=5,
                judge_usefulness_1_to_5=5,
            )
            for index in range(1, 11)
        ),
        overall_verdict="pass",
        strengths=("Complete exact-input review.",),
        systemic_problems=(),
        concrete_corrections_required=(),
        safe_for_judge_use=True,
        rationale="Every answer is supported and safe for the downstream judge.",
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
