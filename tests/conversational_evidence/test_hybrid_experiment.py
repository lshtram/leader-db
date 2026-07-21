from pathlib import Path

import pytest

from leaders_db.conversational_evidence.hybrid_experiment.artifacts import (
    baseline_manifest,
    evidence_index,
    normalize_url,
    quality_summary,
)
from leaders_db.conversational_evidence.hybrid_experiment.curation import (
    ChapterCuration,
    _curation_warnings,
    _normalize_summary,
)
from leaders_db.conversational_evidence.hybrid_experiment.depth_models import (
    SaturationPolicy,
)
from leaders_db.conversational_evidence.hybrid_experiment.full_curation import (
    apply_chapter_curations,
)
from leaders_db.conversational_evidence.hybrid_experiment.prompts import (
    saturation_chapter,
)
from leaders_db.conversational_evidence.hybrid_experiment.runner import (
    _recoverable_gaps,
)
from leaders_db.conversational_evidence.hybrid_experiment.saturation import (
    _records,
)
from leaders_db.conversational_evidence.hybrid_experiment.top_up import (
    chapters_needing_top_up,
)


def test_evidence_index_deduplicates_and_reuses_urls() -> None:
    notes = [
        ("1B", "1B.1 https://Example.com/a?utm_source=x"),
        ("2B", "2B.3 https://example.com/a"),
    ]

    records = evidence_index(notes)

    assert len(records) == 1
    assert records[0]["evidence_id"] == "E0001"
    assert records[0]["chapters"] == ["1B", "2B"]
    assert records[0]["mentioned_lenses"] == ["1B.1", "2B.3"]


def test_quality_summary_reports_mechanical_warnings() -> None:
    records = evidence_index([("3B", "3B.1 https://example.com/a")])

    summary = quality_summary(records)

    assert summary["chapters"]["3B"]["warnings"] == [
        "fewer_than_10_distinct_urls",
        "fewer_than_5_domains",
        "top_domain_above_35_percent",
        "not_all_lenses_mentioned_near_urls",
    ]


def test_baseline_manifest_hashes_production_files() -> None:
    root = Path(__file__).resolve().parents[2]

    value = baseline_manifest(root)

    assert value["git_head"]
    assert len(value["production_files"]) == 6
    assert normalize_url("https://EXAMPLE.com/a/?utm_campaign=x") == "https://example.com/a"


def test_follow_up_uses_only_gaps_from_targeted_chapters() -> None:
    review = {
        "overall_decision": "targeted_follow_up",
        "chapters": [
            {
                "chapter_id": "1B",
                "decision": "pass",
                "material_gaps": [{"gap": "credible but nonrecoverable"}],
            },
            {
                "chapter_id": "5B",
                "decision": "targeted_follow_up",
                "material_gaps": [{"gap": "recoverable"}],
            },
        ],
    }

    assert _recoverable_gaps(review) == [
        {"chapter_id": "5B", "gap": "recoverable"}
    ]


def test_saturation_prompt_uses_breadth_targets_as_quality_controls() -> None:
    policy = SaturationPolicy()

    prompt = saturation_chapter(
        "Example Ruler",
        "Example Country",
        2022,
        "2B",
        "2B.1 example lens",
        [],
        "No accepted web evidence yet.",
        wave=1,
        candidate_target=policy.candidate_target_per_wave,
        opened_target=policy.opened_target_per_wave,
        accepted_min=policy.accepted_url_min,
        accepted_max=policy.accepted_url_max,
        domain_min=policy.domain_min,
    )

    assert "discover about 35" in prompt
    assert "open at least 20" in prompt
    assert "20-35" in prompt
    assert "not quotas" in prompt
    assert "local-language" in prompt
    assert "search-result snippets are not evidence" in prompt
    assert "Remove duplicates before reporting" in prompt


def test_saturation_policy_rejects_incoherent_targets() -> None:
    with pytest.raises(ValueError, match="may not exceed"):
        SaturationPolicy(accepted_url_min=36, accepted_url_max=35)


def test_empty_saturation_run_has_no_ledger_records(tmp_path: Path) -> None:
    assert _records(tmp_path, "2B") == ()
    assert not (tmp_path / "chapters" / "2B.md").exists()


def test_curation_contract_reconciles_disposition_counts() -> None:
    value = ChapterCuration.model_validate(
        {
            "chapter_id": "2B",
            "records": [
                {
                    "evidence_id": "E0001",
                    "disposition": "retain",
                    "source_family": "UN",
                    "duplicate_of": None,
                    "reason": "direct synthesis",
                },
                {
                    "evidence_id": "E0002",
                    "disposition": "drop",
                    "source_family": "Reuters",
                    "duplicate_of": "E0001",
                    "reason": "duplicate",
                },
            ],
            "summary": {
                "retained": 1,
                "context": 0,
                "dropped": 1,
                "remaining_concerns": [],
            },
        }
    )

    assert value.summary.dropped == 1


def test_curation_summary_counts_are_derived_from_records() -> None:
    value = {
        "records": [{"disposition": "retain"}, {"disposition": "drop"}],
        "summary": {"retained": 0, "context": 9, "dropped": 0},
    }

    _normalize_summary(value)

    assert value["summary"] == {"retained": 1, "context": 0, "dropped": 1}


def test_curation_warns_when_one_family_exceeds_quarter() -> None:
    records = [
        {
            "evidence_id": f"E{index:04d}",
            "disposition": "retain",
            "source_family": "one family" if index < 4 else f"family {index}",
            "duplicate_of": None,
            "reason": "useful",
        }
        for index in range(1, 11)
    ]
    value = ChapterCuration.model_validate(
        {
            "chapter_id": "4B",
            "records": records,
            "summary": {
                "retained": 10,
                "context": 0,
                "dropped": 0,
                "remaining_concerns": [],
            },
        }
    )

    assert "above the 25% family ceiling" in _curation_warnings(value)[0]


def test_full_curation_drops_only_rejected_chapter_mapping() -> None:
    source = {
        "schema_version": "hybrid_experiment_dossier_v2",
        "evidence": [
            {
                "evidence_id": "E0001",
                "canonical_url": "https://example.com/a",
                "lenses": ["2B.1", "3B.1"],
                "chapters": ["2B", "3B"],
            }
        ],
        "mappings": [
            {"evidence_id": "E0001", "lenses": ["2B.1", "3B.1"]}
        ],
    }
    curations = {
        chapter: {
            "records": (
                [
                    {
                        "evidence_id": "E0001",
                        "disposition": "drop" if chapter == "2B" else "retain",
                        "source_family": "Example",
                    }
                ]
                if chapter in {"2B", "3B"}
                else []
            ),
            "summary": {
                "retained": int(chapter == "3B"),
                "context": 0,
                "dropped": int(chapter == "2B"),
                "remaining_concerns": [],
            },
        }
        for chapter in (f"{number}B" for number in range(1, 9))
    }

    curated, report = apply_chapter_curations(source, curations)

    assert curated["mappings"] == [
        {"evidence_id": "E0001", "lenses": ["3B.1"]}
    ]
    assert curated["evidence"][0]["chapters"] == ["3B"]
    assert report["chapters"]["2B"]["distinct_urls"] == 0


def test_top_up_selection_uses_curated_quality_not_raw_counts() -> None:
    summary = {
        "chapters": {
            chapter: {
                "distinct_urls": 19 if chapter == "1B" else 20,
                "source_families": 9 if chapter == "2B" else 10,
                "mapped_lenses": (
                    [f"{chapter}.{lens}" for lens in range(1, 10)]
                    if chapter == "3B"
                    else [f"{chapter}.{lens}" for lens in range(1, 11)]
                ),
            }
            for chapter in (f"{number}B" for number in range(1, 9))
        }
    }

    assert chapters_needing_top_up(summary) == ("1B", "2B", "3B")
