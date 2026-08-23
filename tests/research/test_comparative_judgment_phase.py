from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema
from leaders_db.research.comparative_judgment_phase import (
    _validate_file_read_events,
    _validate_no_tool_events,
    build_cross_shard_calibration_preflight,
    load_comparative_judgment_authorization,
)


def test_v8_comparative_preflight_reconstructs_without_calls(tmp_path: Path) -> None:
    root = Path.cwd()
    run = root / "research/runs/five-ruler-2023-luna-sol-v8-release"
    preflight = run / "comparative-judgment-preflight-v8.json"
    authorization = load_comparative_judgment_authorization(
        preflight_path=preflight,
        approved_preflight_sha256=sha256(preflight.read_bytes()).hexdigest(),
        input_root=run / "chapter-judgment-preflight-inputs-v8",
        profile_name="openai-sol-supervisor",
        profiles_path=root / "configs/research-models.yaml",
        stage_budgets_path=root / "configs/research-stage-budgets.yaml",
        run_dir=run,
    )

    assert len(authorization.request_sha256s) == 40
    saved_request = json.loads(
        (run / "chapter-judgment-preflight-inputs-v8/1B-CHN.json").read_text()
    )
    normalized_schema = deepcopy(saved_request["schema"])
    make_strict_response_schema(normalized_schema)
    assert normalized_schema == saved_request["schema"]
    with pytest.raises(FileNotFoundError):
        build_cross_shard_calibration_preflight(
            authorization=authorization,
            run_dir=tmp_path,
            output_path=tmp_path / "final-preflight.json",
        )


def test_file_backed_judgment_allows_only_exact_single_read(tmp_path: Path) -> None:
    paths = ("/frozen/CHN.json", "/frozen/PRK.json")
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"type":"thread.started","thread_id":"t"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"item.started","item":{"id":"cmd-1","type":"command_execution",'
        '"command":"/bin/bash -lc \'cat -- /frozen/CHN.json /frozen/PRK.json\'",'
        '"status":"in_progress"}}\n'
        '{"type":"item.completed","item":{"id":"cmd-1","type":"command_execution",'
        '"command":"/bin/bash -lc \'cat -- /frozen/CHN.json /frozen/PRK.json\'",'
        '"status":"completed","exit_code":0}}\n'
        '{"type":"turn.completed","usage":{}}\n'
    )

    _validate_file_read_events(events, paths)

    events.write_text(
        '{"type":"item.started","item":{"id":"cmd-2","type":"command_execution",'
        '"command":"cat -- /frozen/CHN.json /etc/passwd",'
        '"status":"in_progress"}}\n'
        '{"type":"item.completed","item":{"id":"cmd-2","type":"command_execution",'
        '"command":"cat -- /frozen/CHN.json /etc/passwd",'
        '"status":"completed","exit_code":0}}\n'
    )
    with pytest.raises(ValueError, match="outside its exact file inventory"):
        _validate_file_read_events(events, paths)


def test_embedded_judgment_rejects_every_tool_event(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"type":"thread.started","thread_id":"t"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"type":"reasoning"}}\n'
        '{"type":"item.completed","item":{"type":"agent_message"}}\n'
        '{"type":"turn.completed","usage":{}}\n'
    )
    _validate_no_tool_events(events)
    events.write_text(
        '{"type":"item.completed","item":{"type":"web_search","query":"outside evidence"}}\n'
    )
    with pytest.raises(ValueError, match="used a tool"):
        _validate_no_tool_events(events)
