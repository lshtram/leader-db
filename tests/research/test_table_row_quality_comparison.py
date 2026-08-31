from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.table_row_quality_comparison import (
    TableRowQualityOutput,
    prepare_table_row_quality_request,
    run_table_row_quality_comparison,
)


def _passing_payload() -> dict:
    common = {
        "population": "Total population aged 15 and over",
        "statistic": "Employment rate",
        "unit_of_measure": "Percentages",
    }
    return {
        "owner_occupied": common | {
            "value_percent": 60.1,
            "column_meaning": "Owner-occupied dwelling",
            "citation_line_ids": ["U236-L12", "U236-L13", "U236-L45", "U236-L48"],
        },
        "rented_total": common | {
            "value_percent": 71.9,
            "column_meaning": "Rented dwelling Total(2)",
            "citation_line_ids": [
                "U236-L7", "U236-L12", "U236-L13", "U236-L45", "U236-L48"
            ],
        },
        "jewish_total": common | {
            "value_percent": 65.7,
            "population": "Jewish population aged 15 and over",
            "column_meaning": "Total(1), not a dwelling column",
            "citation_line_ids": ["U238-L10", "U238-L11", "U238-L43", "U238-L46"],
        },
        "arab_total": common | {
            "value_percent": 49.2,
            "population": "Arab population aged 15 and over",
            "column_meaning": "Total(1), not a dwelling column",
            "citation_line_ids": ["U240-L10", "U240-L11", "U240-L43", "U240-L46"],
        },
        "limitations": [
            "The table is descriptive and provides no causation or attribution to a ruler.",
            "Jewish and Arab Total(1) values are population totals, not dwelling "
            "comparisons; Total(2) is rented.",
        ],
        "ruler_causal_attribution": "none",
        "summary": "The exact rows preserve all four corrected employment-rate comparisons.",
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
    payload = _passing_payload()
    schema = schema_type.model_json_schema()
    make_strict_response_schema(schema)
    (output_dir / "prompt.txt").write_text(prompt)
    (output_dir / "output.json").write_text(json.dumps(payload))
    (output_dir / "schema.json").write_text(json.dumps(schema))
    (output_dir / "events.jsonl").write_text(json.dumps({
        "type": "turn.completed",
        "usage": {
            "input_tokens": 100,
            "cached_input_tokens": 0,
            "output_tokens": 50,
            "reasoning_output_tokens": 10,
        },
    }) + "\n")
    return schema_type.model_validate(payload)


def test_request_reconstructs_task_one_hashes_and_required_context() -> None:
    root = Path.cwd()
    request = prepare_table_row_quality_request(
        project_root=root,
        config_path=root / "configs/table-row-quality-comparison.yaml",
        profiles_path=root / "configs/research-models.yaml",
    )

    assert request["profile"].model == "gpt-5.6-sol"
    assert request["estimated_input_tokens"] < 4_000
    assert {item["line_id"] for item in request["line_bindings"]} >= {
        "U236-L12", "U236-L48", "U238-L10", "U238-L46", "U240-L10", "U240-L46"
    }
    assert all(len(item["span"]["text_sha256"]) == 64 for item in request["line_bindings"])


def test_single_result_passes_only_with_correct_values_context_and_limitations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path.cwd()
    monkeypatch.setattr(
        "leaders_db.research.table_row_quality_comparison.execute_json_model", _fake_execute
    )
    manifest_path = run_table_row_quality_comparison(
        project_root=root,
        config_path=root / "configs/table-row-quality-comparison.yaml",
        profiles_path=root / "configs/research-models.yaml",
        output_dir=tmp_path / "quality",
    )
    manifest = json.loads(manifest_path.read_text())

    assert manifest["status"] == "passed"
    assert manifest["model_calls"] == 1
    assert manifest["serialized_request_size_reduction_percent"] > 80
    assert not manifest["gate_failures"]


def test_gate_rejects_one_incorrect_result_without_another_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def failing_execute(*args: object, **kwargs: object) -> TableRowQualityOutput:
        nonlocal calls
        calls += 1
        payload = _passing_payload()
        payload["arab_total"]["value_percent"] = 51.6
        output_dir = args[4]
        assert isinstance(output_dir, Path)
        output_dir.mkdir(parents=True)
        schema = TableRowQualityOutput.model_json_schema()
        (output_dir / "prompt.txt").write_text(str(args[2]))
        (output_dir / "output.json").write_text(json.dumps(payload))
        (output_dir / "schema.json").write_text(json.dumps(schema))
        (output_dir / "events.jsonl").write_text(json.dumps({
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 50,
                "reasoning_output_tokens": 10,
            },
        }) + "\n")
        return TableRowQualityOutput.model_validate(payload)

    monkeypatch.setattr(
        "leaders_db.research.table_row_quality_comparison.execute_json_model", failing_execute
    )
    manifest = run_table_row_quality_comparison(
        project_root=Path.cwd(),
        config_path=Path("configs/table-row-quality-comparison.yaml"),
        profiles_path=Path("configs/research-models.yaml"),
        output_dir=tmp_path / "rejected",
    )

    assert calls == 1
    assert json.loads(manifest.read_text())["status"] == "rejected"


def test_gate_rejects_ambiguous_population_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ambiguous_execute(*args: object, **kwargs: object) -> TableRowQualityOutput:
        payload = _passing_payload()
        payload["jewish_total"]["population"] = "Persons aged 15 and over"
        output_dir = args[4]
        assert isinstance(output_dir, Path)
        output_dir.mkdir(parents=True)
        schema = TableRowQualityOutput.model_json_schema()
        (output_dir / "prompt.txt").write_text(str(args[2]))
        (output_dir / "output.json").write_text(json.dumps(payload))
        (output_dir / "schema.json").write_text(json.dumps(schema))
        (output_dir / "events.jsonl").write_text(json.dumps({
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 50,
                "reasoning_output_tokens": 10,
            },
        }) + "\n")
        return TableRowQualityOutput.model_validate(payload)

    monkeypatch.setattr(
        "leaders_db.research.table_row_quality_comparison.execute_json_model",
        ambiguous_execute,
    )
    manifest = run_table_row_quality_comparison(
        project_root=Path.cwd(),
        config_path=Path("configs/table-row-quality-comparison.yaml"),
        profiles_path=Path("configs/research-models.yaml"),
        output_dir=tmp_path / "ambiguous",
    )

    assert json.loads(manifest.read_text())["status"] == "rejected"


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        ("column", "column meaning is ambiguous"),
        ("citations", "omits required header, context, or value citations"),
        ("limitations", "required limitation meaning is missing"),
    ],
)
def test_gate_rejects_incomplete_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_failure: str,
) -> None:
    def incomplete_execute(*args: object, **kwargs: object) -> TableRowQualityOutput:
        payload = _passing_payload()
        if mutation == "column":
            payload["rented_total"]["column_meaning"] = "Rented dwelling"
        elif mutation == "citations":
            payload["owner_occupied"]["citation_line_ids"] = ["U236-L48"]
        else:
            payload["limitations"] = ["This is descriptive and mentions a dwelling."]
        output_dir = args[4]
        assert isinstance(output_dir, Path)
        output_dir.mkdir(parents=True)
        schema = TableRowQualityOutput.model_json_schema()
        (output_dir / "prompt.txt").write_text(str(args[2]))
        (output_dir / "output.json").write_text(json.dumps(payload))
        (output_dir / "schema.json").write_text(json.dumps(schema))
        (output_dir / "events.jsonl").write_text(json.dumps({
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 50,
                "reasoning_output_tokens": 10,
            },
        }) + "\n")
        return TableRowQualityOutput.model_validate(payload)

    monkeypatch.setattr(
        "leaders_db.research.table_row_quality_comparison.execute_json_model",
        incomplete_execute,
    )
    manifest_path = run_table_row_quality_comparison(
        project_root=Path.cwd(),
        config_path=Path("configs/table-row-quality-comparison.yaml"),
        profiles_path=Path("configs/research-models.yaml"),
        output_dir=tmp_path / mutation,
    )
    manifest = json.loads(manifest_path.read_text())

    assert manifest["status"] == "rejected"
    assert any(expected_failure in item for item in manifest["gate_failures"])
