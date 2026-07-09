from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def test_source_confidence_registry_profiles_grokipedia_as_very_low(
    project_root: Path,
) -> None:
    grokipedia = _profile_by_domain(project_root, "grokipedia.com")

    assert grokipedia["default_confidence"] == "very_low"
    assert grokipedia["final_evidence_use"] == "discovery_only"
    assert grokipedia["source_type"] == "ai_generated_encyclopedia"


def test_source_confidence_registry_profiles_wikipedia_for_orientation(
    project_root: Path,
) -> None:
    wikipedia = _profile_by_domain(project_root, "wikipedia.org")

    assert wikipedia["default_confidence"] == "medium_high"
    assert wikipedia["final_evidence_use"] == "context"
    assert "orientation" in wikipedia["allowed_use"].lower()
    assert "sole support" in wikipedia["caveats"].lower()


def test_source_confidence_registry_profiles_official_government_conditionally(
    project_root: Path,
) -> None:
    official = _profile_by_source(project_root, "Official government sites")

    assert official["default_confidence"] == "medium_low"
    assert "self-serving" in official["allowed_use"].lower()
    overrides = {item["claim_type"]: item for item in official["claim_type_overrides"]}
    assert (
        overrides["self_serving_claim_about_government_fairness_or_restraint"][
            "confidence"
        ]
        == "medium_low"
    )
    assert overrides["formal_fact_or_primary_document"]["confidence"] == "medium_high"


def test_source_confidence_registry_requires_citation_profile_fields(
    project_root: Path,
) -> None:
    registry = _load_registry(project_root)

    assert registry["required_citation_profile_fields"] == [
        "source_confidence",
        "source_confidence_reason",
        "source_type",
        "final_evidence_use",
    ]
    assert "sole support" in registry["source_diversity_rule"].lower()
    assert registry["unlisted_source_policy"]["default_confidence"] == "medium_low"


def test_internet_research_policy_references_registry_parallel_and_profiling(
    project_root: Path,
) -> None:
    policy = json.loads(
        (project_root / "docs/process/internet-research-opencode-policy.json").read_text(
            encoding="utf-8"
        )
    )

    assert policy["allowed_web_path"]["discovery"] == "leaders-db research parallel-search"
    assert policy["allowed_web_path"]["known_url_fetch"] == "webfetch"
    assert policy["run_profiling_required"]["enabled"] is True
    assert policy["source_confidence_registry"] == {
        "path": "docs/methodology/source-confidence-registry.json",
        "required": True,
        "required_citation_profile_fields": [
            "source_confidence",
            "source_confidence_reason",
            "source_type",
            "final_evidence_use",
        ],
        "source_diversity_rule": (
            "Do not use low or very_low confidence sources as sole support for "
            "score-bearing claims. Rate newly discovered sources before relying on them."
        ),
    }


def _load_registry(project_root: Path) -> dict[str, Any]:
    return json.loads(
        (project_root / "docs/methodology/source-confidence-registry.json").read_text(
            encoding="utf-8"
        )
    )


def _profile_by_domain(project_root: Path, domain: str) -> dict[str, Any]:
    for profile in _load_registry(project_root)["source_profiles"]:
        if profile["domain"] == domain:
            return profile
    raise AssertionError(f"missing source confidence profile for domain {domain}")


def _profile_by_source(project_root: Path, source: str) -> dict[str, Any]:
    for profile in _load_registry(project_root)["source_profiles"]:
        if profile["source"] == source:
            return profile
    raise AssertionError(f"missing source confidence profile for source {source}")
