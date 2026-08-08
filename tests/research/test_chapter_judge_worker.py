from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research.chapter_judge_models import RulerChapterJudgment
from leaders_db.research.chapter_judge_prompt import build_chapter_judge_prompt
from leaders_db.research.chapter_judge_worker import (
    _ensure_bias_assessment,
    _find_previous_chapter_candidate,
    _normalize_calibration_references,
    _normalize_confidence_scale,
    _normalize_evidence_reference_lists,
    _normalize_judgment_envelope,
    _normalize_lens_lists,
    _normalize_local_evidence_reference_lists,
    _prepare_batch,
    _write_chapter_projections,
    _write_null_recovery_queue,
    execute_claimed_chapter_judge_job,
)
from leaders_db.research.chapter_projection import build_ruler_chapter_projection
from leaders_db.research.chapter_score_store import persist_chapter_batch_and_complete
from leaders_db.research.dossier_models import RulerEvidenceDossier
from leaders_db.research.job_ledger import (
    ResearchJobSpec,
    claim_next_job,
    complete_job,
    create_jobs,
)


def test_file_backed_prompt_rejects_outside_path_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projection = SimpleNamespace(
        job_key="dossier:test:2023:AAA:1",
        iso3="AAA",
        ruler_id="1",
        ruler_year_id=1,
        ruler_name="Ruler",
        period_start_year=2023,
        period_end_year=2023,
    )
    hashed = False

    def forbidden_hash(path: Path) -> str:
        nonlocal hashed
        hashed = True
        return "0" * 64

    monkeypatch.setattr(
        "leaders_db.research.chapter_judge_prompt._file_sha256", forbidden_hash
    )
    with pytest.raises(ValueError, match="chapter-inputs"):
        build_chapter_judge_prompt(
            {
                "job_key": "chapter-judge:test:2023:1B",
                "run_key": "test",
                "target_year": 2023,
                "input": {"chapter_id": "1B", "unavailable_dossiers": []},
            },
            project_root=tmp_path / "project",
            guide_text="guide",
            projections=((tmp_path / "outside.json", projection),),
            embed_projections=False,
        )
    assert not hashed


def test_normalize_lens_lists_preserves_supported_weak_overlap_as_note() -> None:
    evaluation = {
        "supported_lenses": ["4B.1", "4B.1", "4B.2"],
        "missing_or_weak_lenses": [
            "4B.2",
            "4B.2",
            "4B.3",
            "weak source diversity",
        ],
        "manual_review_reason": "Review sparse evidence.",
    }

    _normalize_lens_lists(
        evaluation, valid_methodology_ids={"4B.1", "4B.2", "4B.3"}
    )

    assert evaluation["supported_lenses"] == ["4B.1", "4B.2"]
    assert evaluation["missing_or_weak_lenses"] == ["4B.3"]
    assert "Partially supported but weak lenses: 4B.2" in evaluation[
        "manual_review_reason"
    ]
    assert evaluation["manual_review_reason"].count("4B.2") == 1
    assert "weak source diversity" in evaluation["manual_review_reason"]


def test_null_judgment_is_normalized_to_release_blocking_review() -> None:
    evaluation = {
        "score_1_to_10": None,
        "insufficient_evidence_reason": "Attribution remains insufficient.",
        "manual_review_required": False,
        "manual_review_reason_type": None,
        "manual_review_reason": None,
    }

    _normalize_judgment_envelope(evaluation)

    assert evaluation["manual_review_required"] is True
    assert evaluation["manual_review_reason_type"] == "recoverable_null"
    assert "Release is blocked" in evaluation["manual_review_reason"]
    assert evaluation["plausible_score_range"] == {"lower": 1, "upper": 10}


def test_normalize_lens_lists_recovers_descriptive_lens_prefixes() -> None:
    evaluation = {
        "supported_lenses": ["2B.1 defensive conduct"],
        "missing_or_weak_lenses": [
            "2B.4 civilian protection, proportionality, and attribution",
            "2B.10: durable end-state change",
        ],
    }

    _normalize_lens_lists(
        evaluation, valid_methodology_ids={"2B.1", "2B.4", "2B.10"}
    )

    assert evaluation["supported_lenses"] == ["2B.1"]
    assert evaluation["missing_or_weak_lenses"] == ["2B.4", "2B.10"]
    assert "civilian protection" in evaluation["manual_review_reason"]


def test_null_recovery_queue_reuses_existing_judgment_fields(tmp_path: Path) -> None:
    evaluation = SimpleNamespace(
        score_1_to_10=None,
        manual_review_reason_type="recoverable_null",
        dossier_job_key="dossier:test",
        iso3="NZL",
        ruler_year_id=12,
        ruler_name="Test Ruler",
        chapter_id="4B",
        insufficient_evidence_reason="Relevant conduct was not recovered.",
        missing_or_weak_lenses=("4B.2", "4B.6"),
        manual_review_reason="Research the ruler's response to constraints.",
    )
    batch = SimpleNamespace(
        job_key="chapter-judge:test:4B",
        chapter_id="4B",
        evaluations=(evaluation,),
    )
    projection = SimpleNamespace(job_key="dossier:test", evidence=(1, 2, 3))
    path = tmp_path / "null-recovery.json"

    _write_null_recovery_queue(batch, projections=((tmp_path, projection),), path=path)

    payload = json.loads(path.read_text())
    assert payload["request_count"] == 1
    assert payload["requests"][0] == {
        "chapter_id": "4B",
        "current_evidence_count": 3,
        "dossier_job_key": "dossier:test",
        "iso3": "NZL",
        "maximum_research_rounds": 2,
        "missing_or_weak_lenses": ["4B.2", "4B.6"],
        "next_action": "resume_same_ruler_research",
        "reason": "Relevant conduct was not recovered.",
        "requested_follow_up": "Research the ruler's response to constraints.",
        "ruler_name": "Test Ruler",
        "ruler_year_id": 12,
    }


def test_normalize_evidence_references_drops_unknown_id_without_guessing() -> None:
    evaluation = {
        "decisive_positive_evidence": [
            {"evidence_id": "E001", "explanation": "Valid."},
            {"evidence_id": "E999", "explanation": "Unknown."},
        ],
        "decisive_negative_evidence": [],
        "contrary_evidence": [],
        "manual_review_required": False,
        "manual_review_reason_type": None,
        "manual_review_reason": None,
    }

    _normalize_evidence_reference_lists(evaluation, valid_evidence_ids={"E001"})

    assert evaluation["decisive_positive_evidence"] == [
        {"evidence_id": "E001", "explanation": "Valid."}
    ]
    assert evaluation["manual_review_required"] is True
    assert evaluation["manual_review_reason_type"] == "projection_integrity"
    assert "E999" in evaluation["manual_review_reason"]


def test_manual_review_requires_stable_reason_type() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["manual_review_required"] = True
    evaluation["manual_review_reason"] = "Attribution could move the score."

    with pytest.raises(ValueError, match="reason type"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["manual_review_reason_type"] = "material_attribution"
    judgment = RulerChapterJudgment.model_validate(evaluation)

    assert judgment.manual_review_reason_type == "material_attribution"


def test_numeric_judgment_requires_half_point_and_cannot_be_recoverable_null() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.2)

    with pytest.raises(ValueError, match=r"multiple of 0\.5"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["manual_review_required"] = True
    evaluation["manual_review_reason_type"] = "recoverable_null"
    evaluation["manual_review_reason"] = "More research may change the score."

    with pytest.raises(ValueError, match="cannot use recoverable_null"):
        RulerChapterJudgment.model_validate(evaluation)


def test_numeric_judgment_requires_traceable_decisive_evidence() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["decisive_positive_evidence"] = []
    evaluation["decisive_negative_evidence"] = []

    with pytest.raises(ValueError, match="requires decisive cited web evidence"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["decisive_local_evidence"] = [
        {
            "local_evidence_id": "LF001",
            "explanation": "Country-level structured context.",
            "harmless_extra_field": "accepted by the tolerant receiver",
        }
    ]
    with pytest.raises(ValueError, match="requires decisive cited web evidence"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["score_1_to_10"] = None
    evaluation["insufficient_evidence_reason"] = "No discriminating evidence."
    evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}
    judgment = RulerChapterJudgment.model_validate(evaluation)

    assert judgment.score_1_to_10 is None


@pytest.mark.parametrize(
    "malformed",
    (None, "LF001", [None, "LF001", {"local_evidence_id": "LF999"}]),
)
def test_local_reference_normalization_tolerates_malformed_values(
    malformed: object,
) -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["contextual_local_evidence"] = malformed

    _normalize_local_evidence_reference_lists(
        evaluation,
        valid_local_evidence_ids={"LF001"},
    )

    assert evaluation["contextual_local_evidence"] == []
    if malformed is None:
        assert evaluation["manual_review_required"] is False
    else:
        assert evaluation["manual_review_required"] is True
        assert evaluation["manual_review_reason_type"] == "projection_integrity"


def test_null_judgment_requires_full_uncertainty_range() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["score_1_to_10"] = None
    evaluation["insufficient_evidence_reason"] = "No discriminating opportunity."
    evaluation["plausible_score_range"] = {"lower": 4, "upper": 6}

    with pytest.raises(ValueError, match="full 1-10 uncertainty range"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}
    judgment = RulerChapterJudgment.model_validate(evaluation)

    assert judgment.score_1_to_10 is None


def test_judgment_requires_explicit_bias_safeguards() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    del evaluation["bias_assessment"]["report_volume_not_used_as_severity"]

    with pytest.raises(ValueError, match="report_volume_not_used_as_severity"):
        RulerChapterJudgment.model_validate(evaluation)


def test_normalize_judgment_envelope_repairs_only_explicit_contract_fields() -> None:
    evaluation: dict[str, object] = {
        "score_1_to_10": None,
        "insufficient_evidence_reason": None,
        "plausible_score_range": {"lower": 4, "upper": 6},
        "chapter_rationale": "Only contextual evidence was available.",
    }

    _normalize_judgment_envelope(evaluation)

    assert evaluation["insufficient_evidence_reason"] == (
        "The judge returned no defensible score; see the chapter rationale."
    )
    assert evaluation["plausible_score_range"] == {"lower": 1, "upper": 10}

    scored = {
        "score_1_to_10": 5,
        "insufficient_evidence_reason": None,
        "plausible_score_range": {"lower": 4, "upper": 6},
    }
    _normalize_judgment_envelope(scored)

    assert scored["plausible_score_range"] == {"lower": 4, "upper": 6}

    scored_recoverable = {
        "score_1_to_10": 4,
        "plausible_score_range": {"lower": 3, "upper": 5},
        "insufficient_evidence_reason": None,
        "decisive_positive_evidence": [{"evidence_id": "E001"}],
        "decisive_negative_evidence": [{"evidence_id": "E002"}],
        "manual_review_required": True,
        "manual_review_reason_type": "recoverable_null",
        "manual_review_reason": "More decisive evidence could materially move the score.",
    }
    expected = scored_recoverable | {"manual_review_reason_type": "decisive_source"}
    _normalize_judgment_envelope(scored_recoverable)

    assert scored_recoverable == expected

    unreviewed_scored = {
        "score_1_to_10": 4,
        "manual_review_required": False,
        "manual_review_reason_type": "recoverable_null",
    }
    _normalize_judgment_envelope(unreviewed_scored)

    assert unreviewed_scored["manual_review_reason_type"] == "recoverable_null"

    missing_score = {"chapter_rationale": "Malformed candidate."}
    _normalize_judgment_envelope(missing_score)

    assert missing_score == {"chapter_rationale": "Malformed candidate."}


def test_normalize_confidence_scale_repairs_only_unambiguous_fraction_batch() -> None:
    evaluations: list[object] = [
        {"confidence_score": 0.72},
        {"confidence_score": 0.4},
        {"confidence_score": 0},
    ]
    candidate: dict[str, object] = {"batch_notes": ["Existing note."]}

    _normalize_confidence_scale(evaluations, candidate=candidate)

    assert [item["confidence_score"] for item in evaluations] == [72.0, 40.0, 0.0]
    assert "0-1 scale to 0-100" in candidate["batch_notes"][-1]

    mixed: list[object] = [{"confidence_score": 0.8}, {"confidence_score": 65}]
    _normalize_confidence_scale(mixed, candidate={})
    assert [item["confidence_score"] for item in mixed] == [0.8, 65]

    all_zero: list[object] = [{"confidence_score": 0}, {"confidence_score": 0}]
    all_zero_candidate: dict[str, object] = {}
    _normalize_confidence_scale(all_zero, candidate=all_zero_candidate)
    assert [item["confidence_score"] for item in all_zero] == [0, 0]
    assert all_zero_candidate == {}


def test_normalize_calibration_references_repairs_only_unique_ruler_year_suffix() -> None:
    available = {
        "dossier:first:2023:USA:15811",
        "dossier:second:2023:MEX:15802",
    }
    evaluation = {
        "calibrated_against": [
            "dossier:stale:2023:USA:15811",
            "dossier:second:2023:MEX:15802",
            "dossier:unknown:2023:XXX:99999",
        ]
    }

    _normalize_calibration_references(
        evaluation,
        available_dossier_keys=available,
    )

    assert evaluation["calibrated_against"] == [
        "dossier:first:2023:USA:15811",
        "dossier:second:2023:MEX:15802",
        "dossier:unknown:2023:XXX:99999",
    ]


def test_chapter_judge_executes_two_dossiers_and_persists_scores_atomically(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'judge.sqlite'}"
    init_database(database_url)
    engine = create_engine(database_url)
    project = tmp_path / "project"
    project.mkdir()
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
                    "source_observation_ids": [
                        "vdem:AAA:2020:electoral_democracy"
                    ],
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

    monkeypatch.setattr(
        "leaders_db.research.chapter_judge_worker._run_codex", fake_run_codex
    )
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
        rows = conn.execute(
            text(
                "SELECT iso3, ruler_year_id, score_1_to_10, method_version, job_key, "
                "judgment_json FROM chapter_scores ORDER BY ruler_year_id"
            )
        ).mappings().all()
    assert [(row["iso3"], row["score_1_to_10"]) for row in rows] == [
        ("AAA", 4.0),
        ("AAA", 7.0),
    ]
    assert {row["method_version"] for row in rows} == {"chapter_4b_v1"}
    assert {row["job_key"] for row in rows} == {judge_key}
    assert all(json.loads(row["judgment_json"])["chapter_rationale"] for row in rows)
    assert all(
        json.loads(row["judgment_json"])["contextual_local_evidence"][0][
            "local_evidence_id"
        ]
        == "LF001"
        for row in rows
    )
    assert json.loads(rows[0]["judgment_json"])["chapter_specific"] == [
        {"field": "trajectory", "value": "Stable fixture trajectory."}
    ]


def test_chapter_score_persistence_rejects_expired_lease_without_partial_rows(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'expired.sqlite'}"
    init_database(database_url)
    engine = create_engine(database_url)
    now = datetime(2020, 1, 1, tzinfo=UTC)
    create_jobs(
        engine,
        (
            ResearchJobSpec(
                job_key="chapter-judge:expired:2020:4B",
                run_key="expired",
                job_type="question_judge",
                target_year=2020,
                question_id="4B",
                provider_profile="fixture",
                provider="openai",
                model="fixture",
                input_payload={
                    "chapter_id": "4B",
                    "rubric_version": "chapter_4b_v1",
                    "dossier_job_keys": ["dossier:fixture"],
                },
            ),
        ),
    )
    judge = claim_next_job(
        engine,
        worker_id="judge",
        lease_seconds=1,
        job_type="question_judge",
        now=now,
    )
    assert judge is not None
    batch = _batch_for_store(job_key=judge["job_key"])

    with pytest.raises(ValueError, match="scope differs"):
        persist_chapter_batch_and_complete(
            engine,
            batch=batch.model_copy(update={"target_year": 2021}),
            job_id=int(judge["id"]),
            worker_id="judge",
            lease_token=str(judge["lease_token"]),
            result_path=tmp_path / "wrong-scope.json",
            now=now,
        )
    with pytest.raises(ValueError, match="scope differs"):
        persist_chapter_batch_and_complete(
            engine,
            batch=batch.model_copy(update={"rubric_version": "chapter_4b_untrusted"}),
            job_id=int(judge["id"]),
            worker_id="judge",
            lease_token=str(judge["lease_token"]),
            result_path=tmp_path / "wrong-rubric.json",
            now=now,
        )

    with pytest.raises(ValueError, match="stale, expired"):
        persist_chapter_batch_and_complete(
            engine,
            batch=batch,
            job_id=int(judge["id"]),
            worker_id="judge",
            lease_token=str(judge["lease_token"]),
            result_path=tmp_path / "result.json",
            now=now + timedelta(seconds=2),
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM chapter_scores")).scalar_one() == 0


def test_prepare_batch_rejects_self_only_calibration_and_discovery_only_evidence(
    tmp_path: Path,
) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_jobs = [
        _fixture_dossier_job(index=index, iso3=iso3, methodology_ids=methodology_ids)
        for index, iso3 in enumerate(("AAA", "BBB"), start=1)
    ]
    dossiers = tuple(
        (
            tmp_path / f"dossier-{index}.json",
            RulerEvidenceDossier.model_validate(
                _dossier_payload(job, methodology_ids=methodology_ids)
            ),
        )
        for index, job in enumerate(dossier_jobs, start=1)
    )
    judge = _fixture_judge_job(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        methodology_ids=methodology_ids,
    )
    candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    candidate["evaluations"][0]["calibrated_against"] = [dossier_jobs[0]["job_key"]]

    with pytest.raises(ValueError, match="another ruler"):
        _prepare_batch(
            candidate,
            job=judge,
            dossiers=dossiers,
            projections=_projections(dossiers, chapter_id="4B"),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )

    discovery_payload = _dossier_payload(dossier_jobs[0], methodology_ids=methodology_ids)
    discovery_payload["evidence"][0]["final_evidence_use"] = "discovery_only"
    discovery_dossier = RulerEvidenceDossier.model_validate(discovery_payload)
    single_job = _fixture_judge_job(
        dossier_job_keys=[str(dossier_jobs[0]["job_key"])],
        methodology_ids=methodology_ids,
    )
    single_candidate = {
        "evaluations": [
            _evaluation(
                job_key=str(dossier_jobs[0]["job_key"]), iso3="AAA", score=5
            )
        ],
        "batch_notes": [],
        "run_profile": {"usage": _unknown_usage()},
    }
    with pytest.raises(ValueError, match="discovery-only"):
        _prepare_batch(
            single_candidate,
            job=single_job,
            dossiers=((tmp_path / "discovery.json", discovery_dossier),),
            projections=_projections(
                ((tmp_path / "discovery.json", discovery_dossier),), chapter_id="4B"
            ),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )


def test_prepare_batch_accepts_singleton_no_peer_calibration_sentinel(
    tmp_path: Path,
) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_job = _fixture_dossier_job(
        index=1, iso3="AAA", methodology_ids=methodology_ids
    )
    dossier = RulerEvidenceDossier.model_validate(
        _dossier_payload(dossier_job, methodology_ids=methodology_ids)
    )
    candidate = {
        "evaluations": [
            _evaluation(job_key=str(dossier_job["job_key"]), iso3="AAA", score=5)
        ],
        "batch_notes": [],
        "run_profile": {"usage": _unknown_usage()},
    }
    candidate["evaluations"][0]["calibrated_against"] = [
        "no_other_available_dossier_in_manifest"
    ]

    batch = _prepare_batch(
        candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(dossier_job["job_key"])],
            methodology_ids=methodology_ids,
        ),
        dossiers=((tmp_path / "singleton.json", dossier),),
        projections=_projections(
            ((tmp_path / "singleton.json", dossier),), chapter_id="4B"
        ),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert batch.evaluations[0].calibrated_against == ()


def test_prepare_batch_deduplicates_repeated_dossier_evaluation(tmp_path: Path) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_jobs = [
        _fixture_dossier_job(index=index, iso3=iso3, methodology_ids=methodology_ids)
        for index, iso3 in enumerate(("AAA", "BBB"), start=1)
    ]
    dossiers = tuple(
        (
            tmp_path / f"dossier-{index}.json",
            RulerEvidenceDossier.model_validate(
                _dossier_payload(job, methodology_ids=methodology_ids)
            ),
        )
        for index, job in enumerate(dossier_jobs, start=1)
    )
    candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    candidate["evaluations"].append(
        json.loads(json.dumps(candidate["evaluations"][0]))
    )

    batch = _prepare_batch(
        candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
            methodology_ids=methodology_ids,
        ),
        dossiers=dossiers,
        projections=_projections(dossiers, chapter_id="4B"),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert len(batch.evaluations) == 2

    null_duplicate_candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    first = null_duplicate_candidate["evaluations"][0]
    first["score_1_to_10"] = None
    first["insufficient_evidence_reason"] = "The admissible record is incomplete."
    first["plausible_score_range"] = {"lower": 1, "upper": 10}
    duplicate_null = json.loads(json.dumps(first))
    duplicate_null["insufficient_evidence_reason"] = (
        "The projection contains only contextual fragments."
    )
    null_duplicate_candidate["evaluations"].append(duplicate_null)

    batch = _prepare_batch(
        null_duplicate_candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
            methodology_ids=methodology_ids,
        ),
        dossiers=dossiers,
        projections=_projections(dossiers, chapter_id="4B"),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert len(batch.evaluations) == 2
    assert "contextual fragments" in batch.evaluations[0].insufficient_evidence_reason

    conflicting = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    duplicate = json.loads(json.dumps(conflicting["evaluations"][0]))
    duplicate["score_1_to_10"] = 2
    conflicting["evaluations"].append(duplicate)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        _prepare_batch(
            conflicting,
            job=_fixture_judge_job(
                dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
                methodology_ids=methodology_ids,
            ),
            dossiers=dossiers,
            projections=_projections(dossiers, chapter_id="4B"),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )

    placeholder_candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    placeholder = json.loads(json.dumps(placeholder_candidate["evaluations"][0]))
    placeholder["score_1_to_10"] = None
    placeholder["insufficient_evidence_reason"] = (
        "Duplicate placeholder not intended for processing."
    )
    placeholder_candidate["evaluations"].append(placeholder)

    batch = _prepare_batch(
        placeholder_candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
            methodology_ids=methodology_ids,
        ),
        dossiers=dossiers,
        projections=_projections(dossiers, chapter_id="4B"),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert len(batch.evaluations) == 2


def test_bias_assessment_drops_out_of_projection_references() -> None:
    evaluation = {
        "bias_assessment": {
            "material_biases": [
                {
                    "bias": "Reporting visibility",
                    "supporting_evidence_ids": ["E001", "E999"],
                    "likely_direction": "uncertain",
                    "interpretation_effect": "Confidence only.",
                }
            ]
        }
    }

    _ensure_bias_assessment(evaluation, valid_evidence_ids={"E001"})

    assert evaluation["bias_assessment"]["material_biases"][0][
        "supporting_evidence_ids"
    ] == ["E001"]

    missing_assessment: dict[str, object] = {}
    _ensure_bias_assessment(missing_assessment, valid_evidence_ids={"E001"})
    assert missing_assessment["bias_assessment"]["report_volume_not_used_as_severity"] is True
    assert missing_assessment["bias_assessment"]["no_blanket_regime_correction"] is True


def test_bias_assessment_remains_explicit_when_projection_has_no_evidence() -> None:
    evaluation = {}

    _ensure_bias_assessment(evaluation, valid_evidence_ids=set())

    assert evaluation["bias_assessment"]["material_biases"] == []
    assert evaluation["bias_assessment"]["report_volume_not_used_as_severity"] is True
    assert evaluation["bias_assessment"]["no_blanket_regime_correction"] is True


def test_prepare_batch_rejects_all_null_multi_ruler_result(tmp_path: Path) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_jobs = [
        _fixture_dossier_job(index=index, iso3=iso3, methodology_ids=methodology_ids)
        for index, iso3 in enumerate(("AAA", "BBB"), start=1)
    ]
    dossiers = tuple(
        (
            tmp_path / f"dossier-{index}.json",
            RulerEvidenceDossier.model_validate(
                _dossier_payload(job, methodology_ids=methodology_ids)
            ),
        )
        for index, job in enumerate(dossier_jobs, start=1)
    )
    dossier_keys = [str(job["job_key"]) for job in dossier_jobs]
    candidate = _judge_candidate(dossier_job_keys=dossier_keys, iso3s=("AAA", "BBB"))
    for evaluation in candidate["evaluations"]:
        evaluation["score_1_to_10"] = None
        evaluation["insufficient_evidence_reason"] = "Local inputs were inaccessible."
        evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}

    with pytest.raises(ValueError, match="all-null comparative batch"):
        _prepare_batch(
            candidate,
            job=_fixture_judge_job(
                dossier_job_keys=dossier_keys, methodology_ids=methodology_ids
            ),
            dossiers=dossiers,
            projections=_projections(dossiers, chapter_id="4B"),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )

def _projections(
    dossiers: tuple[tuple[Path, RulerEvidenceDossier], ...], *, chapter_id: str
) -> tuple:
    return tuple(
        (
            path.with_suffix(".projection.json"),
            build_ruler_chapter_projection(
                dossier,
                chapter_id=chapter_id,
                source_dossier_path=Path(path.name),
                source_dossier_sha256="a" * 64,
            ),
        )
        for path, dossier in dossiers
    )


def test_worker_cannot_fall_back_when_approved_corpus_is_required(
    tmp_path: Path,
) -> None:
    job = _fixture_dossier_job(
        index=1,
        iso3="TST",
        methodology_ids=tuple(f"4B.{i}" for i in range(1, 11)),
    )
    dossier_path = tmp_path / "dossier.json"
    dossier = RulerEvidenceDossier.model_validate(
        _dossier_payload(job, methodology_ids=tuple(f"4B.{i}" for i in range(1, 11)))
    )
    dossier_path.write_text(dossier.model_dump_json(), encoding="utf-8")
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()

    with pytest.raises(ValueError, match="approved corpus package missing"):
        _write_chapter_projections(
            ((dossier_path, dossier),),
            chapter_id="4B",
            attempt_dir=attempt_dir,
            project_root=tmp_path,
            require_approved_corpus=True,
        )


def test_worker_rejects_approved_manifest_changed_after_planning(tmp_path: Path) -> None:
    methodology_ids = tuple(f"4B.{i}" for i in range(1, 11))
    job = _fixture_dossier_job(index=1, iso3="TST", methodology_ids=methodology_ids)
    dossier_path = tmp_path / "dossier.json"
    dossier = RulerEvidenceDossier.model_validate(
        _dossier_payload(job, methodology_ids=methodology_ids)
    )
    dossier_path.write_text(dossier.model_dump_json(), encoding="utf-8")
    manifest_path = tmp_path / "approved.json"
    manifest_path.write_text("planned", encoding="utf-8")
    planned_hash = sha256(manifest_path.read_bytes()).hexdigest()
    manifest_path.write_text("changed", encoding="utf-8")
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()

    with pytest.raises(ValueError, match="changed after planning"):
        _write_chapter_projections(
            ((dossier_path, dossier),),
            chapter_id="4B",
            attempt_dir=attempt_dir,
            project_root=tmp_path,
            approved_packages={
                dossier.job_key: {
                    "path": str(manifest_path),
                    "sha256": planned_hash,
                }
            },
            require_approved_corpus=True,
        )


def test_previous_policy_approved_chapter_result_is_reusable(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    prior = job_dir / "attempts/001-old"
    current = job_dir / "attempts/002-current"
    prior.mkdir(parents=True)
    current.mkdir(parents=True)
    payload = {"evaluations": [{"dossier_job_key": "dossier:test"}]}
    (prior / "chapter-judgment.orphaned.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    (prior / "judge-complete.marker").write_text("complete\n", encoding="utf-8")

    assert _find_previous_chapter_candidate(job_dir, attempt_dir=current) == payload


def _dossier_payload(
    job: dict[str, object], *, methodology_ids: tuple[str, ...]
) -> dict[str, object]:
    evidence = {
        "evidence_id": "E001",
        "claim": "A cited political-freedom fact.",
        "url": "https://example.test/source",
        "title": "Source",
        "publisher": "Publisher",
        "publication_date": "2020-01-01",
        "excerpt": "A relevant excerpt.",
        "source_type": "official",
        "source_confidence": "medium",
        "source_confidence_reason": "Dated primary record.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target_year",
        "ruler_attribution": "Direct ruler-period action.",
        "contrary_evidence": [],
    }
    return {
        "schema_version": "ruler_evidence_dossier_v2",
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "iso3": job["iso3"],
        "country_name": job["country_name"],
        "ruler_id": job["ruler_id"],
        "ruler_year_id": job["input"]["ruler_year_id"],
        "ruler_name": job["ruler_name"],
        "period_start_year": 2020,
        "period_end_year": 2020,
        "methodology_ids": list(methodology_ids),
        "evidence": [evidence],
        "mappings": [
            {
                "evidence_id": "E001",
                "methodology_id": methodology_id,
                "relation": "context",
                "relevance": "Relevant to the chapter.",
            }
            for methodology_id in methodology_ids
        ],
        "coverage": [
            {
                "methodology_id": methodology_id,
                "status": "partially_covered",
                "evidence_ids": ["E001"],
                "reason": "Fixture evidence.",
            }
            for methodology_id in methodology_ids
        ],
        "unresolved_gaps": [],
        "completed_queries": [],
        "normalization_warnings": [],
        "local_priors": [
            {
                "methodology_id": methodology_id,
                "status": "evidence_found",
                "summary": "Fixture prior.",
                "artifact_path": "tmp/prior.json",
                "artifact_sha256": "0" * 64,
            }
            for methodology_id in methodology_ids
        ],
        "evidence_environment": _evidence_environment(),
        "run_profile": {
            "provider_profile": "fixture",
            "provider": "openai",
            "model": "gpt-fixture",
            "local_evidence_calls": [],
            "searches_attempted": [],
            "sources_visited": [],
            "discovery_search_id": "fixture",
            "source_mix_note": "Fixture source mix.",
            "usage": _unknown_usage(),
        },
    }


def _fixture_dossier_job(
    *, index: int, iso3: str, methodology_ids: tuple[str, ...]
) -> dict[str, object]:
    return {
        "job_key": f"dossier:fixture:2020:{iso3}:{index}",
        "run_key": "fixture-batch",
        "iso3": iso3,
        "country_name": f"Country {iso3}",
        "ruler_id": str(index),
        "ruler_name": f"Ruler {index}",
        "period_start_year": 2020,
        "period_end_year": 2020,
        "input": {
            "ruler_year_id": 100 + index,
            "question_ids": list(methodology_ids),
        },
    }


def _fixture_judge_job(
    *, dossier_job_keys: list[str], methodology_ids: tuple[str, ...]
) -> dict[str, object]:
    return {
        "job_key": "chapter-judge:fixture-batch:2020:4B",
        "run_key": "fixture-batch",
        "job_type": "question_judge",
        "status": "claimed",
        "target_year": 2020,
        "provider_profile": "fixture",
        "provider": "openai",
        "model": "gpt-fixture",
        "input": {
            "chapter_id": "4B",
            "rubric_version": "chapter_4b_v1",
            "methodology_ids": list(methodology_ids),
            "dossier_job_keys": dossier_job_keys,
            "unavailable_dossiers": [],
        },
    }


def _judge_candidate(
    *, dossier_job_keys: list[str], iso3s: tuple[str, ...]
) -> dict[str, object]:
    evaluations = [
            _evaluation(job_key=job_key, iso3=iso3, score=4.0 + index * 3)
            for index, (job_key, iso3) in enumerate(
                zip(dossier_job_keys, iso3s, strict=True)
            )
        ]
    for index, evaluation in enumerate(evaluations):
        evaluation["calibrated_against"] = [dossier_job_keys[1 - index]]
    return {
        "evaluations": evaluations,
        "batch_notes": ["Compared the two fixture rulers using common anchors."],
        "run_profile": {"usage": _unknown_usage()},
    }


def _evaluation(*, job_key: str, iso3: str, score: float) -> dict[str, object]:
    return {
        "dossier_job_key": job_key,
        "iso3": iso3,
        "ruler_id": "model-value-overwritten",
        "ruler_year_id": -1,
        "ruler_name": "model-value-overwritten",
        "period_start_year": 2020,
        "period_end_year": 2020,
        "chapter_id": "4B",
        "rubric_version": "chapter_4b_v1",
        "calibration_batch_id": "batch",
        "calibrated_against": [key for key in (job_key,)],
        "score_1_to_10": score,
        "insufficient_evidence_reason": None,
        "confidence_score": 65,
        "plausible_score_range": {"lower": score - 1, "upper": score + 1},
        "decisive_positive_evidence": [
            {"evidence_id": "E001", "explanation": "Positive fixture evidence."}
        ],
        "decisive_negative_evidence": [],
        "decisive_local_evidence": [],
        "contextual_local_evidence": [],
        "inherited_baseline_and_constraints": "Inherited fixture conditions.",
        "ruler_attribution": "Attributable within the fixture period.",
        "supported_lenses": ["4B.1"],
        "missing_or_weak_lenses": ["4B.2"],
        "contrary_evidence": [],
        "source_mix": "One fixture primary source.",
        "structured_prior_summary": "Fixture prior summary.",
        "bias_assessment": _bias_assessment(),
        "chapter_rationale": "Fits the selected comparative anchor.",
        "lower_anchor_rejected": "Too harsh for the documented record.",
        "higher_anchor_rejected": "Too generous given the evidence gap.",
        "manual_review_required": False,
        "manual_review_reason_type": None,
        "manual_review_reason": None,
        "chapter_specific": [
            {"field": "trajectory", "value": "Stable fixture trajectory."}
        ],
    }


def _batch_for_store(*, job_key: str):
    from leaders_db.research.chapter_judge_models import ChapterJudgmentBatch

    payload = {
        "schema_version": "ruler_chapter_judgment_v1",
        "job_key": job_key,
        "run_key": "expired",
        "chapter_id": "4B",
        "target_year": 2020,
        "rubric_version": "chapter_4b_v1",
        "calibration_batch_id": job_key,
        "evaluations": [_evaluation(job_key="dossier:fixture", iso3="AAA", score=5)],
        "unavailable_dossiers": [],
        "batch_notes": [],
        "run_profile": {
            "provider_profile": "fixture",
            "provider": "openai",
            "model": "fixture",
            "dossier_count": 1,
            "unavailable_dossier_count": 0,
            "usage": _unknown_usage(),
        },
    }
    payload["evaluations"][0]["calibration_batch_id"] = job_key
    return ChapterJudgmentBatch.model_validate(payload)


def _unknown_usage() -> dict[str, str]:
    return {
        "input_tokens": "unknown_not_exposed_by_tool",
        "output_tokens": "unknown_not_exposed_by_tool",
        "total_tokens": "unknown_not_exposed_by_tool",
        "estimated_cost_usd": "unknown_not_exposed_by_tool",
    }


def _assert_tolerant_bias_persistence(completed: dict[str, object], batch: object) -> None:
    assert completed["status"] == "completed"
    assert batch.run_profile.usage.total_tokens == 1500
    assert all(item.confidence_score == 50 for item in batch.evaluations)
    assert all(
        item.bias_assessment.report_volume_not_used_as_severity
        for item in batch.evaluations
    )


def _evidence_environment() -> dict[str, object]:
    return {
        "criticism_possible": "Criticism was possible but the fixture record is thin.",
        "censorship_and_self_censorship": "No censorship conclusion beyond E001.",
        "safe_reporting_channels": "Formal reporting channels existed in the fixture.",
        "official_statistics_reliability": "No statistics are used in this fixture.",
        "languages_and_archives_searched": ["English fixture archive"],
        "source_concentration": "The record is concentrated in one official source.",
        "duplicate_event_risk": "Only one underlying fact is present.",
        "complaint_volume_interpretation": "Volume is not treated as conduct severity.",
        "relevant_denominators": "Population and exposure are not measured here.",
        "inherited_conditions_shocks_and_authority": "Authority is direct in the fixture.",
        "chapter_specific_biases": ["Official-source concentration"],
        "supporting_evidence_ids": ["E001"],
    }


def _bias_assessment() -> dict[str, object]:
    return {
        "material_biases": [
            {
                "bias": "Official-source concentration",
                "supporting_evidence_ids": ["E001"],
                "likely_direction": "favors_ruler",
                "interpretation_effect": "The official claim receives limited weight.",
            }
        ],
        "confidence_and_range_effect": "Confidence is lower and the range is wider.",
        "remaining_uncertainty": "Independent corroboration remains absent.",
        "report_volume_not_used_as_severity": True,
        "no_blanket_regime_correction": True,
    }
