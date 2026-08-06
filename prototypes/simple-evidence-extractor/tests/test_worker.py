from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from simple_evidence.broker import broker_request
from simple_evidence.worker import _windows, run_evidence_job


def test_windows_cover_source_with_bounded_overlap() -> None:
    assert _windows(10, 6, 2) == ((1, 6), (5, 10))
    assert _windows(3, 6, 2) == ((1, 3),)


def test_orchestration_resumes_completed_window_without_model_call(
    manifest_path: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "profiles": [{"name": "fake", "model": "Fake"}],
                "window_sentences": 10,
                "overlap_sentences": 1,
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_invoke_model(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["role"])
        if kwargs["role"] == "extractor":
            broker_request(
                kwargs["socket_path"],
                arguments=["show", "DOC-1", "1", "4"],
                capability=kwargs["capability"],
            )
            added = broker_request(
                kwargs["socket_path"],
                arguments=[
                    "add",
                    "DOC-1",
                    "1",
                    "--summary",
                    "The authority adopted Rule A.",
                ],
                capability=kwargs["capability"],
            )
            broker_request(
                kwargs["socket_path"],
                arguments=["confirm", added["fact_id"]],
                capability=kwargs["capability"],
            )
        else:
            fact_id = next(
                line["state"]["fact_id"]
                for line in (
                    json.loads(item)
                    for item in kwargs["registry_path"].read_text().splitlines()
                )
                if line["event"] == "fact_added"
            )
            broker_request(
                kwargs["socket_path"],
                arguments=["show", fact_id],
                capability=kwargs["capability"],
            )
            broker_request(
                kwargs["socket_path"],
                arguments=["confirm", fact_id],
                capability=kwargs["capability"],
            )
        return {"total_tokens": 0, "returncode": 0}

    monkeypatch.setattr("simple_evidence.worker.invoke_model", fake_invoke_model)
    output = tmp_path / "run"
    first = run_evidence_job(
        manifest_path=manifest_path,
        config_path=config,
        output_dir=output,
        maximum_windows=1,
    )
    call_count = len(calls)
    marker_path = next((output / "windows").glob("*.json"))
    marker_path.unlink()
    registry_path = output / "registry.jsonl"
    lines = registry_path.read_text(encoding="utf-8").splitlines()
    registry_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    second = run_evidence_job(
        manifest_path=manifest_path,
        config_path=config,
        output_dir=output,
        maximum_windows=1,
    )

    assert first["accepted"] == 1
    assert second["accepted"] == 1
    assert calls[call_count:] == ["reviewer"]

    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["start_sentence"] = 2
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValueError, match="marker identity changed"):
        run_evidence_job(
            manifest_path=manifest_path,
            config_path=config,
            output_dir=output,
            maximum_windows=1,
        )
    marker["start_sentence"] = 1
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    lines = registry_path.read_text(encoding="utf-8").splitlines()
    registry_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unfinished facts"):
        run_evidence_job(
            manifest_path=manifest_path,
            config_path=config,
            output_dir=output,
            maximum_windows=1,
        )
