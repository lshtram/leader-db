import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest
import yaml

from leaders_db.research.question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
)
from leaders_db.research.question_packet_expansion import (
    expand_question_evidence_package,
    load_expanded_question_evidence_package,
    load_material_defect_return,
    load_question_packet_expansion,
)

ROOT = Path.cwd()
RUN = ROOT / "research/runs/netanyahu-2023-cost-opt-step03-question-packets-v1/4B"
JUDGE_PACKAGE = (
    ROOT / "research/runs/2023-five-ruler-flow-test-v2/corpus/ISR/corpus-judge-package.json"
)
SELECTION = (
    ROOT / "research/runs/2023-five-ruler-flow-test-v2/corpus/ISR/selected-chapter-manifest.json"
)


def test_expansion_promotes_reviewed_candidates_to_exact_evidence() -> None:
    package = ChapterQuestionEvidencePackage.model_validate_json(
        (RUN / "question-evidence-package.json").read_text()
    )
    additions = load_question_packet_expansion(
        project_root=ROOT,
        config_path=ROOT / "configs/question-packet-expansions.yaml",
        chapter_id="4B",
    )

    expanded = expand_question_evidence_package(
        package=package,
        judge_package_path=JUDGE_PACKAGE,
        additions_by_question=additions,
    )

    for packet in expanded.packets:
        required = set(packet.coverage.required_evidence_ids)
        assert set(additions[packet.question_id]).issubset(required)
        assert set(additions[packet.question_id]).issubset(
            packet.source_routed_priority_evidence_ids
        )
        assert not required.intersection(packet.coverage.reopenable_evidence_ids)


def test_expansion_rejects_non_candidate_id() -> None:
    package = ChapterQuestionEvidencePackage.model_validate_json(
        (RUN / "question-evidence-package.json").read_text()
    )

    with pytest.raises(ValueError, match="unique question candidates"):
        expand_question_evidence_package(
            package=package,
            judge_package_path=JUDGE_PACKAGE,
            additions_by_question={"4B.1": ("UNKNOWN",)},
        )


def test_expansion_rejects_wrong_source_hash() -> None:
    package = ChapterQuestionEvidencePackage.model_validate_json(
        (RUN / "question-evidence-package.json").read_text()
    ).model_copy(update={"source_package_sha256": "0" * 64})

    with pytest.raises(ValueError, match="does not match"):
        expand_question_evidence_package(
            package=package,
            judge_package_path=JUDGE_PACKAGE,
            additions_by_question={},
        )


def test_expansion_rejects_duplicate_ledger_id(tmp_path: Path) -> None:
    package = ChapterQuestionEvidencePackage.model_validate_json(
        (RUN / "question-evidence-package.json").read_text()
    )
    payload = json.loads(JUDGE_PACKAGE.read_text())
    payload["evidence"].append(payload["evidence"][0])
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps(payload))
    package = package.model_copy(
        update={"source_package_sha256": sha256(judge.read_bytes()).hexdigest()}
    )

    with pytest.raises(ValueError, match="duplicate evidence"):
        expand_question_evidence_package(
            package=package, judge_package_path=judge, additions_by_question={}
        )


def test_expanded_package_trusted_roundtrip_and_tamper(tmp_path: Path) -> None:
    expanded_path = (
        ROOT
        / "research/runs/netanyahu-2023-cost-opt-step03-question-packets-v2"
        / "4B/question-evidence-package.json"
    )
    arguments = {
        "project_root": ROOT,
        "base_package_path": RUN / "question-evidence-package.json",
        "expanded_package_path": expanded_path,
        "judge_package_path": JUDGE_PACKAGE,
        "selection_manifest_path": SELECTION,
        "config_path": ROOT / "configs/question-packet-expansions.yaml",
    }
    assert load_expanded_question_evidence_package(**arguments).chapter_id == "4B"

    tampered = tmp_path / "expanded.json"
    payload = json.loads(expanded_path.read_text())
    payload["packets"][0]["priority_evidence"][0]["fact_summary"] = "altered"
    tampered.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_expanded_question_evidence_package(**{**arguments, "expanded_package_path": tampered})

    base = tmp_path / "base.json"
    base_payload = json.loads(arguments["base_package_path"].read_text())
    base_payload["packets"][0]["question"] = "altered question"
    base.write_text(json.dumps(base_payload))
    with pytest.raises(ValueError, match="differs from its approved sources"):
        load_expanded_question_evidence_package(**{**arguments, "base_package_path": base})

    config = yaml.safe_load(arguments["config_path"].read_text())
    config["chapters"]["4B"]["4B.1"][0] = "BATCH-0007-E002"
    config_path = tmp_path / "expansion.yaml"
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="source review recommendation"):
        load_expanded_question_evidence_package(**{**arguments, "config_path": config_path})

    copied_root = tmp_path / "copied"
    review_relative = "netanyahu-2023-cost-opt-step03-chapter-v1/4B/review-v3"
    copied_review = copied_root / "research/runs" / review_relative
    shutil.copytree(ROOT / "research/runs" / review_relative, copied_review)
    child = copied_review / "questions/4B.1/blind-review-manifest.json"
    child.write_text(child.read_text() + " ")
    with pytest.raises(ValueError, match="child manifest changed"):
        load_question_packet_expansion(
            project_root=copied_root,
            config_path=arguments["config_path"],
            chapter_id="4B",
        )


def test_material_defect_return_accepts_hash_bound_partial_failed_review(
    tmp_path: Path,
) -> None:
    package = ChapterQuestionEvidencePackage.model_validate_json(
        (RUN / "question-evidence-package.json").read_text()
    )
    packet = package.packets[0]
    evidence_ids = tuple(
        item.evidence_id for item in packet.candidate_index if item.evidence_id not in {
            evidence.evidence_id for evidence in packet.priority_evidence
        }
    )[:2]
    source_run = tmp_path / "research/runs/failed"
    source_run.mkdir(parents=True)
    preflight_path = source_run / "preflight-manifest.json"
    preflight_path.write_text(
        json.dumps({"release_id": "failed-v1", "material_defect_return_count": 0})
    )
    review_dir = source_run / "question-review/4B/questions/4B.1"
    review_dir.mkdir(parents=True)
    review = {"strongest_omitted_evidence_ids": list(evidence_ids)}
    output = review_dir / "output.json"
    output.write_text(json.dumps(review))
    packet_payload = packet.model_dump(mode="json")
    manifest = {
        "question_id": "4B.1",
        "quality_gate": "fail",
        "packet_sha256": _payload_hash(packet_payload),
        "review_sha256": _payload_hash(review),
    }
    manifest_path = review_dir / "blind-review-manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    config = {
        "schema_version": "question_material_defect_return_v1",
        "source_run": "failed",
        "source_release_id": "failed-v1",
        "source_preflight_sha256": sha256(preflight_path.read_bytes()).hexdigest(),
        "prior_return_count": 0,
        "return_ordinal": 1,
        "user_authorized": True,
        "chapters": {
            "4B": {
                "4B.1": {
                    "review_manifest": (
                        "question-review/4B/questions/4B.1/blind-review-manifest.json"
                    ),
                    "review_manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
                    "evidence_ids": list(evidence_ids),
                }
            }
        },
    }
    config_path = tmp_path / "return.yaml"
    config_path.write_text(yaml.safe_dump(config))

    receipt = load_material_defect_return(
        project_root=tmp_path,
        config_path=config_path,
        active_chapters=("4B",),
    )
    additions = receipt.additions_for(package)

    assert additions == {"4B.1": evidence_ids}
    expanded = expand_question_evidence_package(
        package=package,
        judge_package_path=JUDGE_PACKAGE,
        additions_by_question=additions,
    )
    expanded_packet = expanded.packets[0]
    assert set(evidence_ids).issubset(expanded_packet.coverage.required_evidence_ids)
    receipt.verify_unchanged()

    preflight_bytes = preflight_path.read_bytes()
    preflight_path.write_text(json.dumps({"release_id": "failed-v1"}))
    with pytest.raises(ValueError, match="source preflight changed"):
        load_material_defect_return(
            project_root=tmp_path,
            config_path=config_path,
            active_chapters=("4B",),
        )
    preflight_path.write_bytes(preflight_bytes)

    manifest_bytes = manifest_path.read_bytes()
    manifest_path.write_text(json.dumps({**manifest, "quality_gate": "pass"}))
    with pytest.raises(ValueError, match="review manifest changed"):
        load_material_defect_return(
            project_root=tmp_path,
            config_path=config_path,
            active_chapters=("4B",),
        )
    manifest_path.write_bytes(manifest_bytes)

    output.write_text(json.dumps({"strongest_omitted_evidence_ids": []}))
    with pytest.raises(ValueError, match="changed during preflight"):
        receipt.verify_unchanged()


def test_material_defect_return_rejects_tampering_and_missing_authorization(
    tmp_path: Path,
) -> None:
    review_dir = tmp_path / "research/runs/failed/review/4B.1"
    review_dir.mkdir(parents=True)
    output = {"strongest_omitted_evidence_ids": ["BATCH-0002-E020"]}
    (review_dir / "output.json").write_text(json.dumps(output))
    manifest = review_dir / "blind-review-manifest.json"
    manifest.write_text(json.dumps({"question_id": "4B.1", "quality_gate": "pass"}))
    config = {
        "schema_version": "question_material_defect_return_v1",
        "source_run": "failed",
        "source_release_id": "failed-v1",
        "source_preflight_sha256": "a" * 64,
        "prior_return_count": 0,
        "return_ordinal": 1,
        "user_authorized": False,
        "chapters": {
            "4B": {
                "4B.1": {
                    "review_manifest": "4B.1/blind-review-manifest.json",
                    "review_manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
                    "evidence_ids": ["BATCH-0002-E020"],
                }
            }
        },
    }
    config_path = tmp_path / "return.yaml"
    config_path.write_text(yaml.safe_dump(config))

    with pytest.raises(ValueError, match="user_authorized"):
        load_material_defect_return(
            project_root=tmp_path,
            config_path=config_path,
            active_chapters=("4B",),
        )


def test_material_defect_return_rejects_external_config_and_irrelevant_chapter(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.yaml"
    external.write_text("invalid: true\n")
    with pytest.raises(ValueError, match="outside the project"):
        load_material_defect_return(
            project_root=project,
            config_path=external,
            active_chapters=("4B",),
        )

    config = project / "return.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "question_material_defect_return_v1",
                "source_run": "failed",
                "source_release_id": "failed-v1",
                "source_preflight_sha256": "a" * 64,
                "prior_return_count": 0,
                "return_ordinal": 1,
                "user_authorized": True,
                "chapters": {
                    "9B": {
                        "9B.1": {
                            "review_manifest": "review.json",
                            "review_manifest_sha256": "a" * 64,
                            "evidence_ids": ["E1"],
                        }
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="outside the active run"):
        load_material_defect_return(
            project_root=project,
            config_path=config,
            active_chapters=("4B",),
        )


def test_material_defect_return_rejects_a_second_return_in_lineage(tmp_path: Path) -> None:
    source = tmp_path / "research/runs/returned-v1"
    source.mkdir(parents=True)
    preflight_path = source / "preflight-manifest.json"
    preflight_path.write_text(
        json.dumps({"release_id": "returned-v1", "material_defect_return_count": 1})
    )
    config = tmp_path / "return.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "question_material_defect_return_v1",
                "source_run": "returned-v1",
                "source_release_id": "returned-v1",
                "source_preflight_sha256": sha256(preflight_path.read_bytes()).hexdigest(),
                "prior_return_count": 0,
                "return_ordinal": 1,
                "user_authorized": True,
                "chapters": {
                    "4B": {
                        "4B.1": {
                            "review_manifest": "review.json",
                            "review_manifest_sha256": "a" * 64,
                            "evidence_ids": ["E1"],
                        }
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="source lineage"):
        load_material_defect_return(
            project_root=tmp_path,
            config_path=config,
            active_chapters=("4B",),
        )


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()
