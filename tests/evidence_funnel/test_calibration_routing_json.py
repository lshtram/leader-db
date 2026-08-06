from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.evidence_funnel.calibration_routing import normalize_routing_table
from leaders_db.evidence_funnel.models import SourceDescriptor


def test_normalizes_complete_explicit_m3_json(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    raw.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "chunk_id": "U0002",
                        "decision": "include",
                        "question_ids": ["5B.3", "5B.9"],
                        "relevance": "high",
                        "adjacent_context": "Inflation response and fiscal cost.",
                        "exclusion_reason": None,
                    },
                    {
                        "chunk_id": "U0001",
                        "decision": "exclude",
                        "question_ids": [],
                        "relevance": "none",
                        "adjacent_context": "Administrative cover.",
                        "exclusion_reason": "No substantive evidence.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert tuple(item.chunk_id for item in result.decisions) == ("U0001", "U0002")
    assert not result.decisions[0].included
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")
    assert result.decisions[1].relevance_strength == "pivotal"


def test_normalizes_fenced_router_decisions_dialect(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "router_decisions": [
            {
                "chunk_id": "U0001",
                "decision": "include",
                "question_ids": ["5B.3"],
                "relevance": "high",
                "adjacent_context": "Explicit economic evidence.",
            }
        ],
        "summary": {"included": 1},
    }
    raw.write_text(f"```json\n{json.dumps(payload)}\n```\n", encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001",),
    )

    assert result.decisions[0].included
    assert result.decisions[0].relevant_question_ids == ("5B.3",)


def test_normalizes_numeric_chapter_lenses_alias(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = [
        {
            "chunk_id": "U0001",
            "decision": "include",
            "relevance": "material",
            "5B_lenses": ["5B.3", "5B.9"],
            "adjacent_context": "Measured fiscal policy outcome.",
            "exclusion_reason": None,
        }
    ]
    raw.write_text(f"```json\n{json.dumps(payload)}\n```", encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].relevant_question_ids == ("5B.3", "5B.9")


def test_normalizes_fenced_routing_decisions_dialect(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "routing_decisions": [
            {
                "chunk_id": "U0001",
                "decision": "include",
                "applicable_question_ids": ["5B.3"],
                "relevance": "material",
                "rationale": "A concrete measured fiscal outcome.",
                "adjacent_context_needed": "The next page contains implementation detail.",
                "exclusion_reason": None,
            }
        ]
    }
    raw.write_text(f"```json\n{json.dumps(payload)}\n```", encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001",),
    )

    assert result.decisions[0].included
    assert result.decisions[0].relevant_question_ids == ("5B.3",)
    assert result.decisions[0].explanation == "A concrete measured fiscal outcome."


def test_rejects_multiple_decision_list_aliases(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    row = {
        "chunk_id": "U0001",
        "decision": "exclude",
        "question_ids": [],
        "relevance": "none",
        "exclusion_reason": "No material evidence.",
    }
    raw.write_text(
        json.dumps({"decisions": [row], "routing_decisions": [row]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="decision-list aliases conflict"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001",),
        )


def test_normalizes_excluded_low_relevance(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "exclude",
                "question_ids": [],
                "relevance": "low",
                "adjacent_context": "Relevant context below the inclusion threshold.",
                "exclusion_reason": "No material evidence.",
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001",),
    )

    assert not result.decisions[0].included
    assert result.decisions[0].relevance_strength == "weak"


@pytest.mark.parametrize("relevance", ["material", "pivotal"])
def test_rejects_excluded_material_relevance(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    relevance: str,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "exclude",
                "question_ids": [],
                "relevance": relevance,
                "adjacent_context": "Material evidence must be included.",
                "exclusion_reason": "Contradictory disposition.",
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="decision and relevance conflict"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001",),
        )


def test_normalizes_json_fence_after_prose_and_non_json_fence(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "exclude",
                "question_ids": [],
                "relevance": "none",
                "adjacent_context": "No material evidence.",
                "exclusion_reason": "Cover page.",
            }
        ]
    }
    raw.write_text(
        "Routing notes follow.\n```\nnot json\n```\n"
        f"```JSON\n{json.dumps(payload)}\n```\nEnd report.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001",),
    )

    assert not result.decisions[0].included


def test_normalizes_fenced_materiality_routing_dialect(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    rows = [
        {
            "chunk_id": "U0001",
            "decision": "include",
            "applicable_lenses": ["5B.3"],
            "relevant_facts": ["The enacted policy cost two percent of GDP."],
        },
        {
            "chunk_id": "U0002",
            "decision": "exclude",
            "exclusion_reason": "Table of contents; no evidence content.",
        },
    ]
    raw.write_text(f"```json\n{json.dumps(rows)}\n```\n", encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert result.decisions[0].included
    assert result.decisions[0].relevant_question_ids == ("5B.3",)
    assert not result.decisions[1].included


def test_normalizes_boolean_include_and_lens_explanations(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    rows = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "include": True,
                "question_ids": ["5B.3"],
                "evidence_cited_lenses": {
                    "5B.3": "The enacted budget reports a quantified fiscal cost."
                },
            },
            {
                "chunk_id": "U0002",
                "include": False,
                "question_ids": [],
                "exclusion_reason": "Generic background only.",
            },
        ]
    }
    raw.write_text(
        f"## Routing report\n\n```json\n{json.dumps(rows)}\n```\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert result.decisions[0].included
    assert "quantified fiscal cost" in result.decisions[0].explanation
    assert not result.decisions[1].included


def test_normalizes_complete_excluded_then_included_tables(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### Excluded\n\n"
        "| chunk_id | exclusion_reason |\n|---|---|\n"
        "| **U0001** | Boilerplate with no evidence. |\n\n"
        "### Included\n\n"
        "| chunk_id | question_ids | concrete_evidence_record |\n|---|---|---|\n"
        "| **U0002** | 5B.3, 5B.9 | A named, quantified policy action. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert not result.decisions[0].included
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")


def test_normalizes_complete_all_excluded_table(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### Excluded\n\n"
        "| chunk_id | exclusion_reason |\n|---|---|\n"
        "| **U0001** | Boilerplate. |\n"
        "| **U0002** | Generic background. |\n\n"
        "### Included\n\n"
        "| chunk_id | question_ids | evidence |\n|---|---|---|\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert all(not decision.included for decision in result.decisions)


def test_normalizes_complete_all_excluded_decision_table(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | decision | exclusion_reason |\n|---|---|---|\n"
        "| U0001 | EXCLUDE | Boilerplate. |\n"
        "| U0002 | EXCLUDE | Generic background mentioning 5B.3 only. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert all(not decision.included for decision in result.decisions)


def test_rejects_excluded_decision_row_with_question_ids(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | decision | question_ids | exclusion_reason |\n|---|---|---|---|\n"
        "| U0001 | EXCLUDE | 5B.3 | Boilerplate. |\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="excluded Markdown row has question IDs"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001",),
        )


def test_normalizes_human_readable_decision_headers(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| Chunk | Decision | Lenses | Note |\n|---|---|---|---|\n"
        "| U0001 | Exclude | — | Generic background. |\n"
        "| U0002 | Include | 5B.3, 5B.9 | Quantified policy action. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert not result.decisions[0].included
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")


def test_normalizes_reason_class_header(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| Chunk | Decision | Reason class |\n|---|---|---|\n"
        "| U0001 | Exclude | Electoral narrative, no economic evidence. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001",),
    )

    assert not result.decisions[0].included


def test_normalizes_applicable_lens_parenthetical_header(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | Decision | Applicable Lens(es) | Exclusion Reason |\n"
        "|---|---|---|---|\n"
        "| U0001 | EXCLUDE | — | Boilerplate. |\n"
        "| U0002 | INCLUDE | 5B.3, 5B.9 | Quantified evidence rationale. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001", "U0002"),
    )

    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")


@pytest.mark.parametrize(
    "header",
    [
        "| Chunk | chunk_id | Decision | Note |",
        "| Chunk | Decision | Lenses | Applicable Lenses | Note |",
    ],
)
def test_rejects_colliding_human_header_aliases(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    header: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(f"{header}\n|---|---|---|---|\n", encoding="utf-8")

    with pytest.raises(ValueError, match="header aliases conflict"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001",),
        )


def test_repeated_data_cells_are_not_treated_as_header_aliases(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| Chunk | Decision | Lenses | Note | Extra |\n|---|---|---|---|---|\n"
        "| U0001 | EXCLUDE | — | Repeated prose. | Repeated prose. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001",),
    )

    assert not result.decisions[0].included


def test_rejects_incomplete_sectioned_markdown_accounting(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### Excluded\n\n| **U0001** | Boilerplate. |\n\n"
        "### Included\n\n| chunk_id | question_ids | evidence |\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="chunk set mismatch"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001", "U0002"),
        )


@pytest.mark.parametrize(
    "included_row",
    [
        "| U0002 | | Evidence text merely mentions 5B.3. |",
        "| Evidence mentions U0002 | 5B.3 | Material evidence. |",
        "| U0002 | 5B.3 | |",
        "| U0002 | 15B.3 | Material evidence. |",
        "| U0002 | 5B.3, 8B.1 | Material evidence. |",
        "| U0002 | 5B.3, 5B.3 | Material evidence. |",
    ],
)
def test_rejects_misplaced_ids_or_missing_markdown_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    included_row: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### Excluded\n\n"
        "| chunk_id | exclusion_reason |\n|---|---|\n"
        "| U0001 | Context for 5B.3, but no material evidence. |\n\n"
        "### Included\n\n"
        "| chunk_id | question_ids | concrete_evidence_record |\n|---|---|---|\n"
        f"{included_row}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001", "U0002"),
        )


def test_normalizes_m3_question_and_context_aliases(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    explanation = "Documents a quantified policy outcome and its qualification."
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "include",
                "applicable_question_ids": ["5B.3", "5B.7"],
                "relevance": explanation,
                "adjacent_context_needed": "The preceding definition is useful context.",
                "exclusion_reason": None,
            }
        ]
    }
    raw.write_text(f"```json\n{json.dumps(payload)}\n```", encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw,
        source=descriptor,
        chunk_ids=("U0001",),
    )

    assert result.decisions[0].relevant_question_ids == ("5B.3", "5B.7")
    assert result.decisions[0].explanation == "The preceding definition is useful context."


def test_normalizes_list_valued_adjacent_context(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "include": True,
                "question_ids": ["5B.3"],
                "relevance": "Documents a quantified policy outcome.",
                "adjacent_context": ["U0002", "U0010"],
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].adjacent_chunk_ids == ("U0002", "U0010")
    assert result.decisions[0].explanation == "Documents a quantified policy outcome."


def test_validates_but_does_not_infer_ids_from_prose_context_list(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "include": True,
                "question_ids": ["5B.3"],
                "relevance": "Documents a quantified policy outcome.",
                "adjacent_context": [
                    "U0002 contains broader context, but this is not a locator.",
                    "The prior discussion supplies attribution.",
                ],
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].adjacent_chunk_ids == ()


def test_rejects_mixed_ids_and_prose_in_context_list(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "include": True,
                "question_ids": ["5B.3"],
                "relevance": "Material evidence.",
                "adjacent_context": ["U0002", "Prior-page prose."],
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="mixed adjacent chunk IDs and prose"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_mixed_adjacent_context_representations(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "include": True,
                "question_ids": ["5B.3"],
                "relevance": "Material evidence.",
                "adjacent_context": ["U0002"],
                "adjacent_context_needed": "Prior-page context.",
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="mixed representations"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_inverts_adjacent_context_for_links(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "exclude",
                "question_ids": [],
                "relevance": "low",
                "rationale": "Context only.",
                "adjacent_context_for": ["U0002"],
                "exclusion_reason": "No independent material finding.",
            },
            {
                "chunk_id": "U0002",
                "decision": "include",
                "question_ids": ["5B.3"],
                "relevance": "high",
                "rationale": "Material fiscal finding.",
                "adjacent_context_for": [],
                "exclusion_reason": None,
            },
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].adjacent_chunk_ids == ()
    assert result.decisions[1].adjacent_chunk_ids == ("U0001",)


def test_inverts_exact_adjacency_ids_from_excluded_context(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "include": False,
                "question_ids": [],
                "relevance": "none",
                "adjacent_context": ["U0002"],
                "exclusion_reason": "Context for the material finding.",
            },
            {
                "chunk_id": "U0002",
                "include": True,
                "question_ids": ["5B.3"],
                "relevance": "high",
                "rationale": "Measured fiscal policy outcome.",
                "adjacent_context": [],
                "exclusion_reason": None,
            },
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].adjacent_chunk_ids == ()
    assert result.decisions[1].adjacent_chunk_ids == ("U0001",)


def test_rejects_unknown_adjacent_context_for_target(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "exclude",
                "question_ids": [],
                "relevance": "low",
                "rationale": "Context only.",
                "adjacent_context_for": ["U9999"],
                "exclusion_reason": "No independent material finding.",
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown adjacent_context_for"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_adjacent_context_for_excluded_target(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "exclude",
                "question_ids": [],
                "relevance": "low",
                "rationale": "Context only.",
                "adjacent_context_for": ["U0002"],
                "exclusion_reason": "No independent material finding.",
            },
            {
                "chunk_id": "U0002",
                "decision": "exclude",
                "question_ids": [],
                "relevance": "low",
                "rationale": "Also context only.",
                "exclusion_reason": "No independent material finding.",
            },
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="targets excluded chunks"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
        )


def test_rationale_does_not_mask_invalid_structured_aliases(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "include",
                "question_ids": ["5B.3"],
                "relevance": "high",
                "rationale": "Material fiscal finding.",
                "evidence_cited_lenses": {"5B.99": "Invalid lens."},
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="non-5B IDs"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rationale_does_not_mask_conflicting_adjacent_text(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "include",
                "question_ids": ["5B.3"],
                "relevance": "high",
                "rationale": "Material fiscal finding.",
                "adjacent_context": "Prior page.",
                "adjacent_context_needed": "Following page.",
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="aliases conflict"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_uses_material_finding_as_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = [
        {
            "chunk_id": "U0001",
            "decision": "INCLUDE",
            "applicable_lenses": ["5B.3"],
            "material_finding": "Measured fiscal result with attribution.",
            "adjacent_context_needed": None,
            "exclusion_reason": None,
        }
    ]
    raw.write_text(f"```json\n{json.dumps(payload)}\n```", encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].explanation == "Measured fiscal result with attribution."


def test_allows_null_material_finding_for_excluded_row(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    payload = [
        {
            "chunk_id": "U0001",
            "decision": "EXCLUDE",
            "applicable_lenses": [],
            "material_finding": None,
            "adjacent_context_needed": "Chart context only.",
            "exclusion_reason": "No independently material finding.",
        }
    ]
    raw.write_text(f"```json\n{json.dumps(payload)}\n```", encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert not result.decisions[0].included
    assert result.decisions[0].explanation == "Chart context only."


def test_normalizes_complete_bold_field_blocks(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
**chunk_id: U0001**
- decision: exclude
- applicable_5b_lenses: none
- relevance: none
- adjacent_context: Figure context.
- exclusion_reason: Figure caption only; no policy finding.

---

**chunk_id: U0002**
- decision: include
- applicable_5b_lenses: 5B.3, 5B.9
- relevance: high
- adjacent_context: Prior-page context.
- why_included: Contains a measured fiscal outcome and attributed shock response.
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert not result.decisions[0].included
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")
    assert result.decisions[1].explanation.startswith("Contains a measured")


def test_normalizes_complete_heading_blocks(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
### U0001 — Figure
- **Decision:** exclude
- **Exclusion reason:** Numeric figure only; no attributed policy finding.
- **Adjacent context needed:** None.

---

### U0002 — Fiscal assessment
- **Decision:** include
- **Applicable lenses:**
  - **5B.3** — measured fiscal-rule outcome.
  - **5B.9** — attributed shock response.
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert not result.decisions[0].included
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")


def test_normalizes_heading_field_value_tables(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
### U0001 — EXCLUDE
| Field | Value |
|---|---|
| **chunk_id** | U0001 |
| **decision** | EXCLUDE |
| **applicable_lenses** | — |
| **exclusion_reason** | No material policy finding. |

---

### U0002 — INCLUDE
| Field | Value |
|---|---|
| **chunk_id** | U0002 |
| **decision** | INCLUDE |
| **applicable_lenses** | 5B.3, 5B.9 |
| **inclusion_reason** | Measured policy result with attribution. |
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert not result.decisions[0].included
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")


def test_normalizes_heading_paragraph_fields(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
### U0001
**Text:** Concrete fiscal policy and measured outcome.
**Decision:** **INCLUDE**
**Applicable lenses:** 5B.3, 5B.9

---

### U0002
**Text:** Political background.
**Decision:** **EXCLUDE**
**Applicable lenses:** None
**Exclusion reason:** No independently material finding.
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].relevant_question_ids == ("5B.3", "5B.9")
    assert not result.decisions[1].included


def test_normalizes_decision_in_heading_with_bulleted_fields(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
### U0001 — **EXCLUDE**
- **Question IDs:** (none)
- **Relevance:** No material evidence
- **Adjacent context:** Identity metadata.
- **Exclusion reason:** No policy action or measured outcome.

---

### U0002 — **INCLUDE**
- **Question IDs:** 5B.3, 5B.9
- **Relevance:** Direct material evidence
- **Cited lenses:** Fiscal and shock-management evidence.
- **Evidence record:** The source reports a measured policy outcome.
- **Exclusion reason:** N/A
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert not result.decisions[0].included
    assert result.decisions[0].exclusion_reason == (
        "No policy action or measured outcome."
    )
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")
    assert result.decisions[1].explanation == (
        "The source reports a measured policy outcome."
    )


def test_normalizes_explicit_table_row_wrapped_inside_cell(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | Decision | Question IDs | Relevance | Adjacent | "
        "Exclusion Reason |\n"
        "|---|---|---|---|---|---|\n"
        "| U0001 | EXCLUDE | — | No material evidence | External context, not AM\n"
        "\n"
        "LO's policy response | No enacted domestic policy or targeted measure |\n"
        "| U0002 | INCLUDE | 5B.3 | Concrete fiscal rule | None | N/A |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].exclusion_reason == (
        "No enacted domestic policy or targeted measure"
    )
    assert result.decisions[1].relevant_question_ids == ("5B.3",)


def test_normalizes_relevant_question_ids_table_header(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | Decision | Relevant Question IDs | Lenses Cited | "
        "Exclusion Reason |\n"
        "|---|---|---|---|---|\n"
        "| U0001 | EXCLUDE | — | — | No material finding. |\n"
        "| U0002 | INCLUDE | 5B.3, 5B.9 | 3, 9 | "
        "Concrete policy content with a measured outcome. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")


def test_normalizes_singular_applicable_lens_table_header(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | decision | applicable_lens | exclusion_reason |\n"
        "|---|---|---|---|\n"
        "| U0001 | EXCLUDE | — | No material finding. |\n"
        "| U0002 | INCLUDE | 5B.2 | Concrete appointment evidence. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[1].relevant_question_ids == ("5B.2",)


def test_normalizes_heading_decision_with_unbulleted_reason_fields(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — EXCLUDE\n"
        "**Reason:** No enacted policy or measured outcome. No applicable IDs.\n"
        "\n---\n"
        "### U0002 — **INCLUDE**\n"
        "**Relevance:** 5B.9\n"
        "**Concrete evidence present:** A named targeted shock response.\n"
        "**Cited lenses:** 5B.9\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert not result.decisions[0].included
    assert result.decisions[1].relevant_question_ids == ("5B.9",)
    assert result.decisions[1].explanation == (
        "A named targeted shock response."
    )


def test_normalizes_decorated_applicable_lens_field(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — INCLUDE\n"
        "- **Relevance:** 5B.1, 5B.3\n"
        "- **Applicable lenses:** 5B.1 (agenda), 5B.3 (fiscal rules)\n"
        "- **Material evidence identified:** A concrete fiscal policy.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].relevant_question_ids == ("5B.1", "5B.3")
    assert result.decisions[0].explanation == "A concrete fiscal policy."


def test_normalizes_relevant_questions_and_lenses_cited_aliases(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — EXCLUDE\n"
        "- **Relevant questions:** 5B.5 (adjacent only)\n"
        "- **Exclusion reason:** Context without a material policy finding.\n"
        "\n---\n"
        "### U0002 — INCLUDE\n"
        "- **Relevant questions:** 5B.3, 5B.9\n"
        "- **Lenses cited:** 5B.3 (fiscal), 5B.9 (shock response)\n"
        "- **Material evidence:** A concrete named policy and outcome.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].relevant_question_ids == ()
    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")


def test_normalizes_explicit_none_with_incidental_adjacent_ids(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — EXCLUDE\n"
        "- **Relevant questions:** None (incidental adjacency to 5B.1, 5B.8)\n"
        "- **Exclusion reason:** Intent without implementation evidence.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].relevant_question_ids == ()


@pytest.mark.parametrize(
    "value",
    [
        "None (incidental adjacency to nonsense)",
        "None (incidental adjacency to 5b.1)",
    ],
)
def test_rejects_incidental_adjacency_without_exact_valid_ids(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    value: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — EXCLUDE\n"
        f"- **Relevant questions:** {value}\n"
        "- **Exclusion reason:** No material finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not adjacent-only"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_normalizes_body_decision_and_nonmaterial_lens_annotations(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001\n"
        "**Decision:** EXCLUDE\n"
        "**Applicable lenses:** 5B.5 (marginal — allegation only), "
        "5B.7 (adjacent — opposition research)\n"
        "**Exclusion reason:** No governing action or adjudicated finding.\n"
        "\n---\n"
        "### U0002\n"
        "**Decision:** INCLUDE — marginal\n"
        "**Applicable lenses:** 5B.1 (adjacent — characterization)\n"
        "**Material evidence:** A low-confidence attributed characterization.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].relevant_question_ids == ()
    assert result.decisions[1].relevant_question_ids == ("5B.1",)


def test_normalizes_level_two_heading_checkmark_and_marginal_relevance(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "## U0001 — EXCLUDE\n"
        "- **Relevance:** 5B.1, 5B.9 (marginal)\n"
        "- **Exclusion reason:** Announcements without implementation findings.\n"
        "\n---\n"
        "## U0002 — INCLUDE ✓\n"
        "- **Relevance:** 5B.1, 5B.3\n"
        "- **Material content:** A named fiscal policy with concrete mechanics.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].relevant_question_ids == ()
    assert result.decisions[1].relevant_question_ids == ("5B.1", "5B.3")


def test_normalizes_all_excluded_inline_bold_decisions(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001\n"
        "**Decision: EXCLUDE**\n"
        "**Exclusion reason:** No material finding.\n"
        "\n---\n"
        "### U0002\n"
        "**Decision: EXCLUDE (primary)**\n"
        "**Exclusion reason:** Pre-execution pledge without implementation.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert not any(item.included for item in result.decisions)


def test_normalizes_one_line_bold_id_exclusions(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**U0001** — EXCLUDE. Navigation with no policy content.\n\n"
        "**U0002** — EXCLUDE. Biography without a material finding.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert not any(item.included for item in result.decisions)
    assert result.decisions[1].exclusion_reason == (
        "Biography without a material finding."
    )


def test_normalizes_bold_id_heading_decisions_and_lens_alias(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**U0001** — EXCLUDE\n"
        "- **Exclusion reason:** No material finding.\n"
        "\n---\n"
        "**U0002** — INCLUDE\n"
        "- **Lenses:** 5B.3, 5B.9\n"
        "- **Material content:** A concrete fiscal shock response.\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[1].relevant_question_ids == ("5B.3", "5B.9")
    assert result.decisions[1].explanation == (
        "A concrete fiscal shock response."
    )


def test_rejects_bold_id_heading_and_relevance_conflict(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**U0001** — INCLUDE\n"
        "- **Relevance:** EXCLUDE\n"
        "- **Lenses:** 5B.3\n"
        "- **Material content:** A concrete finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="disposition fields conflict"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_bold_id_include_without_material_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**U0001** — INCLUDE\n"
        "- **Lenses:** 5B.3\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="auditable explanation"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize(
    "structured",
    [
        "### U0001 — INCLUDE\n"
        "- **Question IDs:** 5B.3\n"
        "- **Evidence record:** A concrete finding.\n",
        "**U0001** — locator\n"
        "- **Decision:** INCLUDE\n"
        "- **Applicable lenses:** 5B.3\n"
        "- **Relevance:** A concrete finding.\n",
    ],
)
def test_rejects_mixed_one_line_and_structured_decision_dialects(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    structured: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        structured + "\n**U0001** — EXCLUDE. No material finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mixed inline-exclusion"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize(
    "body",
    [
        "**Decision: EXCLUDE**\n"
        "**Relevance:** 5B.3\n"
        "**Material evidence:** A concrete finding.\n",
        "**Decision:** EXCLUDE\n"
        "**Decision: INCLUDE**\n"
        "**Exclusion reason:** No material finding.\n",
        "**Decision: EXCLUDE (secondary)**\n"
        "**Relevance:** 5B.3\n"
        "**Material evidence:** A concrete finding.\n",
    ],
)
def test_rejects_conflicts_with_inline_bold_decision(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    body: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(f"### U0001 — INCLUDE\n{body}", encoding="utf-8")

    with pytest.raises(ValueError, match="decision"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize(
    "value",
    [
        "8B.1 (adjacent only)",
        "5B.5 (not adjacent only)",
        "5B.5 (adjacent only), 5B.7 (material)",
    ],
)
def test_rejects_invalid_excluded_adjacent_question_annotations(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    value: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — EXCLUDE\n"
        f"- **Relevant questions:** {value}\n"
        "- **Exclusion reason:** Context without a material finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_bold_body_decision_conflicting_with_heading(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — **INCLUDE**\n"
        "- **Decision:** **EXCLUDE**\n"
        "- **Question IDs:** 5B.3\n"
        "- **Evidence record:** A concrete finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="heading and body decisions conflict"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_mixed_field_styles_with_conflicting_decision(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — INCLUDE\n"
        "- **Question IDs:** 5B.3\n"
        "- **Evidence record:** A concrete finding.\n"
        "**Decision:** EXCLUDE\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="heading and body decisions conflict"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_out_of_chapter_id_in_secondary_heading_field(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — INCLUDE\n"
        "- **Question IDs:** 5B.3\n"
        "- **Cited lenses:** 8B.1\n"
        "- **Evidence record:** A concrete finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid heading question IDs"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize("invalid_id", ["5B.99", "9B.1"])
def test_rejects_nonexact_id_in_decorated_heading_field(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    invalid_id: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — INCLUDE\n"
        "- **Relevance:** 5B.3\n"
        f"- **Applicable lenses:** 5B.3 (valid), {invalid_id} (invalid)\n"
        "- **Material evidence identified:** A concrete fiscal policy.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid heading question IDs"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_explicit_empty_structured_question_alias_conflict(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — INCLUDE\n"
        "- **Question IDs:** 5B.3\n"
        "- **Applicable lenses:** None\n"
        "- **Evidence record:** A concrete finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="heading question fields conflict"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_normalizes_chunk_heading_field_tables(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
## Chunk: U0001
**Decision: INCLUDE**
| Field | Value |
|---|---|
| chunk_id | U0001 |
| relevance | ["5B.3", "5B.9"] |
| exclusion_reason | — |
**Routing rationale:** Measured policy outcome with attribution.

---

## Chunk: U0002
**Decision: EXCLUDE**
| Field | Value |
|---|---|
| chunk_id | U0002 |
| relevance | [] |
| exclusion_reason | No independently material finding. |
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].relevant_question_ids == ("5B.3", "5B.9")
    assert not result.decisions[1].included


@pytest.mark.parametrize("reason", ["", "None."])
def test_rejects_missing_paragraph_exclusion_reason(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    reason: str,
) -> None:
    raw = tmp_path / "routing.md"
    reason_field = f"**Exclusion reason:** {reason}\n" if reason else ""
    raw.write_text(
        "### U0001\n"
        "**Text:** Background narrative only.\n"
        "**Decision:** **EXCLUDE**\n"
        "**Applicable lenses:** None\n"
        f"{reason_field}",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lacks an auditable explanation"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_normalizes_bold_id_field_sections(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
**U0001**
- **Decision:** INCLUDE
- **Question IDs:** 5B.3, 5B.9
- **Relevance:** Measured fiscal policy outcome.
- **Exclusion reason:** N/A

---

**U0002**
- **Decision:** EXCLUDE
- **Question IDs:** None
- **Relevance:** Background only.
- **Exclusion reason:** No independently material policy finding.
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].relevant_question_ids == ("5B.3", "5B.9")
    assert not result.decisions[1].included


def test_normalizes_bold_id_relevance_decision_sections(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        """
**U0001** — `page 1`
- **Relevance:** INCLUDE
- **Applicable lenses:** 5B.3, 5B.9
- **Evidence finding(s):**
  - Measured fiscal outcome with attribution.
- **Adjacent context:** None.
**Exclusion reason:** N/A — included.

---

**U0002** — `page 2`
- **Relevance:** EXCLUDE
- **Applicable lenses:** None
**Exclusion reason:** No independently material evidence.
""",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001", "U0002")
    )

    assert result.decisions[0].relevant_question_ids == ("5B.3", "5B.9")
    assert not result.decisions[1].included


def test_rejects_conflicting_bold_id_dispositions(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**U0001**\n"
        "- **Decision:** INCLUDE\n"
        "- **Relevance:** EXCLUDE\n"
        "- **Question IDs:** 5B.3\n"
        "- **Exclusion reason:** N/A\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="disposition fields conflict"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_empty_evidence_finding_before_unbulleted_field(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**U0001** — INCLUDE\n"
        "- **Lenses:** 5B.3\n"
        "- **Evidence finding(s):**\n"
        "**Exclusion reason:** N/A — included.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="auditable explanation"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize(
    ("heading", "table_chunk_id", "message"),
    [
        ("INCLUDE", "U0001", "heading and body decisions conflict"),
        ("EXCLUDE", "U9999", "chunk_id conflicts with heading"),
    ],
)
def test_rejects_conflicting_heading_field_value_identity(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    heading: str,
    table_chunk_id: str,
    message: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        f"### U0001 — {heading}\n"
        "| Field | Value |\n"
        "| :--- | ---: |\n"
        f"| chunk_id | {table_chunk_id} |\n"
        "| decision | EXCLUDE |\n"
        "| applicable_lenses | — |\n"
        "| exclusion_reason | No material finding. |\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_heading_block_id_outside_lens_field(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — Fiscal assessment\n"
        "- **Decision:** include\n"
        "- **Why:** A finding relevant to **5B.3**.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lacks question IDs"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_invalid_id_in_heading_lens_field(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — Fiscal assessment\n"
        "- **Decision:** include\n"
        "- **Applicable lenses:**\n"
        "  - **5B.3** — valid.\n"
        "  - **8B.1** — invalid chapter.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid heading-block question IDs"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_punctuated_sentinel_heading_reason(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "### U0001 — Figure\n"
        "- **Decision:** exclude\n"
        "- **Exclusion reason:** None.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lacks an auditable explanation"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("- decision: exclude\n", "duplicate field-block fields"),
        ("", "invalid field-block question IDs"),
    ],
)
def test_rejects_invalid_bold_field_blocks(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    extra: str,
    message: str,
) -> None:
    lenses = "5B.3" if extra else "15B.3, 8B.1"
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**chunk_id: U0001**\n"
        "- decision: include\n"
        f"{extra}"
        f"- applicable_5b_lenses: {lenses}\n"
        "- why_included: Material finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize("explanation", ["none", "n/a", "-", "—"])
def test_rejects_sentinel_field_block_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    explanation: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**chunk_id: U0001**\n"
        "- decision: exclude\n"
        "- applicable_5b_lenses: none\n"
        f"- exclusion_reason: {explanation}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lacks an auditable explanation"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_rejects_invalid_lens_on_excluded_field_block(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "**chunk_id: U0001**\n"
        "- decision: exclude\n"
        "- applicable_5b_lenses: 5B.99\n"
        "- exclusion_reason: No material finding.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid field-block question IDs"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_uses_prose_relevance_column_as_table_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | decision | question_ids | relevance | exclusion_reason |\n"
        "|---|---|---|---|---|\n"
        "| U0001 | INCLUDE | 5B.3 | Measured fiscal outcome with attribution. | — |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].explanation.startswith("Measured fiscal")


@pytest.mark.parametrize("header", ["Applicable 5B Lens", "Applicable 5B Lens(es)"])
def test_normalizes_singular_applicable_5b_lens_header(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    header: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        f"| chunk_id | Decision | {header} | Exclusion Reason |\n"
        "|---|---|---|---|\n"
        "| U0001 | INCLUDE | 5B.3, 5B.9 | Concrete measured policy outcome. |\n",
        encoding="utf-8",
    )

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].relevant_question_ids == ("5B.3", "5B.9")


@pytest.mark.parametrize("label", ["high", "High.", "INCLUDE", "excluded"])
def test_rejects_controlled_relevance_label_as_table_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    label: str,
) -> None:
    raw = tmp_path / "routing.md"
    raw.write_text(
        "| chunk_id | decision | question_ids | relevance | exclusion_reason |\n"
        "|---|---|---|---|---|\n"
        f"| U0001 | INCLUDE | 5B.3 | {label} | — |\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lacks explanation"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_uses_prose_relevance_as_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    explanation = "Documents a quantified policy outcome and its qualification."
    payload = {
        "decisions": [
            {
                "chunk_id": "U0001",
                "decision": "include",
                "applicable_question_ids": ["5B.3"],
                "relevance": explanation,
            }
        ]
    }
    raw.write_text(json.dumps(payload), encoding="utf-8")

    result = normalize_routing_table(
        raw_path=raw, source=descriptor, chunk_ids=("U0001",)
    )

    assert result.decisions[0].explanation == explanation


@pytest.mark.parametrize(
    ("secondary_name", "secondary_value", "error"),
    [
        ("applicable_question_ids", ["5B.7"], "question ID aliases conflict"),
        ("applicable_question_ids", ["8B.1"], "non-5B IDs"),
        ("adjacent_context_needed", "Conflicting context.", "aliases conflict"),
    ],
)
def test_rejects_conflicting_or_invalid_secondary_alias(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    secondary_name: str,
    secondary_value: object,
    error: str,
) -> None:
    raw = tmp_path / "routing.json"
    row: dict[str, object] = {
        "chunk_id": "U0001",
        "decision": "include",
        "question_ids": ["5B.3"],
        "relevance": "include",
        "adjacent_context": "Primary context.",
        secondary_name: secondary_value,
    }
    raw.write_text(json.dumps({"decisions": [row]}), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


def test_disposition_relevance_is_not_an_explanation(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    row = {
        "chunk_id": "U0001",
        "decision": "include",
        "question_ids": ["5B.3"],
        "relevance": "include",
    }
    raw.write_text(json.dumps({"decisions": [row]}), encoding="utf-8")

    with pytest.raises(ValueError, match="lacks an explicit explanation"):
        normalize_routing_table(
            raw_path=raw, source=descriptor, chunk_ids=("U0001",)
        )


@pytest.mark.parametrize(
    "row",
    [
        {
            "chunk_id": "U0001",
            "decision": "exclude",
            "include": True,
            "question_ids": ["5B.3"],
            "relevant_facts": ["A fact."],
        },
        {
            "chunk_id": "U0001",
            "include": True,
            "relevance": "exclude",
            "question_ids": ["5B.3"],
            "relevant_facts": ["A fact."],
        },
    ],
)
def test_rejects_conflicting_disposition_aliases(
    tmp_path: Path,
    descriptor: SourceDescriptor,
    row: dict[str, object],
) -> None:
    raw = tmp_path / "routing.json"
    raw.write_text(json.dumps({"decisions": [row]}), encoding="utf-8")

    with pytest.raises(ValueError, match="aliases conflict"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001",),
        )


def test_rejects_lens_explanation_key_outside_question_ids(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    raw.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "chunk_id": "U0001",
                        "include": True,
                        "question_ids": ["5B.3"],
                        "relevant_facts": ["A valid fact explanation."],
                        "evidence_cited_lenses": {"5B.7": "Different lens."},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="disagree"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001",),
        )


def test_rejects_incomplete_m3_json(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    raw.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "chunk_id": "U0001",
                        "decision": "exclude",
                        "question_ids": [],
                        "relevance": "none",
                        "adjacent_context": "Administrative cover.",
                        "exclusion_reason": "No substantive evidence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="chunk set mismatch"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001", "U0002"),
        )


def test_rejects_conflicting_m3_json_disposition(
    tmp_path: Path,
    descriptor: SourceDescriptor,
) -> None:
    raw = tmp_path / "routing.json"
    raw.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "chunk_id": "U0001",
                        "decision": "include",
                        "question_ids": ["5B.3"],
                        "relevance": "none",
                        "adjacent_context": "Contradictory disposition.",
                        "exclusion_reason": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="decision and relevance conflict"):
        normalize_routing_table(
            raw_path=raw,
            source=descriptor,
            chunk_ids=("U0001",),
        )
