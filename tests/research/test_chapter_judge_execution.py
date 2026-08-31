from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research.chapter_judge_worker import (
    execute_claimed_chapter_judge_job,
)
from leaders_db.research.chapter_score_store import persist_chapter_batch_and_complete
from leaders_db.research.job_ledger import (
    ResearchJobSpec,
    claim_next_job,
    complete_job,
    create_jobs,
)
from tests.research.test_chapter_judge_worker import (
    _assert_tolerant_bias_persistence,
    _dossier_payload,
    _judge_candidate,
)


def test_chapter_judge_executes_two_dossiers_and_persists_scores_atomically(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'judge.sqlite'}"
    init_database(database_url)
    engine = create_engine(database_url)
    project = tmp_path / "project"
    project.mkdir()
    budget_dir = project / "configs"
    budget_dir.mkdir()
    (budget_dir / "research-stage-budgets.yaml").write_bytes(
        Path("configs/research-stage-budgets.yaml").read_bytes()
    )
    (budget_dir / "research-control-flow.yaml").write_bytes(
        Path("configs/research-control-flow.yaml").read_bytes()
    )
    guide_dir = project / "docs/methodology/chapter-guides"
    guide_dir.mkdir(parents=True)
    (guide_dir / "4b-political-freedom.md").write_text(
        "# 4B\n\n- Rubric version: `chapter_4b_v1`\n\nUse one common meter.\n",
        encoding="utf-8",
    )
    profiles = project / "profiles.yaml"
    profiles.write_text(
        """version: 1
profiles:
  fixture:
    provider: openai
    model: gpt-fixture
    execution_surface: codex
    roles: [chapter_judge]
    cost_class: test
    context_window: 100000
    codex_config_path: ~/.codex/config.toml
    credential_path: ~/.codex/auth.json
    notes: Fixture profile.
""",
        encoding="utf-8",
    )
    output_root = project / "outputs"
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    local_path = project / "local-priors.json"
    local_payload = [
        {
            "methodology_id": methodology_id,
            "status": "evidence_found",
            "mapping_note": "Country-level structured context.",
            "local_facts": [
                {
                    "field_key": "electoral_democracy",
                    "label": "Electoral democracy",
                    "value": 0.62,
                    "value_type": "number",
                    "year": 2020,
                    "source_slugs": ["vdem"],
                    "source_observation_ids": ["vdem:AAA:2020:electoral_democracy"],
                    "confidence": 88,
                    "warnings": ["Ruler attribution requires cited evidence."],
                    "period_role": "target",
                    "unit": "index",
                    "scale": "0-1",
                }
            ],
        }
        for methodology_id in methodology_ids
    ]
    local_encoded = json.dumps(local_payload, sort_keys=True).encode()
    local_path.write_bytes(local_encoded)
    local_digest = sha256(local_encoded).hexdigest()
    parent_ids: list[int] = []
    dossier_job_keys: list[str] = []
    for index, iso3 in enumerate(("AAA", "AAA"), start=1):
        parent_run_key = f"batch-{index}"
        key = f"dossier:{parent_run_key}:2020:{iso3}:{index}"
        dossier_job_keys.append(key)
        create_jobs(
            engine,
            (
                ResearchJobSpec(
                    job_key=key,
                    run_key=parent_run_key,
                    job_type="dossier_researcher",
                    target_year=2020,
                    period_start_year=2020,
                    period_end_year=2020,
                    iso3=iso3,
                    country_name=f"Country {iso3}",
                    ruler_id=str(index),
                    ruler_name=f"Ruler {index}",
                    provider_profile="fixture",
                    provider="openai",
                    model="gpt-fixture",
                    input_payload={
                        "question_ids": list(methodology_ids),
                        "ruler_year_id": 100 + index,
                        "output_root": str(output_root),
                    },
                ),
            ),
        )
        parent = claim_next_job(
            engine,
            worker_id=f"researcher-{index}",
            lease_seconds=900,
            job_type="dossier_researcher",
            run_key=parent_run_key,
        )
        assert parent is not None
        dossier_path = project / f"dossier-{iso3}-{index}.json"
        dossier_payload = _dossier_payload(parent, methodology_ids=methodology_ids)
        for prior in dossier_payload["local_priors"]:
            prior["artifact_path"] = str(local_path)
            prior["artifact_sha256"] = local_digest
        dossier_path.write_text(json.dumps(dossier_payload), encoding="utf-8")
        complete_job(
            engine,
            job_id=int(parent["id"]),
            worker_id=f"researcher-{index}",
            lease_token=str(parent["lease_token"]),
            result_path=str(dossier_path),
        )
        parent_ids.append(int(parent["id"]))

    judge_key = "chapter-judge:batch:2020:4B"
    create_jobs(
        engine,
        (
            ResearchJobSpec(
                job_key=judge_key,
                run_key="batch",
                job_type="question_judge",
                target_year=2020,
                question_id="4B",
                provider_profile="fixture",
                provider="openai",
                model="gpt-fixture",
                input_payload={
                    "chapter_id": "4B",
                    "rubric_version": "chapter_4b_v1",
                    "methodology_ids": list(methodology_ids),
                    "dossier_job_keys": dossier_job_keys,
                    "dossier_run_key": None,
                    "dossier_run_keys": ["batch-1", "batch-2"],
                    "unavailable_dossiers": [],
                    "output_root": str(output_root),
                },
            ),
        ),
        dependencies_by_job_key={judge_key: tuple(parent_ids)},
    )
    judge = claim_next_job(
        engine,
        worker_id="judge-worker",
        lease_seconds=900,
        job_type="question_judge",
        run_key="batch",
    )
    assert judge is not None
    monkeypatch.setattr(
        "leaders_db.research.chapter_judge_worker.FILE_BACKED_PROMPT_THRESHOLD_BYTES",
        0,
    )

    def fake_run_codex(*args, **kwargs) -> None:
        prompt = kwargs["prompt"]
        assert "Chapter projections (authoritative judge inputs)" in prompt
        assert "A cited political-freedom fact." not in prompt
        assert '"sha256"' in prompt
        assert "Read every listed file in full" in prompt
        assert all(
            text in prompt
            for text in (
                "formal responsibility for national policy",
                "Chapter 7B requires a personal-integrity nexus",
                "structured local facts and signals use LF/LS IDs",
                "rewrite a local fact as a web citation",
            )
        )
        command = kwargs["command"]
        command_root = Path(command[command.index("--cd") + 1])
        assert command_root.name.startswith("001-")
        input_paths = tuple(command_root.glob("chapter-inputs/*.json"))
        assert len(input_paths) == 2
        assert all(str(path.resolve()) in prompt for path in input_paths)
        assert all("LF001" in path.read_text(encoding="utf-8") for path in input_paths)
        result_path = Path(command[command.index("--output-last-message") + 1])
        candidate = _judge_candidate(
            dossier_job_keys=dossier_job_keys,
            iso3s=("AAA", "AAA"),
        )
        for evaluation in candidate["evaluations"]:
            evaluation["contextual_local_evidence"] = [
                {
                    "local_evidence_id": "LF001",
                    "explanation": "Structured target-year country context.",
                }
            ]
            evaluation["structured_prior_summary"] = (
                "The available LF001 structured context is interpreted with cited "
                "ruler-attribution evidence."
            )
        for evaluation in candidate["evaluations"]:
            del evaluation["bias_assessment"]
        result_path.write_text(json.dumps(candidate), encoding="utf-8")
        kwargs["events_path"].write_text(
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 1200, "output_tokens": 300},
                }
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr("leaders_db.research.chapter_judge_worker._run_codex", fake_run_codex)
    result_path, batch = execute_claimed_chapter_judge_job(
        engine,
        job=judge,
        worker_id="judge-worker",
        project_root=project,
        model_profiles_path=profiles,
        lease_seconds=900,
        heartbeat_seconds=60,
        timeout_seconds=600,
    )
    completed = persist_chapter_batch_and_complete(
        engine,
        batch=batch,
        job_id=int(judge["id"]),
        worker_id="judge-worker",
        lease_token=str(judge["lease_token"]),
        result_path=result_path,
    )

    _assert_tolerant_bias_persistence(completed, batch)
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT iso3, ruler_year_id, score_1_to_10, method_version, job_key, "
                    "judgment_json FROM chapter_scores ORDER BY ruler_year_id"
                )
            )
            .mappings()
            .all()
        )
    assert [(row["iso3"], row["score_1_to_10"]) for row in rows] == [
        ("AAA", 4.0),
        ("AAA", 7.0),
    ]
    assert {row["method_version"] for row in rows} == {"chapter_4b_v1"}
    assert {row["job_key"] for row in rows} == {judge_key}
    assert all(json.loads(row["judgment_json"])["chapter_rationale"] for row in rows)
    assert all(
        json.loads(row["judgment_json"])["contextual_local_evidence"][0]["local_evidence_id"]
        == "LF001"
        for row in rows
    )
    assert json.loads(rows[0]["judgment_json"])["chapter_specific"] == [
        {"field": "trajectory", "value": "Stable fixture trajectory."}
    ]
