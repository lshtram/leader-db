"""Audit the AMLO source catalog without bypassing access restrictions."""

from __future__ import annotations

import argparse
import json
import re
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

from leaders_db.conversational_evidence.document_reader_experiment import (
    AccessAuditRecord,
    classify_access_response,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = (
    PROJECT_ROOT
    / "research/conversational-evidence/amlo-2022-5b-manual-deep-research-v1"
    / "accessible-source-universe.md"
)
USER_AGENT = "leaders-db-research-access-audit/0.1"
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
ROW_PATTERN = re.compile(r"^\| ([A-Z]+-[0-9]{3}) \|")


def main() -> None:
    """Write one access observation for every catalog row."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--sample-bytes", type=int, default=131_072)
    parser.add_argument("--retry-from", type=Path)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout <= 0 or args.sample_bytes < 1:
        raise ValueError("workers, timeout, and sample size must be positive")
    sources = parse_catalog(args.catalog)
    prior_by_id: dict[str, dict[str, object]] = {}
    if args.retry_from is not None:
        prior = json.loads(args.retry_from.read_text(encoding="utf-8"))
        prior_by_id = {str(item["source_id"]): item for item in prior["records"]}
        sources_to_audit = tuple(
            item
            for item in sources
            if prior_by_id.get(item["source_id"], {}).get("state") == "transient_failure"
        )
    else:
        sources_to_audit = sources
    robots = audit_robots(
        {urlparse(item["url"]).netloc for item in sources_to_audit},
        args.timeout,
    )
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        audited = list(
            pool.map(
                lambda item: audit_source(
                    item,
                    robots_allowed=robots.get(urlparse(item["url"]).netloc),
                    timeout=args.timeout,
                    sample_bytes=args.sample_bytes,
                ),
                sources_to_audit,
            )
        )
    audited_by_id = {str(item["source_id"]): item for item in audited}
    records = [
        audited_by_id.get(item["source_id"]) or prior_by_id.get(item["source_id"])
        for item in sources
    ]
    if any(item is None for item in records):
        raise ValueError("retry audit did not preserve every catalog row")
    payload = {
        "schema_version": "source_access_audit_v1",
        "catalog": str(args.catalog.resolve()),
        "user_agent": USER_AGENT,
        "records": records,
    }
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_catalog(path: Path) -> tuple[dict[str, str], ...]:
    """Parse stable IDs, links, and declared access labels from the Markdown catalog."""

    records: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        id_match = ROW_PATTERN.match(line)
        link_match = LINK_PATTERN.search(line)
        if not id_match or not link_match:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        access_index = 2 if id_match.group(1).startswith("ASF-") else 3
        records.append(
            {
                "source_id": id_match.group(1),
                "title": link_match.group(1),
                "url": link_match.group(2),
                "catalog_access": cells[access_index],
            }
        )
    if len(records) != len({item["source_id"] for item in records}):
        raise ValueError("catalog source IDs must be unique")
    return tuple(records)


def audit_robots(hosts: set[str], timeout: float) -> dict[str, bool | None]:
    """Read each host's robots policy once; unknown remains explicit."""

    results: dict[str, bool | None] = {}
    for host in sorted(hosts):
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(f"https://{host}/robots.txt")
        try:
            response = requests.get(
                parser.url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            if response.status_code >= 400:
                results[host] = None
                continue
            parser.parse(response.text.splitlines())
            results[host] = parser.can_fetch(USER_AGENT, f"https://{host}/")
        except requests.RequestException:
            results[host] = None
    return results


def audit_source(
    item: dict[str, str],
    *,
    robots_allowed: bool | None,
    timeout: float,
    sample_bytes: int,
) -> dict[str, object]:
    """Sample one source only when robots policy does not deny retrieval."""

    if robots_allowed is False:
        record = classify_access_response(
            source_id=item["source_id"],
            requested_url=item["url"],
            status_code=None,
            final_url=None,
            content_type=None,
            sampled_body=b"",
            robots_allowed=False,
        )
        return _serialize(item, record)
    try:
        with requests.get(
            item["url"],
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        ) as response:
            body = _read_sample(response, sample_bytes)
            record = classify_access_response(
                source_id=item["source_id"],
                requested_url=item["url"],
                status_code=response.status_code,
                final_url=response.url,
                content_type=response.headers.get("Content-Type"),
                sampled_body=body,
                robots_allowed=robots_allowed,
            )
    except requests.RequestException as exc:
        record = classify_access_response(
            source_id=item["source_id"],
            requested_url=item["url"],
            status_code=None,
            final_url=None,
            content_type=None,
            sampled_body=b"",
            robots_allowed=robots_allowed,
            error=f"{type(exc).__name__}: {exc}",
        )
    return _serialize(item, record)


def _read_sample(response: requests.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        remaining = limit - size
        chunks.append(chunk[:remaining])
        size += min(len(chunk), remaining)
        if size >= limit:
            break
    return b"".join(chunks)


def _serialize(item: dict[str, str], record: AccessAuditRecord) -> dict[str, object]:
    payload = record.model_dump(mode="json")
    payload.update(
        {
            "title": item["title"],
            "catalog_access": item["catalog_access"],
        }
    )
    return payload


if __name__ == "__main__":
    main()
