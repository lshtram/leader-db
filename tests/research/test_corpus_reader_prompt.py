from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.corpus_reader_models import BatchFactOutput, BatchVerification
from leaders_db.research.corpus_reader_prompt import (
    build_corpus_reader_prompt,
    write_reader_request_manifest,
)
from leaders_db.research.corpus_reader_runner import run_corpus_reading
from leaders_db.research.corpus_reading_plan import CorpusReadingPlan


def _plan() -> CorpusReadingPlan:
    return CorpusReadingPlan.model_validate({
        "ruler_name": "Fixture Ruler",
        "period_start_year": 2023,
        "period_end_year": 2023,
        "config": {},
        "documents": [{
            "source_id": "SRC-1",
            "url": "https://example.test/report",
            "title": "Report",
            "publisher": "Publisher",
            "document_type": "report",
            "chapter_ids": ["5B"],
            "status": "queued",
            "extracted_path": "extracted/SRC-1.json",
            "raw_sha256": "abc",
            "estimated_tokens": 10,
        }],
        "batches": [{
            "batch_id": "BATCH-0001",
            "source_ids": ["SRC-1"],
            "unit_ranges": {"SRC-1": [1, 1]},
            "chapter_ids": ["5B"],
            "estimated_tokens": 10,
        }],
    })


def _write_extraction(acquisition: Path, payload: dict | None = None) -> None:
    (acquisition / "extracted").mkdir(parents=True)
    if payload is None:
        payload = {
            "source_id": "SRC-1",
            "raw_sha256": "abc",
            "units": [{
                "unit": 1,
                "locator": "page 1",
                "text": "First exact paragraph.\n\nSecond exact paragraph.",
            }],
        }
    (acquisition / "extracted/SRC-1.json").write_text(json.dumps(payload))


def test_prompt_renders_stable_paragraph_labels_and_request_binding(tmp_path: Path) -> None:
    root = Path.cwd()
    acquisition = tmp_path / "acquisition"
    _write_extraction(acquisition)
    plan = _plan()
    rendered = build_corpus_reader_prompt(
        acquisition_dir=acquisition,
        plan=plan,
        batch=plan.batches[0],
        prompts_path=root / "configs/corpus-reader-prompts.yaml",
        questions_path=root / "src/leaders_db/conversational_evidence/data/questions.json",
    )

    assert "[SOURCE=SRC-1 UNIT=1 LOCATOR=page 1]" in rendered.prompt
    assert "Leave citation_span_ids empty" in rendered.prompt
    assert rendered.character_count == len(rendered.prompt)
    manifest = write_reader_request_manifest(
        tmp_path / "reader-request.json",
        rendered,
        "test-profile",
        "a" * 64,
        "test-model",
        BatchFactOutput,
        tmp_path / "reader",
    )
    assert json.loads(manifest.read_text())["prompt_config_version"] == 2
    write_reader_request_manifest(
        manifest,
        rendered,
        "test-profile",
        "a" * 64,
        "test-model",
        BatchFactOutput,
        tmp_path / "reader",
    )

    altered = rendered.model_copy(update={"prompt_sha256": "0" * 64})
    with pytest.raises(ValueError, match="request binding differs"):
        write_reader_request_manifest(
            manifest,
            altered,
            "test-profile",
            "a" * 64,
            "test-model",
            BatchFactOutput,
            tmp_path / "reader",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "source_id": "SRC-OTHER",
            "raw_sha256": "abc",
            "units": [{"unit": 1, "locator": "page 1", "text": "Text."}],
        },
        {
            "source_id": "SRC-1",
            "raw_sha256": "abc",
            "units": [{"unit": 1, "locator": "page 1", "text": 123}],
        },
        {
            "source_id": "SRC-1",
            "raw_sha256": "abc",
            "units": [{"unit": 1, "locator": "page 1", "text": " \n\n "}],
        },
        {
            "source_id": "SRC-1",
            "raw_sha256": "abc",
            "units": [{"unit": 2, "locator": "page 2", "text": "Text."}],
        },
    ],
)
def test_prompt_rejects_ambiguous_or_empty_extraction(
    tmp_path: Path, payload: dict
) -> None:
    root = Path.cwd()
    acquisition = tmp_path / "acquisition"
    _write_extraction(acquisition, payload)
    plan = _plan()
    with pytest.raises(ValueError):
        build_corpus_reader_prompt(
            acquisition_dir=acquisition,
            plan=plan,
            batch=plan.batches[0],
            prompts_path=root / "configs/corpus-reader-prompts.yaml",
            questions_path=root / "src/leaders_db/conversational_evidence/data/questions.json",
        )


def test_prompt_allows_unselected_empty_extraction_unit(tmp_path: Path) -> None:
    root = Path.cwd()
    acquisition = tmp_path / "acquisition"
    _write_extraction(acquisition, {
        "source_id": "SRC-1",
        "raw_sha256": "abc",
        "units": [
            {"unit": 1, "locator": "page 1", "text": ""},
            {"unit": 2, "locator": "page 2", "text": "Selected text."},
        ],
    })
    payload = _plan().model_dump(mode="json")
    payload["batches"][0]["unit_ranges"]["SRC-1"] = [2, 2]
    plan = CorpusReadingPlan.model_validate(payload)

    rendered = build_corpus_reader_prompt(
        acquisition_dir=acquisition,
        plan=plan,
        batch=plan.batches[0],
        prompts_path=root / "configs/corpus-reader-prompts.yaml",
        questions_path=root / "src/leaders_db/conversational_evidence/data/questions.json",
    )

    assert "Selected text." in rendered.prompt


def test_request_binding_rejects_unbound_existing_output(tmp_path: Path) -> None:
    root = Path.cwd()
    acquisition = tmp_path / "acquisition"
    _write_extraction(acquisition)
    plan = _plan()
    rendered = build_corpus_reader_prompt(
        acquisition_dir=acquisition,
        plan=plan,
        batch=plan.batches[0],
        prompts_path=root / "configs/corpus-reader-prompts.yaml",
        questions_path=root / "src/leaders_db/conversational_evidence/data/questions.json",
    )
    reader = tmp_path / "reader"
    reader.mkdir()
    (reader / "output.json").write_text("{}")
    with pytest.raises(ValueError, match="without a trusted request"):
        write_reader_request_manifest(
            tmp_path / "reader-request.json",
            rendered,
            "test-profile",
            "a" * 64,
            "test-model",
            BatchFactOutput,
            reader,
        )


def test_corpus_run_binds_selected_paragraph_without_an_extra_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path.cwd()
    acquisition = tmp_path / "acquisition"
    _write_extraction(acquisition)
    plan = _plan()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(plan.model_dump_json())

    def fake_execute(
        project_root: Path,
        profile: object,
        prompt: str,
        model: type[BaseModel],
        output_dir: Path,
        **kwargs: object,
    ) -> BaseModel:
        del project_root, profile, kwargs
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "prompt.txt").write_text(prompt)
        schema = model.model_json_schema()
        make_strict_response_schema(schema)
        (output_dir / "schema.json").write_text(json.dumps(schema))
        if model is BatchFactOutput:
            result = BatchFactOutput.model_validate({
                "facts": [{
                    "source_id": "SRC-1",
                    "start_unit": 1,
                    "end_unit": 1,
                    "fact_summary": "The report documents a material fact.",
                    "question_ids": ["5B.1"],
                    "polarity": "mixed",
                    "period_fit": "target year",
                    "ruler_attribution": "national responsibility",
                    "citation_span_ids": [],
                }],
                "documents_with_no_material_fact": [],
            })
        else:
            result = BatchVerification.model_validate({
                "verdicts": [{
                    "evidence_id": "BATCH-0001-E001",
                    "status": "accepted",
                    "notes": [],
                    "citation_span_ids": ["U1-P1"],
                }],
            })
        (output_dir / "output.json").write_text(result.model_dump_json())
        return result

    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.execute_json_model", fake_execute
    )
    manifest = run_corpus_reading(
        project_root=root,
        acquisition_dir=acquisition,
        plan_path=plan_path,
        output_dir=tmp_path / "reading",
        profile_name="openai-terra-candidate",
        profiles_path=root / "configs/research-models.yaml",
        parallel_batches=1,
    )

    assert json.loads(manifest.read_text())["failed_batch_ids"] == []
    evidence = json.loads(
        (tmp_path / "reading/BATCH-0001/verified-evidence.json").read_text()
    )
    assert evidence[0]["citations"][0]["span_id"] == "U1-P1"
    request = json.loads(
        (tmp_path / "reading/BATCH-0001/reader-request.json").read_text()
    )
    assert request["prompt_config_version"] == 2

    def fail_execute(*args, **kwargs):
        pytest.fail("completed bound batch must recover without another model call")

    monkeypatch.setattr(
        "leaders_db.research.corpus_reader_runner.execute_json_model", fail_execute
    )
    run_corpus_reading(
        project_root=root,
        acquisition_dir=acquisition,
        plan_path=plan_path,
        output_dir=tmp_path / "reading",
        profile_name="openai-terra-candidate",
        profiles_path=root / "configs/research-models.yaml",
        parallel_batches=1,
    )
    reader_output_path = tmp_path / "reading/BATCH-0001/reader/output.json"
    original_reader_output = reader_output_path.read_text()
    tampered_reader = json.loads(original_reader_output)
    tampered_reader["facts"][0]["citation_span_ids"] = ["U1-P1"]
    reader_output_path.write_text(json.dumps(tampered_reader))
    with pytest.raises(RuntimeError, match="corpus reading is incomplete"):
        run_corpus_reading(
            project_root=root,
            acquisition_dir=acquisition,
            plan_path=plan_path,
            output_dir=tmp_path / "reading",
            profile_name="openai-terra-candidate",
            profiles_path=root / "configs/research-models.yaml",
            parallel_batches=1,
        )
    reader_output_path.write_text(original_reader_output)
    (tmp_path / "reading/BATCH-0001/verification/request-manifest.json").unlink()
    with pytest.raises(RuntimeError, match="corpus reading is incomplete"):
        run_corpus_reading(
            project_root=root,
            acquisition_dir=acquisition,
            plan_path=plan_path,
            output_dir=tmp_path / "reading",
            profile_name="openai-terra-candidate",
            profiles_path=root / "configs/research-models.yaml",
            parallel_batches=1,
        )


def test_request_reload_rejects_prompt_schema_and_profile_tamper(tmp_path: Path) -> None:
    root = Path.cwd()
    acquisition = tmp_path / "acquisition"
    _write_extraction(acquisition)
    plan = _plan()
    rendered = build_corpus_reader_prompt(
        acquisition_dir=acquisition,
        plan=plan,
        batch=plan.batches[0],
        prompts_path=root / "configs/corpus-reader-prompts.yaml",
        questions_path=root / "src/leaders_db/conversational_evidence/data/questions.json",
    )
    reader = tmp_path / "reader"
    reader.mkdir()
    request = tmp_path / "reader-request.json"
    write_reader_request_manifest(
        request,
        rendered,
        "test-profile",
        "a" * 64,
        "test-model",
        BatchFactOutput,
        reader,
    )
    (reader / "prompt.txt").write_text(rendered.prompt)
    (reader / "output.json").write_text("{}")
    schema = BatchFactOutput.model_json_schema()
    make_strict_response_schema(schema)
    (reader / "schema.json").write_text(json.dumps(schema))
    write_reader_request_manifest(
        request,
        rendered,
        "test-profile",
        "a" * 64,
        "test-model",
        BatchFactOutput,
        reader,
    )

    (reader / "prompt.txt").write_text("tampered")
    with pytest.raises(ValueError, match="saved corpus reader prompt"):
        write_reader_request_manifest(
            request, rendered, "test-profile", "a" * 64, "test-model",
            BatchFactOutput, reader,
        )
    (reader / "prompt.txt").write_text(rendered.prompt)
    (reader / "schema.json").write_text("{}")
    with pytest.raises(ValueError, match="output schema differs"):
        write_reader_request_manifest(
            request, rendered, "test-profile", "a" * 64, "test-model",
            BatchFactOutput, reader,
        )
    (reader / "schema.json").write_text(json.dumps(schema))
    with pytest.raises(ValueError, match="request binding differs"):
        write_reader_request_manifest(
            request, rendered, "test-profile", "b" * 64, "test-model",
            BatchFactOutput, reader,
        )
