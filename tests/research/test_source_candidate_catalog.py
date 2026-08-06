import json
from pathlib import Path

import pytest

from leaders_db.research.chapter_source_discovery import (
    _is_recoverable_discovery_output,
    _validate_discovery_depth,
)
from leaders_db.research.codex_worker import WorkerOutputError
from leaders_db.research.source_candidate_catalog import (
    read_source_candidate_catalog,
    recover_source_candidate_catalog,
    seed_source_candidate_catalog,
    write_source_candidate_catalog,
)


def _line(*, status: str, chapter: str) -> str:
    return "SOURCE_CANDIDATE_JSON: " + json.dumps(
        {
            "url": "https://EXAMPLE.test/report/#section",
            "title": "A report",
            "publisher": "Research institute",
            "document_type": "research_report",
            "access_status": status,
            "chapter_ids": [chapter],
            "likely_topics": ["implementation"],
            "discovery_query": "test query",
        }
    )


def test_candidate_catalog_deduplicates_and_preserves_cross_chapter_routing() -> None:
    notebook = _line(status="unopened", chapter="5B") + "\n" + _line(
        status="opened", chapter="8B"
    )

    catalog = recover_source_candidate_catalog(notebook)

    assert len(catalog.candidates) == 1
    candidate = catalog.candidates[0]
    assert candidate.url == "https://example.test/report"
    assert candidate.access_status == "opened"
    assert candidate.chapter_ids == ("5B", "8B")


def test_candidate_catalog_ignores_malformed_lines_and_writes_valid_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.json"

    write_source_candidate_catalog(
        "SOURCE_CANDIDATE_JSON: not-json\n" + _line(status="unopened", chapter="5B"),
        path,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "ruler_source_candidate_catalog_v1"
    assert len(payload["candidates"]) == 1


def test_candidate_catalog_updates_do_not_erase_existing_discovery(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    write_source_candidate_catalog(_line(status="unopened", chapter="5B"), path)

    write_source_candidate_catalog("No candidate lines in this extraction handoff", path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["candidates"]) == 1


def test_candidate_catalog_rejects_invalid_chapter_ids() -> None:
    malformed = _line(status="unopened", chapter="9B")

    assert recover_source_candidate_catalog(malformed).candidates == ()


def test_chapter_handoff_candidate_inherits_active_chapter() -> None:
    candidate = json.loads(_line(status="opened", chapter="5B").partition(":")[2])
    candidate.pop("chapter_ids")
    notebook = (
        "--- CHAPTER RESEARCH 7B ---\n"
        "SOURCE_CANDIDATE_JSON: " + json.dumps(candidate)
    )

    recovered = recover_source_candidate_catalog(notebook)

    assert recovered.candidates[0].chapter_ids == ("7B",)


def test_initial_candidate_inherits_matching_evidence_routes() -> None:
    candidate = json.loads(_line(status="opened", chapter="5B").partition(":")[2])
    candidate.pop("chapter_ids")
    claim = {
        "url": candidate["url"],
        "chapter_ids": ["2B", "8B"],
    }
    notebook = (
        "SOURCE_CLAIM_JSON: " + json.dumps(claim) + "\n"
        "SOURCE_CANDIDATE_JSON: " + json.dumps(candidate)
    )

    recovered = recover_source_candidate_catalog(notebook)

    assert recovered.candidates[0].chapter_ids == ("2B", "8B")


def test_catalogue_reader_preserves_valid_rows_when_one_route_is_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.json"
    valid = json.loads(_line(status="opened", chapter="5B").partition(":")[2])
    invalid = {**valid, "url": "https://example.test/unrouted", "chapter_ids": []}
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_source_candidate_catalog_v1",
                "candidates": [valid, invalid],
            }
        ),
        encoding="utf-8",
    )

    catalog = read_source_candidate_catalog(path)

    assert tuple(item.url for item in catalog.candidates) == (
        "https://EXAMPLE.test/report/#section",
    )


def test_catalogue_reader_still_rejects_non_route_corruption(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    invalid = json.loads(_line(status="opened", chapter="5B").partition(":")[2])
    invalid["access_status"] = "invented_status"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_source_candidate_catalog_v1",
                "candidates": [invalid],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="existing source candidate catalogue"):
        read_source_candidate_catalog(path)


def test_catalogue_reader_rejects_an_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps({"schema_version": "future_version", "candidates": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="existing source candidate catalogue"):
        read_source_candidate_catalog(path)


def test_candidate_catalog_removes_tracking_parameters() -> None:
    tracked = _line(status="unopened", chapter="5B").replace(
        "report/#section", "report/?utm_source=test&b=2&a=1#section"
    )

    candidate = recover_source_candidate_catalog(tracked).candidates[0]

    assert candidate.url == "https://example.test/report?a=1&b=2"


def test_discovery_depth_rejects_a_silent_shortfall(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    output = tmp_path / "handoff.md"
    write_source_candidate_catalog(_line(status="unopened", chapter="5B"), catalog)
    output.write_text("No blocker declared", encoding="utf-8")

    with pytest.raises(WorkerOutputError, match="expected at least 30"):
        _validate_discovery_depth(
            catalog, discovery_id="5B", minimum=30, output=output
        )


def test_completed_prose_only_discovery_is_not_recoverable(tmp_path: Path) -> None:
    output = tmp_path / "overview.md"
    output.write_text("A prose source landscape without candidate records.", encoding="utf-8")

    assert _is_recoverable_discovery_output(output, discovery_id="overview") is False


def test_completed_machine_readable_discovery_is_recoverable(tmp_path: Path) -> None:
    output = tmp_path / "overview.md"
    output.write_text(_line(status="unopened", chapter="5B"), encoding="utf-8")

    assert _is_recoverable_discovery_output(output, discovery_id="overview") is True


def test_discovery_depth_accepts_an_explicit_information_blocker(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    output = tmp_path / "handoff.md"
    write_source_candidate_catalog(_line(status="unopened", chapter="5B"), catalog)
    output.write_text(
        'DISCOVERY_SATURATION_BLOCKER_JSON: {"discovery_id":"5B",'
        '"searches_attempted":["archive query"],'
        '"limitation":"archive unavailable"}',
        encoding="utf-8",
    )

    _validate_discovery_depth(catalog, discovery_id="5B", minimum=30, output=output)


def test_prior_catalogues_seed_a_new_run_without_text_duplication(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    combined = tmp_path / "combined.json"
    write_source_candidate_catalog(_line(status="unopened", chapter="5B"), first)
    write_source_candidate_catalog(_line(status="rejected", chapter="8B"), second)

    seed_source_candidate_catalog((first, second), combined)

    candidate = json.loads(combined.read_text(encoding="utf-8"))["candidates"][0]
    assert candidate["access_status"] == "rejected"
    assert candidate["chapter_ids"] == ["5B", "8B"]


def test_accepted_candidate_requires_an_evidence_record_for_the_same_url() -> None:
    without_claim = recover_source_candidate_catalog(
        _line(status="accepted", chapter="5B")
    ).candidates[0]
    malformed_claim = 'SOURCE_CLAIM_JSON: {"url":"https://example.test/report"}'
    claim = "SOURCE_CLAIM_JSON: " + json.dumps(
        {
            "provisional_id": "E-1",
            "canonical_fact_key": "report-fact",
            "disposition": "accepted",
            "chapter_ids": ["5B"],
            "methodology_ids": [],
            "url": "https://example.test/report",
            "claim": "The report documents the policy.",
            "locator": "page 4",
        }
    )
    with_malformed_claim = recover_source_candidate_catalog(
        _line(status="accepted", chapter="5B") + "\n" + malformed_claim
    ).candidates[0]
    with_claim = recover_source_candidate_catalog(
        _line(status="accepted", chapter="5B") + "\n" + claim
    ).candidates[0]

    assert without_claim.access_status == "opened"
    assert with_malformed_claim.access_status == "opened"
    assert with_claim.access_status == "accepted"


def test_discovery_blocker_rejects_empty_search_entries(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    output = tmp_path / "output.md"
    write_source_candidate_catalog(_line(status="unopened", chapter="5B"), catalog)
    output.write_text(
        'DISCOVERY_SATURATION_BLOCKER_JSON: {"discovery_id":"5B",'
        '"searches_attempted":[null],"limitation":"unknown"}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="expected at least 30"):
        _validate_discovery_depth(catalog, discovery_id="5B", minimum=30, output=output)


def test_rejected_disposition_supersedes_opened(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    write_source_candidate_catalog(_line(status="opened", chapter="5B"), path)
    write_source_candidate_catalog(_line(status="rejected", chapter="5B"), path)

    candidate = json.loads(path.read_text(encoding="utf-8"))["candidates"][0]

    assert candidate["access_status"] == "rejected"


def test_invalid_existing_catalogue_stops_instead_of_being_replaced(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="existing source candidate catalogue"):
        write_source_candidate_catalog(_line(status="unopened", chapter="5B"), path)
