from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from leaders_db.research.watchdog import (
    build_shard_status,
    record_shard_progress,
    validate_shard_output,
)


def test_missing_output_before_deadline_is_not_yet_stuck(tmp_path) -> None:
    started = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=tmp_path / "missing.json",
        expected_record_count=1,
        max_expected_minutes=30,
        now=started,
    )

    result = validate_shard_output(status, now=started + timedelta(minutes=5))

    assert result["status"] == "missing_output"
    assert result["validation_errors"][0]["code"] == "missing_output"


def test_missing_output_after_deadline_is_timed_out_or_stuck(tmp_path) -> None:
    started = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=tmp_path / "missing.json",
        expected_record_count=1,
        max_expected_minutes=30,
        now=started,
    )

    result = validate_shard_output(status, now=started + timedelta(minutes=31))

    assert result["status"] == "timed_out_or_stuck"


def test_missing_output_with_stale_progress_is_flagged_before_deadline(tmp_path) -> None:
    started = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=tmp_path / "missing.json",
        expected_record_count=1,
        max_expected_minutes=60,
        max_progress_stale_minutes=10,
        now=started,
    )

    result = validate_shard_output(status, now=started + timedelta(minutes=11))

    assert result["status"] == "progress_stale"
    assert result["validation_errors"][0]["code"] == "progress_stale"


def test_progress_heartbeat_prevents_stale_status(tmp_path) -> None:
    started = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=tmp_path / "missing.json",
        expected_record_count=1,
        max_expected_minutes=60,
        max_progress_stale_minutes=10,
        now=started,
    )
    status = record_shard_progress(
        status,
        message="searched observer reports",
        now=started + timedelta(minutes=8),
    )

    result = validate_shard_output(status, now=started + timedelta(minutes=12))

    assert result["status"] == "missing_output"
    assert result["progress_events"] == [
        {
            "at_utc": (started + timedelta(minutes=8)).isoformat(),
            "message": "searched observer reports",
        }
    ]


def test_valid_output_completes_shard(tmp_path) -> None:
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"records": [_record()]}), encoding="utf-8")
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=output_path,
        expected_record_count=1,
        max_expected_minutes=30,
    )

    result = validate_shard_output(status)

    assert result["status"] == "completed"
    assert result["observed_record_count"] == 1
    assert result["validation_errors"] == []


def test_wrong_record_count_fails_validation(tmp_path) -> None:
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"records": [_record()]}), encoding="utf-8")
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=output_path,
        expected_record_count=2,
        max_expected_minutes=30,
    )

    result = validate_shard_output(status)

    assert result["status"] == "record_count_mismatch"
    assert result["validation_errors"][0]["code"] == "record_count_mismatch"


def test_missing_required_keys_fail_validation(tmp_path) -> None:
    incomplete = _record()
    incomplete.pop("target_year_evidence")
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"records": [incomplete]}), encoding="utf-8")
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=output_path,
        expected_record_count=1,
        max_expected_minutes=30,
    )

    result = validate_shard_output(status)

    assert result["status"] == "missing_required_keys"
    assert result["validation_errors"][0] == {
        "code": "missing_required_keys",
        "record_index": 1,
        "missing": ["target_year_evidence"],
    }


def test_missing_citations_fail_validation(tmp_path) -> None:
    record = _record()
    record["citations"] = []
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps({"records": [record]}), encoding="utf-8")
    status = build_shard_status(
        input_path=tmp_path / "input.json",
        output_path=output_path,
        expected_record_count=1,
        max_expected_minutes=30,
    )

    result = validate_shard_output(status)

    assert result["status"] == "missing_citations"
    assert result["validation_errors"][0]["code"] == "missing_citations"


def _record() -> dict[str, object]:
    return {
        "iso3": "PRK",
        "country_name": "North Korea",
        "leader_id": "1437",
        "leader_name": "Kim Jong Un",
        "target_year_evidence": "Evidence summary.",
        "near_period_context": "Context summary.",
        "contrary_or_mitigating_evidence": "No mitigating evidence found.",
        "source_mix_note": "Structured, NGO, and official sources.",
        "caveats": ["Closed information environment."],
        "citations": [
            {
                "title": "Source",
                "url": "https://example.test/source",
                "source_role": "ngo",
                "publisher": "Publisher",
                "date_or_year": "2020",
                "supports": "Supports claim.",
            }
        ],
    }
