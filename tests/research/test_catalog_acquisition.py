from __future__ import annotations

import json
from pathlib import Path

import requests

from leaders_db.research.catalog_acquisition import (
    CatalogAcquisitionConfig,
    acquire_catalogue,
)


class _Response:
    def __init__(self, url: str, body: bytes, status: int = 200) -> None:
        self.url = url
        self.content = body
        self.status_code = status
        self.headers = {"Content-Type": "text/html"}

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield self.content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _catalogue(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "ruler_source_candidate_catalog_v1",
                "candidates": [
                    {
                        "url": "https://example.test/a",
                        "title": "A",
                        "publisher": "Publisher",
                        "document_type": "report",
                        "access_status": "unopened",
                        "chapter_ids": ["5B"],
                    },
                    {
                        "url": "https://example.test/b",
                        "title": "B",
                        "publisher": "Publisher",
                        "document_type": "report",
                        "access_status": "accepted",
                        "chapter_ids": ["6B"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_acquisition_dispositions_every_candidate_regardless_of_prior_status(
    tmp_path: Path, monkeypatch
) -> None:
    catalogue = tmp_path / "catalogue.json"
    _catalogue(catalogue)
    calls = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        return _Response(url, f"<html><body>{url} evidence</body></html>".encode())

    monkeypatch.setattr(requests, "get", fake_get)
    manifest_path = acquire_catalogue(
        catalogue,
        tmp_path / "run",
        config=CatalogAcquisitionConfig(workers=2, respect_robots_txt=False),
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert len(calls) == 2
    assert [record["status"] for record in manifest["records"]] == [
        "acquired",
        "acquired",
    ]
    assert all(record["raw_sha256"] for record in manifest["records"])
    assert all(record["estimated_tokens"] > 0 for record in manifest["records"])


def test_acquisition_resumes_terminal_records_without_refetch(
    tmp_path: Path, monkeypatch
) -> None:
    catalogue = tmp_path / "catalogue.json"
    _catalogue(catalogue)
    calls = 0

    def fake_get(url: str, **kwargs):
        nonlocal calls
        calls += 1
        return _Response(url, b"<html><body>evidence</body></html>")

    monkeypatch.setattr(requests, "get", fake_get)
    config = CatalogAcquisitionConfig(workers=1, respect_robots_txt=False)
    acquire_catalogue(catalogue, tmp_path / "run", config=config)
    acquire_catalogue(catalogue, tmp_path / "run", config=config)

    assert calls == 2


def test_acquisition_retries_transient_failures_and_persists_attempt_count(
    tmp_path: Path, monkeypatch
) -> None:
    catalogue = tmp_path / "catalogue.json"
    catalogue.write_text(
        json.dumps(
            {
                "schema_version": "ruler_source_candidate_catalog_v1",
                "candidates": [
                    {
                        "url": "https://example.test/retry",
                        "title": "Retry",
                        "publisher": "Publisher",
                        "document_type": "report",
                        "access_status": "unopened",
                        "chapter_ids": ["5B"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = 0

    def flaky_get(url: str, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise requests.Timeout("temporary")
        return _Response(url, b"<html><body>evidence</body></html>")

    monkeypatch.setattr(requests, "get", flaky_get)
    manifest_path = acquire_catalogue(
        catalogue,
        tmp_path / "run",
        config=CatalogAcquisitionConfig(
            workers=1,
            max_transient_attempts=3,
            respect_robots_txt=False,
        ),
    )
    record = json.loads(manifest_path.read_text(encoding="utf-8"))["records"][0]

    assert calls == 3
    assert record["status"] == "acquired"
    assert record["acquisition_attempts"] == 3
