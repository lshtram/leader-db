"""Parse and summarize one frozen deep-chapter prompt quality experiment."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

PREFIX = "SOURCE_CLAIM_JSON:"
REQUIRED_FIELDS = {
    "title",
    "publisher",
    "publication_date",
    "url",
    "claim",
    "locator",
    "provisional_id",
    "canonical_fact_key",
    "disposition",
    "chapter_ids",
    "methodology_ids",
    "source_type",
    "source_confidence",
    "source_confidence_reason",
    "final_evidence_use",
    "period_fit",
    "ruler_attribution",
    "contrary_evidence",
    "underlying_fact_key",
    "lenses",
}


def main() -> None:
    """Write parsed records and diagnostic metrics for v1 and v2."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--versions", nargs="+", default=("v1", "v2"))
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    summary: dict[str, Any] = {}
    for version in args.versions:
        run_dir = experiment_dir / version / "run-01"
        records, parse_errors = _parse_records(
            (run_dir / "output.md").read_text(encoding="utf-8")
        )
        (run_dir / "parsed-records.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        metrics = _metrics(records, parse_errors, run_dir / "events.jsonl")
        (run_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary[version] = metrics
    (experiment_dir / "metrics-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _parse_records(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith(PREFIX):
            continue
        try:
            value = json.loads(line.removeprefix(PREFIX).strip())
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number}: record is not an object")
            continue
        records.append(value)
    return records, errors


def _metrics(
    records: list[dict[str, Any]], parse_errors: list[str], events_path: Path
) -> dict[str, Any]:
    missing = [
        {
            "provisional_id": record.get("provisional_id"),
            "fields": sorted(REQUIRED_FIELDS - record.keys()),
        }
        for record in records
        if REQUIRED_FIELDS - record.keys()
    ]
    facts = Counter(str(record.get("underlying_fact_key", "")) for record in records)
    urls = Counter(str(record.get("url", "")) for record in records)
    families = Counter(str(record.get("publisher", "")) for record in records)
    methodologies = {
        str(methodology_id)
        for record in records
        for methodology_id in record.get("methodology_ids", [])
    }
    event_counts: Counter[str] = Counter()
    usage: dict[str, Any] = {}
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        event_type = str(event.get("type", "unknown"))
        item = event.get("item")
        if isinstance(item, dict):
            event_type = f"{event_type}:{item.get('type', 'unknown')}"
        event_counts[event_type] += 1
        if event.get("type") == "turn.completed":
            usage = event.get("usage", {})
    return {
        "record_count": len(records),
        "parse_errors": parse_errors,
        "records_missing_required_fields": missing,
        "unique_underlying_fact_keys": len([key for key in facts if key]),
        "repeated_underlying_fact_keys": {
            key: count for key, count in facts.items() if key and count > 1
        },
        "unique_urls": len([url for url in urls if url]),
        "reused_urls": {url: count for url, count in urls.items() if url and count > 1},
        "independent_publisher_labels": len([name for name in families if name]),
        "covered_methodology_ids": sorted(methodologies),
        "event_counts": dict(sorted(event_counts.items())),
        "usage": usage,
    }


if __name__ == "__main__":
    main()
