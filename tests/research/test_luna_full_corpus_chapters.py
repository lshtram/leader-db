"""Tests for the budgeted full-corpus Luna chapter runner."""

import importlib.util
import json
import urllib.error
from pathlib import Path


def _module():
    path = Path("scripts/experiments/run_luna_full_corpus_chapters.py")
    spec = importlib.util.spec_from_file_location("full_luna", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partition_preserves_order_and_records_once() -> None:
    module = _module()
    records = [
        {key: ("x" * 500 if key == "exact_excerpt" else f"{key}-{number}")
         for key in module.EVIDENCE_FIELDS}
        for number in range(5)
    ]
    original_tokens = module.SHARD_TOKENS
    module.SHARD_TOKENS = 200
    try:
        shards = module._partition(records)
    finally:
        module.SHARD_TOKENS = original_tokens

    assert [item for shard in shards for item in shard] == records
    assert len(shards) > 1


def test_cost_projection_stays_below_budget_for_small_fixture(tmp_path) -> None:
    module = _module()
    shards = (({key: "value" for key in module.EVIDENCE_FIELDS},),)

    projection = module._project_cost(shards, Path("."), ("1B",))

    assert 0 < projection < module.BUDGET_USD


def test_call_guard_rejects_budget_boundary() -> None:
    module = _module()

    try:
        module._guard_call(4.99, "expensive prompt " * 10_000, 500)
    except RuntimeError as error:
        assert "$5.00" in str(error)
    else:
        raise AssertionError("budget boundary was not enforced")


def test_retry_delay_uses_api_message_and_stays_bounded() -> None:
    module = _module()
    error = urllib.error.HTTPError("url", 429, "limited", {}, None)

    assert module._retry_seconds(error, "Please try again in 32.46s") == 34.46
    assert module._retry_seconds(error, "Please try again in 300s") == 60.0


def test_compact_shard_output_must_be_complete_json() -> None:
    module = _module()

    module.validate_shard_output(
        '{"findings":[["E-1",["1B.1","3B.2"],"supporting"]]}.'
    )
    try:
        module.validate_shard_output('{"findings":[["E-1"')
    except RuntimeError as error:
        assert "truncated or malformed" in str(error)
    else:
        raise AssertionError("truncated output was accepted")

    try:
        module.validate_shard_output('{"findings":[]} explanation')
    except RuntimeError as error:
        assert "content after" in str(error)
    else:
        raise AssertionError("substantive trailing output was accepted")


def test_synthesis_requires_all_ten_questions() -> None:
    module = _module()
    payload = {
        "chapter_id": "1B",
        "question_answers": [
            {"question_id": f"1B.{number}"} for number in range(1, 11)
        ],
    }

    module.validate_synthesis(json.dumps(payload), "1B")
    payload["question_answers"].pop()
    try:
        module.validate_synthesis(json.dumps(payload), "1B")
    except RuntimeError as error:
        assert "all ten" in str(error)
    else:
        raise AssertionError("incomplete synthesis was accepted")


def test_synthesis_schema_does_not_truncate_prose_fields() -> None:
    module = _module()

    schema = module.synthesis_format("1B")["schema"]
    properties = schema["properties"]["question_answers"]["items"]["properties"]

    assert properties["answer"] == {"type": "string"}
    assert properties["uncertainty"] == {"type": "string"}


def test_synthesis_drops_unregistered_ids_without_guessing() -> None:
    module = _module()
    payload = {"question_answers": [{
        "supporting_ids": ["E-1", "MADE-UP"],
        "contrary_ids": ["E-2"],
    }]}

    normalized, removed = module.normalize_synthesis_ids(
        json.dumps(payload), {"E-1", "E-2"}
    )

    assert removed == ["MADE-UP"]
    assert json.loads(normalized)["question_answers"][0]["supporting_ids"] == ["E-1"]
