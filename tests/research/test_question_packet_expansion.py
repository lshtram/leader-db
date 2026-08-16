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
        load_expanded_question_evidence_package(
            **{**arguments, "expanded_package_path": tampered}
        )

    base = tmp_path / "base.json"
    base_payload = json.loads(arguments["base_package_path"].read_text())
    base_payload["packets"][0]["question"] = "altered question"
    base.write_text(json.dumps(base_payload))
    with pytest.raises(ValueError, match="differs from its approved sources"):
        load_expanded_question_evidence_package(
            **{**arguments, "base_package_path": base}
        )

    config = yaml.safe_load(arguments["config_path"].read_text())
    config["chapters"]["4B"]["4B.1"][0] = "BATCH-0007-E002"
    config_path = tmp_path / "expansion.yaml"
    config_path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="source review recommendation"):
        load_expanded_question_evidence_package(
            **{**arguments, "config_path": config_path}
        )

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
