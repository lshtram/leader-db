from __future__ import annotations

import pytest
from pydantic import ValidationError

from leaders_db.research.codex_worker import (
    WorkerOutputError,
    _validate_substantive_evidence_yield,
)
from leaders_db.research.dossier_models import (
    DossierEvidence,
    RulerEvidenceDossier,
    codex_dossier_json_schema,
    normalize_dossier_candidate,
)


def test_old_v2_evidence_without_new_audit_fields_remains_readable() -> None:
    evidence = DossierEvidence.model_validate(_evidence())

    assert evidence.source_locator == "unknown_not_recorded"
    assert evidence.canonical_fact_key == "unknown_not_recorded"


@pytest.mark.parametrize("locator", ["locator_missing", "release page", "document index"])
def test_new_final_evidence_rejects_generic_locator(locator: str) -> None:
    payload = _evidence() | {
        "source_locator": locator,
        "canonical_fact_key": "source|locator|claim",
    }

    with pytest.raises(ValidationError, match="precise source locator"):
        DossierEvidence.model_validate(payload)


def test_strict_writer_schema_requires_new_audit_fields() -> None:
    schema = codex_dossier_json_schema()
    evidence_schema = schema["$defs"]["DossierEvidence"]

    assert {"source_locator", "canonical_fact_key"}.issubset(evidence_schema["required"])


@pytest.mark.parametrize(
    "partial",
    [
        {"source_locator": "PDF p. 4"},
        {"canonical_fact_key": "source|p4|claim"},
    ],
)
def test_new_writer_cannot_supply_only_one_audit_field(partial: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match=r"requires a precise|requires a canonical"):
        DossierEvidence.model_validate(_evidence() | partial)


def test_dossier_rejects_duplicate_canonical_fact() -> None:
    first = _evidence() | {
        "source_locator": "PDF p. 4",
        "canonical_fact_key": "source|p4|claim",
    }
    second = first | {"evidence_id": "E002", "canonical_fact_key": "other-key"}

    with pytest.raises(ValidationError, match="duplicate canonical"):
        RulerEvidenceDossier.model_validate(_dossier((first, second)))


def test_normalizer_merges_exact_duplicate_fact_and_rewires_references() -> None:
    first = _evidence() | {
        "source_locator": "PDF p. 4",
        "canonical_fact_key": "source|p4|claim",
    }
    second = first | {
        "evidence_id": "duplicate-id",
        "canonical_fact_key": "other-key",
    }
    payload = _dossier((first, second))
    payload["methodology_ids"] = ["1B.1", "2B.1"]
    payload["mappings"] = [
        {
            "evidence_id": "E001",
            "methodology_id": "1B.1",
            "relation": "context",
            "relevance": "First reference.",
        },
        {
            "evidence_id": "duplicate-id",
            "methodology_id": "2B.1",
            "relation": "supports",
            "relevance": "Same fact, duplicate row.",
        }
    ]
    payload["coverage"][0] |= {
        "status": "covered",
        "evidence_ids": ["E001", "duplicate-id"],
    }
    payload["coverage"].append(
        {
            "methodology_id": "2B.1",
            "status": "covered",
            "evidence_ids": ["duplicate-id"],
            "reason": "Second reference.",
        }
    )
    payload["local_priors"].append(
        {
            "methodology_id": "2B.1",
            "status": "no_evidence_found",
            "summary": "No local evidence.",
            "artifact_path": "fixture.json",
            "artifact_sha256": "b" * 64,
        }
    )

    normalized = normalize_dossier_candidate(payload, methodology_ids=("1B.1", "2B.1"))
    dossier = RulerEvidenceDossier.model_validate(normalized)

    assert [item.evidence_id for item in dossier.evidence] == ["E001"]
    assert {(item.methodology_id, item.relation) for item in dossier.mappings} == {
        ("1B.1", "context"),
        ("2B.1", "supports"),
    }
    assert dossier.coverage[0].evidence_ids == ("E001",)
    assert dossier.coverage[1].evidence_ids == ("E001",)
    assert any("duplicate canonical fact" in item for item in dossier.normalization_warnings)


def test_normalizer_does_not_merge_case_sensitive_url_paths() -> None:
    first = _evidence() | {
        "source_locator": "PDF p. 4",
        "canonical_fact_key": "source-a|p4|claim",
    }
    second = first | {
        "evidence_id": "E002",
        "url": "https://example.test/Report.pdf",
        "canonical_fact_key": "source-b|p4|claim",
    }

    normalized = normalize_dossier_candidate(
        _dossier((first, second)), methodology_ids=("1B.1",)
    )

    assert len(normalized["evidence"]) == 2


def test_normalizer_retains_stronger_duplicate_and_unions_contrary_evidence() -> None:
    first = _evidence() | {
        "source_locator": "PDF p. 4",
        "canonical_fact_key": "source|p4|claim",
        "final_evidence_use": "context",
        "source_confidence": "medium",
        "excerpt": "Short excerpt.",
        "contrary_evidence": ["First caveat."],
    }
    second = first | {
        "evidence_id": "E002",
        "canonical_fact_key": "other-key",
        "final_evidence_use": "final_evidence",
        "source_confidence": "high",
        "excerpt": "Longer and more precise supporting excerpt.",
        "contrary_evidence": ["Second caveat."],
    }

    normalized = normalize_dossier_candidate(
        _dossier((first, second)), methodology_ids=("1B.1",)
    )
    retained = normalized["evidence"][0]

    assert retained["evidence_id"] == "E001"
    assert retained["final_evidence_use"] == "final_evidence"
    assert retained["source_confidence"] == "high"
    assert retained["contrary_evidence"] == ["First caveat.", "Second caveat."]
    assert any(
        "conflicting metadata" in item for item in normalized["normalization_warnings"]
    )


def test_normalizer_drops_unknown_mapping_before_strict_validation() -> None:
    evidence = _evidence() | {
        "source_locator": "PDF p. 4",
        "canonical_fact_key": "source|p4|claim",
    }
    payload = _dossier((evidence,))
    payload["mappings"] = [
        {
            "evidence_id": "undeclared-id",
            "methodology_id": "1B.1",
            "relation": "supports",
            "relevance": "Broken formatter reference.",
        }
    ]
    payload["coverage"][0] |= {
        "status": "covered",
        "evidence_ids": ["E001"],
    }

    normalized = normalize_dossier_candidate(payload, methodology_ids=("1B.1",))
    dossier = RulerEvidenceDossier.model_validate(normalized)

    assert dossier.mappings[0].evidence_id == "E001"
    assert any(
        "unknown evidence or question" in item
        for item in dossier.normalization_warnings
    )


def test_multi_chapter_dossier_cannot_publish_with_zero_evidence() -> None:
    payload = _dossier(())
    payload["methodology_ids"] = ["1B.1", "2B.1"]
    payload["coverage"] = [
        {
            "methodology_id": methodology_id,
            "status": "no_evidence_found",
            "evidence_ids": [],
            "reason": "No evidence found.",
        }
        for methodology_id in payload["methodology_ids"]
    ]
    payload["local_priors"] = [
        {
            "methodology_id": methodology_id,
            "status": "not_available",
            "summary": "No local prior.",
            "artifact_path": "data/none.json",
            "artifact_sha256": "f" * 64,
        }
        for methodology_id in payload["methodology_ids"]
    ]

    dossier = RulerEvidenceDossier.model_validate(payload)

    with pytest.raises(WorkerOutputError, match="cannot publish with zero evidence"):
        _validate_substantive_evidence_yield(dossier)


def test_single_chapter_zero_evidence_remains_publishable() -> None:
    dossier = RulerEvidenceDossier.model_validate(_dossier(()))

    _validate_substantive_evidence_yield(dossier)


def test_multi_chapter_nonzero_evidence_remains_publishable() -> None:
    evidence = _evidence() | {
        "source_locator": "PDF p. 4",
        "canonical_fact_key": "source|p4|claim",
    }
    payload = _dossier((evidence,))
    payload["methodology_ids"] = ["1B.1", "2B.1"]
    payload["coverage"].append(
        {
            "methodology_id": "2B.1",
            "status": "no_evidence_found",
            "evidence_ids": [],
            "reason": "No evidence found.",
        }
    )
    payload["local_priors"].append(
        {
            "methodology_id": "2B.1",
            "status": "not_available",
            "summary": "No local prior.",
            "artifact_path": "data/none.json",
            "artifact_sha256": "f" * 64,
        }
    )
    dossier = RulerEvidenceDossier.model_validate(payload)

    _validate_substantive_evidence_yield(dossier)


def _evidence() -> dict[str, object]:
    return {
        "evidence_id": "E001",
        "claim": "The primary record reports a dated action.",
        "url": "https://example.test/report.pdf",
        "title": "Primary report",
        "publisher": "Example authority",
        "publication_date": "2020-06-01",
        "excerpt": "A short supporting excerpt.",
        "source_type": "official_record",
        "source_confidence": "high",
        "source_confidence_reason": "Primary dated record.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target_year_2020",
        "ruler_attribution": "cabinet/government",
        "contrary_evidence": [],
    }


def _dossier(evidence: tuple[dict[str, object], ...]) -> dict[str, object]:
    return {
        "schema_version": "ruler_evidence_dossier_v2",
        "job_key": "dossier:test",
        "run_key": "test",
        "iso3": "NZL",
        "country_name": "New Zealand",
        "ruler_id": "1",
        "ruler_year_id": 1,
        "ruler_name": "Fixture ruler",
        "period_start_year": 2020,
        "period_end_year": 2020,
        "methodology_ids": ["1B.1"],
        "evidence": list(evidence),
        "mappings": [],
        "coverage": [
            {
                "methodology_id": "1B.1",
                "status": "no_evidence_found",
                "evidence_ids": [],
                "reason": "Fixture coverage.",
            }
        ],
        "local_priors": [
            {
                "methodology_id": "1B.1",
                "status": "no_evidence_found",
                "summary": "No local evidence.",
                "artifact_path": "fixture.json",
                "artifact_sha256": "a" * 64,
            }
        ],
        "run_profile": {
            "provider_profile": "fixture",
            "provider": "openai",
            "model": "fixture",
            "source_mix_note": "Fixture sources.",
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": "unknown_not_exposed_by_tool",
            },
        },
    }
