from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.citation_span_experiment import (
    SpanReaderOutput,
    run_span_quality_comparison,
    run_span_reader_experiment,
)
from leaders_db.research.citation_span_validation import (
    apply_span_corrections,
    validate_span_quality_comparison,
    validate_span_reader_experiment,
)


def _baseline() -> dict:
    return {
        "evidence_id": "BATCH-0021-R01-E006",
        "source_id": "SRC-afccda2f4a47b2bb",
        "title": "Synthetic source",
        "start_unit": 1,
        "end_unit": 1,
        "question_ids": ["5B.10"],
        "limitations": ["Descriptive only."],
        "fact_summary": (
            "Among people aged 15 and over, the employment rate was 71.9% "
            "for residents of owner-occupied dwellings."
        ),
    }


def _fake_execute(
    project_root: Path,
    profile: object,
    prompt: str,
    schema_type: type[BaseModel],
    output_dir: Path,
) -> BaseModel:
    del project_root, profile
    output_dir.mkdir(parents=True)
    if schema_type is SpanReaderOutput:
        payload = {
            "facts": [{
                "fact_summary": "A supported synthetic employment fact.",
                "question_ids": ["5B.10"],
                "polarity": "mixed",
                "period_fit": "Direct 2023 measurement.",
                "ruler_attribution": "No ruler attribution.",
                "limitations": ["Descriptive only."],
                "span_ids": ["U1-P1"],
            }],
            "slice_limitations": [],
        }
    else:
        payload = {
            "factual_accuracy": "pass",
            "material_coverage": "pass",
            "balance": "pass",
            "routing_and_attribution": "pass",
            "locator_fidelity": "pass",
            "material_omissions": [],
            "rationale": "The corrected comparison preserves every material synthetic fact.",
        }
    schema = schema_type.model_json_schema()
    make_strict_response_schema(schema)
    (output_dir / "prompt.txt").write_text(prompt)
    (output_dir / "output.json").write_text(json.dumps(payload))
    (output_dir / "schema.json").write_text(json.dumps(schema))
    return schema_type.model_validate(payload)


@pytest.fixture
def span_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path | dict]:
    root = Path.cwd()
    extraction = tmp_path / "extraction.json"
    extraction.write_text(json.dumps({
        "source_id": "SRC-afccda2f4a47b2bb",
        "units": [{"unit": 1, "text": "First supported paragraph.\n\nSecond paragraph."}],
    }))
    monkeypatch.setattr(
        "leaders_db.research.citation_span_experiment.execute_json_model", _fake_execute
    )
    reader_dir = tmp_path / "reader"
    reader_manifest = run_span_reader_experiment(
        project_root=root,
        extraction_path=extraction,
        baseline=_baseline(),
        corrections_path=root / "configs/citation-span-corrections.yaml",
        output_dir=reader_dir,
        profile_name="openai-terra-candidate",
        profiles_path=root / "configs/research-models.yaml",
    )
    comparison_dir = tmp_path / "comparison"
    comparison_manifest = run_span_quality_comparison(
        project_root=root,
        baseline=_baseline(),
        corrections_path=root / "configs/citation-span-corrections.yaml",
        reader_manifest_path=reader_manifest,
        extraction_path=extraction,
        reader_profile_name="openai-terra-candidate",
        output_dir=comparison_dir,
        profile_name="openai-sol-supervisor",
        profiles_path=root / "configs/research-models.yaml",
    )
    return {
        "root": root,
        "extraction": extraction,
        "baseline": _baseline(),
        "reader": reader_manifest,
        "comparison": comparison_manifest,
    }


def test_correction_is_explicit_and_does_not_mutate_baseline() -> None:
    baseline = _baseline()
    corrected = apply_span_corrections(
        baseline, Path("configs/citation-span-corrections.yaml")
    )
    assert "60.1%" in corrected["fact_summary"]
    assert "71.9%" in baseline["fact_summary"]


def test_trusted_span_experiment_roundtrip(span_run: dict[str, Path | dict]) -> None:
    root = span_run["root"]
    assert isinstance(root, Path)
    reader = validate_span_reader_experiment(
        project_root=root,
        manifest_path=span_run["reader"],
        extraction_path=span_run["extraction"],
        baseline=span_run["baseline"],
        corrections_path=root / "configs/citation-span-corrections.yaml",
        expected_profile_name="openai-terra-candidate",
        profiles_path=root / "configs/research-models.yaml",
    )
    comparison = validate_span_quality_comparison(
        project_root=root,
        manifest_path=span_run["comparison"],
        baseline=span_run["baseline"],
        corrections_path=root / "configs/citation-span-corrections.yaml",
        reader_manifest_path=span_run["reader"],
        extraction_path=span_run["extraction"],
        reader_profile_name="openai-terra-candidate",
        expected_profile_name="openai-sol-supervisor",
        profiles_path=root / "configs/research-models.yaml",
    )
    assert reader["fact_count"] == 1
    assert comparison["quality_gate"] == "pass"


def test_trusted_reader_rejects_saved_prompt_tamper(
    span_run: dict[str, Path | dict],
) -> None:
    manifest_path = span_run["reader"]
    assert isinstance(manifest_path, Path)
    (manifest_path.parent / "prompt.txt").write_text("altered")
    with pytest.raises(ValueError, match="prompt mismatch"):
        validate_span_reader_experiment(
            project_root=span_run["root"],
            manifest_path=manifest_path,
            extraction_path=span_run["extraction"],
            baseline=span_run["baseline"],
            corrections_path=Path("configs/citation-span-corrections.yaml"),
            expected_profile_name="openai-terra-candidate",
            profiles_path=Path("configs/research-models.yaml"),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("estimated_input_tokens", 1),
        ("unit_range", [1, 2]),
        ("question_ids", ["8B.10"]),
        ("unexpected", "field"),
    ],
)
def test_trusted_reader_rejects_manifest_substitution(
    span_run: dict[str, Path | dict], field: str, value: object
) -> None:
    manifest_path = span_run["reader"]
    assert isinstance(manifest_path, Path)
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="does not reconstruct"):
        validate_span_reader_experiment(
            project_root=span_run["root"],
            manifest_path=manifest_path,
            extraction_path=span_run["extraction"],
            baseline=span_run["baseline"],
            corrections_path=Path("configs/citation-span-corrections.yaml"),
            expected_profile_name="openai-terra-candidate",
            profiles_path=Path("configs/research-models.yaml"),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"facts": [], "slice_limitations": []},
        {
            "facts": [{
                "fact_summary": "A supported synthetic employment fact.",
                "question_ids": [],
                "polarity": "invented",
                "period_fit": "",
                "ruler_attribution": "",
                "limitations": [],
                "span_ids": ["U1-P1"],
            }],
            "slice_limitations": [],
        },
    ],
)
def test_reader_contract_rejects_empty_or_unstructured_facts(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SpanReaderOutput.model_validate(payload)


@pytest.mark.parametrize("polarity", ["exculpatory", "context"])
def test_reader_contract_accepts_canonical_qualifying_polarities(polarity: str) -> None:
    payload = {
        "facts": [{
            "fact_summary": "A supported synthetic employment fact.",
            "question_ids": ["5B.10"],
            "polarity": polarity,
            "period_fit": "Direct 2023 measurement.",
            "ruler_attribution": "No ruler attribution.",
            "limitations": [],
            "span_ids": ["U1-P1"],
        }],
        "slice_limitations": [],
    }
    assert SpanReaderOutput.model_validate(payload).facts[0].polarity == polarity


@pytest.mark.parametrize(
    ("start_unit", "end_unit", "text", "error"),
    [
        (2, 1, "Supported text.", "source range is invalid"),
        (1, 1, " \r\n\t ", "contains no text spans"),
    ],
)
def test_reader_rejects_empty_source_ranges_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start_unit: int,
    end_unit: int,
    text: str,
    error: str,
) -> None:
    root = Path.cwd()
    baseline = _baseline()
    baseline.update(start_unit=start_unit, end_unit=end_unit)
    extraction = tmp_path / "extraction.json"
    extraction.write_text(json.dumps({
        "source_id": baseline["source_id"],
        "units": [{"unit": start_unit, "text": text}],
    }))
    monkeypatch.setattr(
        "leaders_db.research.citation_span_experiment.execute_json_model",
        lambda *args, **kwargs: pytest.fail("model execution must not occur"),
    )
    with pytest.raises(ValueError, match=error):
        run_span_reader_experiment(
            project_root=root,
            extraction_path=extraction,
            baseline=baseline,
            corrections_path=root / "configs/citation-span-corrections.yaml",
            output_dir=tmp_path / "reader",
            profile_name="openai-terra-candidate",
            profiles_path=root / "configs/research-models.yaml",
        )


def test_trusted_comparison_rejects_gate_tamper(
    span_run: dict[str, Path | dict],
) -> None:
    manifest_path = span_run["comparison"]
    assert isinstance(manifest_path, Path)
    manifest = json.loads(manifest_path.read_text())
    manifest["quality_gate"] = "fail"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="does not reconstruct"):
        validate_span_quality_comparison(
            project_root=span_run["root"],
            manifest_path=manifest_path,
            baseline=span_run["baseline"],
            corrections_path=Path("configs/citation-span-corrections.yaml"),
            reader_manifest_path=span_run["reader"],
            extraction_path=span_run["extraction"],
            reader_profile_name="openai-terra-candidate",
            expected_profile_name="openai-sol-supervisor",
            profiles_path=Path("configs/research-models.yaml"),
        )
