from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from math import ceil
from pathlib import Path

import pytest

from leaders_db.research.chapter_projection import (
    CONSERVATIVE_BYTES_PER_TOKEN,
    RulerChapterProjection,
    build_ruler_chapter_projection,
    estimate_chapter_projection_batch_context,
)
from leaders_db.research.dossier_models import RulerEvidenceDossier


def test_projection_is_compact_deterministic_and_preserves_provenance(tmp_path: Path) -> None:
    dossier = _dossier()
    source_path = tmp_path / "dossier.json"
    projection = build_ruler_chapter_projection(
        dossier,
        chapter_id="4b",
        source_dossier_path=source_path,
        source_dossier_sha256="a" * 64,
    )

    assert projection.chapter_id == "4B"
    assert projection.methodology_ids == _chapter_ids("4B")
    assert [item.evidence_id for item in projection.evidence] == ["E001", "E003"]
    assert {item.methodology_id for item in projection.mappings} == set(_chapter_ids("4B"))
    assert [item.methodology_id for item in projection.coverage] == list(_chapter_ids("4B"))
    assert [item.methodology_id for item in projection.local_priors] == list(
        _chapter_ids("4B")
    )
    assert projection.unresolved_gaps == ("Attribution remains disputed.",)
    assert projection.source_dossier_path == str(source_path)
    assert projection.source_dossier_sha256 == "a" * 64
    assert projection.source_dossier_schema_version == "ruler_evidence_dossier_v2"
    assert projection.evidence_environment.supporting_evidence_ids == ("E001",)
    assert projection.run_provenance.provider_profile == "researcher"
    assert projection.run_provenance.research_notebook_sha256 == "b" * 64
    estimated_payload = projection.model_dump(
        mode="json", exclude={"estimated_input_tokens"}
    )
    serialized = json.dumps(
        estimated_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert projection.estimated_input_tokens == ceil(len(serialized) / 3)
    assert CONSERVATIVE_BYTES_PER_TOKEN == 3

    reversed_payload = dossier.model_dump(mode="json")
    reversed_payload["evidence"].reverse()
    reversed_payload["mappings"].reverse()
    reversed_dossier = RulerEvidenceDossier.model_validate(reversed_payload)
    repeated = build_ruler_chapter_projection(
        reversed_dossier,
        chapter_id="4B",
        source_dossier_path=source_path,
        source_dossier_sha256="a" * 64,
    )
    assert repeated == projection


def test_projection_includes_discovery_only_evidence_only_as_explicit_context(
    tmp_path: Path,
) -> None:
    payload = _dossier().model_dump(mode="json")
    payload["evidence"][2]["final_evidence_use"] = "discovery_only"
    dossier = RulerEvidenceDossier.model_validate(payload)

    projection = build_ruler_chapter_projection(
        dossier,
        chapter_id="4B",
        source_dossier_path=tmp_path / "dossier.json",
        source_dossier_sha256="c" * 64,
    )

    assert projection.contextual_discovery_only_evidence_ids == ("E003",)
    assert next(
        item for item in projection.evidence if item.evidence_id == "E003"
    ).final_evidence_use == "discovery_only"

    invalid = deepcopy(payload)
    mapping = next(item for item in invalid["mappings"] if item["evidence_id"] == "E003")
    mapping["relation"] = "supports"
    with pytest.raises(ValueError, match="not explicitly contextual: E003"):
        build_ruler_chapter_projection(
            RulerEvidenceDossier.model_validate(invalid),
            chapter_id="4B",
            source_dossier_path=tmp_path / "dossier.json",
            source_dossier_sha256="c" * 64,
        )


def test_projection_loads_local_evidence_directly_from_parent_artifact(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "local-priors.json"
    local_priors = [
        {
            "methodology_id": methodology_id,
            "status": "evidence_found",
            "mapping_note": "Structured political-freedom context.",
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
                    "warnings": ["Country-level context; attribution required."],
                    "period_role": "target",
                    "unit": "index",
                    "scale": "0-1",
                    "uncertainty": {"lower": 0.58, "upper": 0.66},
                }
            ],
        }
        for methodology_id in _chapter_ids("4B")
    ]
    encoded = json.dumps(local_priors, indent=2, sort_keys=True).encode()
    local_path.write_bytes(encoded)
    digest = sha256(encoded).hexdigest()
    payload = _dossier().model_dump(mode="json")
    for prior in payload["local_priors"]:
        if prior["methodology_id"].startswith("4B."):
            prior["artifact_path"] = str(local_path)
            prior["artifact_sha256"] = digest
    dossier = RulerEvidenceDossier.model_validate(payload)

    projection = build_ruler_chapter_projection(
        dossier,
        chapter_id="4B",
        source_dossier_path=tmp_path / "dossier.json",
        source_dossier_sha256="e" * 64,
    )

    assert projection.local_evidence.status == "available"
    assert projection.local_evidence.artifact_sha256 == digest
    package = projection.local_evidence.package
    assert package is not None
    assert package.facts[0].fact_id == "LF001"
    assert package.facts[0].value == 0.62
    assert package.facts[0].locator == "local-prior:4B.1"
    assert package.longitudinal_signals[0].signal_id == "LS001"
    assert all(
        not item.url.startswith("local-prior:")
        for item in projection.evidence
    )


def test_projection_keeps_legacy_v1_readable_with_explicit_local_gap(
    tmp_path: Path,
) -> None:
    projection = build_ruler_chapter_projection(
        _dossier(),
        chapter_id="4B",
        source_dossier_path=tmp_path / "dossier.json",
        source_dossier_sha256="e" * 64,
    )
    payload = projection.model_dump(mode="json")
    payload.pop("local_evidence")

    restored = RulerChapterProjection.model_validate(payload)

    assert restored.local_evidence.status == "unavailable"
    assert restored.local_evidence.package is None
    assert "legacy projection" in restored.local_evidence.error


def test_projection_exposes_hash_mismatch_without_dropping_web_evidence(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "local-priors.json"
    local_path.write_text("[]", encoding="utf-8")
    payload = _dossier().model_dump(mode="json")
    for prior in payload["local_priors"]:
        if prior["methodology_id"].startswith("4B."):
            prior["artifact_path"] = str(local_path)
            prior["artifact_sha256"] = "f" * 64

    projection = build_ruler_chapter_projection(
        RulerEvidenceDossier.model_validate(payload),
        chapter_id="4B",
        source_dossier_path=tmp_path / "dossier.json",
        source_dossier_sha256="e" * 64,
    )

    assert projection.local_evidence.status == "invalid"
    assert "hash does not match" in projection.local_evidence.error
    assert [item.evidence_id for item in projection.evidence] == ["E001", "E003"]


def test_projection_requires_complete_chapter_and_valid_source_hash(tmp_path: Path) -> None:
    dossier = _dossier()

    with pytest.raises(ValueError, match="complete 3B chapter"):
        build_ruler_chapter_projection(
            dossier,
            chapter_id="3B",
            source_dossier_path=tmp_path / "dossier.json",
            source_dossier_sha256="d" * 64,
        )
    with pytest.raises(ValueError, match="String should match pattern"):
        build_ruler_chapter_projection(
            dossier,
            chapter_id="4B",
            source_dossier_path=tmp_path / "dossier.json",
            source_dossier_sha256="not-a-sha",
        )


def test_batch_context_estimate_enforces_ceiling_before_claim(tmp_path: Path) -> None:
    first = build_ruler_chapter_projection(
        _dossier(job_key="dossier:one"),
        chapter_id="4B",
        source_dossier_path=tmp_path / "one.json",
        source_dossier_sha256="1" * 64,
    )
    second = build_ruler_chapter_projection(
        _dossier(job_key="dossier:two"),
        chapter_id="4B",
        source_dossier_path=tmp_path / "two.json",
        source_dossier_sha256="2" * 64,
    )

    estimate = estimate_chapter_projection_batch_context(
        (first, second), context_ceiling=100_000, prompt_overhead_tokens=2_000
    )

    assert estimate.projection_count == 2
    assert estimate.estimated_input_tokens == estimate.projection_tokens + 2_000
    assert estimate.remaining_tokens == 100_000 - estimate.estimated_input_tokens
    with pytest.raises(ValueError, match="exceeds context ceiling"):
        estimate_chapter_projection_batch_context(
            (first, second),
            context_ceiling=estimate.estimated_input_tokens - 1,
            prompt_overhead_tokens=2_000,
        )
    with pytest.raises(ValueError, match="unique dossier job keys"):
        estimate_chapter_projection_batch_context(
            (first, first), context_ceiling=100_000
        )


def _dossier(*, job_key: str = "dossier:test") -> RulerEvidenceDossier:
    methodology_ids = (*_chapter_ids("4B"), "5B.1")
    evidence = [
        _evidence("E001", final_evidence_use="final_evidence"),
        _evidence("E002", final_evidence_use="final_evidence"),
        _evidence("E003", final_evidence_use="context"),
        _evidence("E004", final_evidence_use="final_evidence"),
    ]
    mappings = [
        {
            "evidence_id": "E001",
            "methodology_id": methodology_id,
            "relation": "supports",
            "relevance": f"Evidence relevant to {methodology_id}.",
        }
        for methodology_id in _chapter_ids("4B")
    ]
    mappings.extend(
        (
            {
                "evidence_id": "E003",
                "methodology_id": "4B.2",
                "relation": "context",
                "relevance": "Background context only.",
            },
            {
                "evidence_id": "E002",
                "methodology_id": "5B.1",
                "relation": "supports",
                "relevance": "Evidence for another chapter.",
            },
        )
    )
    return RulerEvidenceDossier.model_validate(
        {
            "schema_version": "ruler_evidence_dossier_v2",
            "job_key": job_key,
            "run_key": "batch:test",
            "iso3": "AAA",
            "country_name": "Example Republic",
            "ruler_id": "ruler-1",
            "ruler_year_id": 10,
            "ruler_name": "Example Ruler",
            "period_start_year": 2020,
            "period_end_year": 2020,
            "methodology_ids": methodology_ids,
            "evidence": evidence,
            "mappings": mappings,
            "coverage": [
                {
                    "methodology_id": methodology_id,
                    "status": "covered",
                    "evidence_ids": ["E001"]
                    + (["E003"] if methodology_id == "4B.2" else []),
                    "reason": "Relevant cited evidence was found.",
                }
                for methodology_id in _chapter_ids("4B")
            ]
            + [
                {
                    "methodology_id": "5B.1",
                    "status": "covered",
                    "evidence_ids": ["E002"],
                    "reason": "Other chapter evidence was found.",
                }
            ],
            "unresolved_gaps": ["Attribution remains disputed."],
            "completed_queries": ["example query"],
            "normalization_warnings": [],
            "local_priors": [
                {
                    "methodology_id": methodology_id,
                    "status": "available",
                    "summary": f"Local summary for {methodology_id}.",
                    "artifact_path": f"data/{methodology_id}.json",
                    "artifact_sha256": "f" * 64,
                }
                for methodology_id in methodology_ids
            ],
            "evidence_environment": {
                "criticism_possible": "Criticism was possible in the fixture.",
                "censorship_and_self_censorship": "E001 provides limited context.",
                "safe_reporting_channels": "Channels existed but are incompletely documented.",
                "official_statistics_reliability": "No statistics are used.",
                "languages_and_archives_searched": ["English fixture archive"],
                "source_concentration": "The evidence is source-concentrated.",
                "duplicate_event_risk": "Repeated coverage was collapsed.",
                "complaint_volume_interpretation": "Volume is not severity.",
                "relevant_denominators": "Population and exposure remain contextual.",
                "inherited_conditions_shocks_and_authority": "Authority was assessed separately.",
                "chapter_specific_biases": ["Source concentration"],
                "supporting_evidence_ids": ["E001"],
            },
            "run_profile": {
                "provider_profile": "researcher",
                "provider": "openai",
                "model": "gpt-example",
                "workflow_mode": "direct_search_chapter_loop_v1",
                "formatter_provider_profile": "formatter",
                "formatter_provider": "openai",
                "formatter_model": "gpt-formatter",
                "research_notebook_path": "trusted/notebook.md",
                "research_notebook_sha256": "b" * 64,
                "local_evidence_calls": [],
                "searches_attempted": [],
                "sources_visited": [],
                "discovery_search_id": "search-1",
                "source_mix_note": "Mixed sources.",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "estimated_cost_usd": 0.01,
                },
            },
        }
    )


def _evidence(evidence_id: str, *, final_evidence_use: str) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "claim": f"Claim for {evidence_id}.",
        "url": f"https://example.test/{evidence_id}",
        "title": f"Source {evidence_id}",
        "publisher": "Example Publisher",
        "publication_date": "2020-06-01",
        "excerpt": f"Excerpt for {evidence_id}.",
        "source_locator": f"section-{evidence_id.lower()}",
        "canonical_fact_key": f"example.test:{evidence_id.lower()}:claim",
        "source_type": "primary",
        "source_confidence": "high",
        "source_confidence_reason": "Contemporaneous primary source.",
        "final_evidence_use": final_evidence_use,
        "period_fit": "Within target year.",
        "ruler_attribution": "Directly attributable.",
        "contrary_evidence": [],
    }


def _chapter_ids(chapter_id: str) -> tuple[str, ...]:
    return tuple(f"{chapter_id}.{index}" for index in range(1, 11))
