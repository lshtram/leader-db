import json

import pytest

from leaders_db.research.codex_worker import (
    WorkerOutputError,
    _restore_formatter_ledger_evidence,
    _validate_formatter_ledger_accounting,
)
from leaders_db.research.dossier_models import (
    RulerEvidenceDossier,
    normalize_dossier_candidate,
)


def test_duplicate_manifest_alias_is_satisfied_by_same_normalized_fact() -> None:
    dossier = RulerEvidenceDossier.model_validate(_dossier_payload())
    notebook = "--- RESEARCH LEDGER MANIFEST ---\n\n" + json.dumps(
        {
            "schema_version": "ruler_research_ledger_manifest_v1",
            "entries": [
                _manifest_entry("fact-primary", ["1B.1"]),
                _manifest_entry("fact-alias", ["1B.2"]),
            ],
        }
    )

    _validate_formatter_ledger_accounting(dossier, notebook=notebook)


def test_unrelated_routed_fact_does_not_satisfy_incomplete_final_alias() -> None:
    dossier = RulerEvidenceDossier.model_validate(_dossier_payload())
    notebook = "--- RESEARCH LEDGER MANIFEST ---\n\n" + json.dumps(
        {
            "schema_version": "ruler_research_ledger_manifest_v1",
            "entries": [
                {
                    "canonical_fact_key": "routing-only-alias",
                    "disposition": "final_evidence",
                    "methodology_ids": ["1B.1", "1B.2"],
                }
            ],
        }
    )

    with pytest.raises(WorkerOutputError, match="routing-only-alias"):
        _validate_formatter_ledger_accounting(dossier, notebook=notebook)


def test_incomplete_entry_requires_the_same_canonical_key() -> None:
    dossier = RulerEvidenceDossier.model_validate(_dossier_payload())
    notebook = "--- RESEARCH LEDGER MANIFEST ---\n\n" + json.dumps(
        {
            "schema_version": "ruler_research_ledger_manifest_v1",
            "entries": [
                {
                    "canonical_fact_key": "fact-primary",
                    "disposition": "final_evidence",
                    "methodology_ids": ["1B.1", "1B.2"],
                }
            ],
        }
    )

    _validate_formatter_ledger_accounting(dossier, notebook=notebook)


def test_routing_restore_targets_first_duplicate_canonical_key() -> None:
    payload = _dossier_payload()
    duplicate = dict(payload["evidence"][0])
    duplicate["evidence_id"] = "E002"
    duplicate["claim"] = "A shorter formatter restatement of the policy."
    payload["evidence"].append(duplicate)
    payload["mappings"] = []
    notebook = "--- RESEARCH LEDGER MANIFEST ---\n\n" + json.dumps(
        {
            "schema_version": "ruler_research_ledger_manifest_v1",
            "entries": [_manifest_entry("fact-primary", ["1B.1", "1B.2"])],
        }
    )

    restored = _restore_formatter_ledger_evidence(
        payload,
        existing_candidate=None,
        notebook=notebook,
    )
    normalized = normalize_dossier_candidate(
        restored,
        methodology_ids=("1B.1", "1B.2"),
    )

    retained = next(
        item
        for item in normalized["evidence"]
        if item["canonical_fact_key"] == "fact-primary"
    )
    assert {
        mapping["methodology_id"]
        for mapping in normalized["mappings"]
        if mapping["evidence_id"] == retained["evidence_id"]
    } == {"1B.1", "1B.2"}


def test_routing_restore_skips_canonical_key_row_merged_into_earlier_fact() -> None:
    payload = _dossier_payload()
    earlier_fact = dict(payload["evidence"][0])
    earlier_fact["canonical_fact_key"] = "other-fact"
    merged_target = dict(payload["evidence"][0])
    merged_target["evidence_id"] = "E002"
    surviving_target = dict(payload["evidence"][0])
    surviving_target.update(
        evidence_id="E003",
        claim="A distinct target fact.",
        excerpt="A distinct target fact.",
    )
    payload["evidence"] = [earlier_fact, merged_target, surviving_target]
    payload["mappings"] = []
    notebook = "--- RESEARCH LEDGER MANIFEST ---\n\n" + json.dumps(
        {
            "schema_version": "ruler_research_ledger_manifest_v1",
            "entries": [_manifest_entry("fact-primary", ["1B.1", "1B.2"])],
        }
    )

    restored = _restore_formatter_ledger_evidence(
        payload,
        existing_candidate=None,
        notebook=notebook,
    )
    normalized = normalize_dossier_candidate(
        restored,
        methodology_ids=("1B.1", "1B.2"),
    )

    retained = next(
        item
        for item in normalized["evidence"]
        if item["canonical_fact_key"] == "fact-primary"
    )
    assert retained["claim"] == "A distinct target fact."
    assert {
        mapping["methodology_id"]
        for mapping in normalized["mappings"]
        if mapping["evidence_id"] == retained["evidence_id"]
    } == {"1B.1", "1B.2"}


def _manifest_entry(key: str, methodology_ids: list[str]) -> dict[str, object]:
    return {
        "canonical_fact_key": key,
        "disposition": "final_evidence",
        "url": "https://example.test/report",
        "locator": "page 4",
        "claim": "The report documents the policy.",
        "methodology_ids": methodology_ids,
    }


def _dossier_payload() -> dict[str, object]:
    evidence = {
        "evidence_id": "E001",
        "claim": "The report documents the policy.",
        "url": "https://example.test/report",
        "title": "Report",
        "publisher": "Institute",
        "publication_date": "2023-01-01",
        "excerpt": "The report documents the policy.",
        "source_locator": "page 4",
        "canonical_fact_key": "fact-primary",
        "source_type": "report",
        "source_confidence": "high",
        "source_confidence_reason": "Primary report.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target_period",
        "ruler_attribution": "direct",
        "contrary_evidence": [],
    }
    mappings = [
        {
            "evidence_id": "E001",
            "methodology_id": methodology_id,
            "relation": "supports",
            "relevance": "Direct evidence.",
        }
        for methodology_id in ("1B.1", "1B.2")
    ]
    coverage = [
        {
            "methodology_id": methodology_id,
            "status": "covered",
            "evidence_ids": ["E001"],
            "reason": "Direct evidence.",
        }
        for methodology_id in ("1B.1", "1B.2")
    ]
    local_priors = [
        {
            "methodology_id": methodology_id,
            "status": "available",
            "summary": "Fixture prior.",
            "artifact_path": "fixture.json",
            "artifact_sha256": "0" * 64,
        }
        for methodology_id in ("1B.1", "1B.2")
    ]
    return {
        "schema_version": "ruler_evidence_dossier_v2",
        "job_key": "dossier:test",
        "run_key": "test",
        "iso3": "TST",
        "country_name": "Testland",
        "ruler_id": "ruler-1",
        "ruler_year_id": 1,
        "ruler_name": "Test Ruler",
        "period_start_year": 2023,
        "period_end_year": 2023,
        "methodology_ids": ["1B.1", "1B.2"],
        "evidence": [evidence],
        "mappings": mappings,
        "coverage": coverage,
        "local_priors": local_priors,
        "evidence_environment": {
            "criticism_possible": "Assessed.",
            "censorship_and_self_censorship": "Assessed.",
            "safe_reporting_channels": "Assessed.",
            "official_statistics_reliability": "Assessed.",
            "languages_and_archives_searched": ["English"],
            "source_concentration": "Mixed.",
            "duplicate_event_risk": "Controlled.",
            "complaint_volume_interpretation": "Contextualized.",
            "relevant_denominators": "Recorded.",
            "inherited_conditions_shocks_and_authority": "Recorded.",
            "chapter_specific_biases": ["None identified."],
            "supporting_evidence_ids": ["E001"],
        },
        "run_profile": {
            "provider_profile": "fixture",
            "provider": "fixture",
            "model": "fixture",
            "source_mix_note": "Fixture source mix.",
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
        },
    }
