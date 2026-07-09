from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.research.parallel_api import (
    PARALLEL_SEARCH_ENDPOINT,
    ParallelApiError,
    ParallelSearchRequest,
    call_parallel_search,
)

runner = CliRunner()


def test_parallel_search_api_constructs_official_request() -> None:
    captured: dict[str, Any] = {}

    def fake_opener(request: Any, *, timeout: float) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        captured["content_type"] = request.get_header("Content-type")
        captured["api_key"] = request.get_header("X-api-key")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {
                "search_id": "search_test",
                "results": [],
                "usage": [{"name": "sku_search", "count": 1}],
                "session_id": "session_test",
            }
        )

    payload, elapsed = call_parallel_search(
        ParallelSearchRequest(
            objective="Find election-observer evidence.",
            search_queries=["OSCE Belarus 2020 election report"],
        ),
        api_key="secret-test-key",
        timeout_seconds=12.5,
        opener=fake_opener,
    )

    assert captured == {
        "url": PARALLEL_SEARCH_ENDPOINT,
        "method": "POST",
        "timeout": 12.5,
        "content_type": "application/json",
        "api_key": "secret-test-key",
        "body": {
            "objective": "Find election-observer evidence.",
            "search_queries": ["OSCE Belarus 2020 election report"],
        },
    }
    assert payload["usage"] == [{"name": "sku_search", "count": 1}]
    assert elapsed >= 0


def test_parallel_search_cli_missing_key_fails_without_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from leaders_db import env as leaders_env

    leaders_env._LOADED = False
    monkeypatch.setenv("LEADERSDB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)

    result = runner.invoke(
        app,
        [
            "research",
            "parallel-search",
            "--objective",
            "Find evidence.",
            "--query",
            "election report",
            "--output",
            str(tmp_path / "parallel.json"),
            "--json",
        ],
    )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload == {"error": "PARALLEL_API_KEY is required in the environment or .env"}
    assert "secret" not in result.stdout.lower()


def test_parallel_search_api_http_error_is_clear_without_api_key() -> None:
    def fake_opener(request: Any, *, timeout: float) -> _FakeResponse:
        raise HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            hdrs={},
            fp=BytesIO(b'{"error":{"message":"rate limit exceeded for secret-test-key"}}'),
        )

    with pytest.raises(ParallelApiError) as exc_info:
        call_parallel_search(
            ParallelSearchRequest(search_queries=["Belarus election 2020"]),
            api_key="secret-test-key",
            timeout_seconds=3.0,
            opener=fake_opener,
        )

    assert str(exc_info.value) == (
        "Parallel Search API returned HTTP 429: rate limit exceeded for [REDACTED]"
    )
    assert exc_info.value.status_code == 429
    assert "secret-test-key" not in str(exc_info.value)


def test_parallel_search_api_timeout_url_error_is_clear_without_api_key() -> None:
    def fake_opener(request: Any, *, timeout: float) -> _FakeResponse:
        raise URLError(TimeoutError("secret-test-key timed out"))

    with pytest.raises(ParallelApiError) as exc_info:
        call_parallel_search(
            ParallelSearchRequest(search_queries=["Belarus election 2020"]),
            api_key="secret-test-key",
            timeout_seconds=3.0,
            opener=fake_opener,
        )

    assert str(exc_info.value) == "Parallel Search request timed out"
    assert "secret-test-key" not in str(exc_info.value)


def test_parallel_search_api_non_json_response_is_safe_without_body_leak() -> None:
    def fake_opener(request: Any, *, timeout: float) -> _FakeBytesResponse:
        return _FakeBytesResponse(b"not json secret-test-key")

    with pytest.raises(ParallelApiError) as exc_info:
        call_parallel_search(
            ParallelSearchRequest(search_queries=["Belarus election 2020"]),
            api_key="secret-test-key",
            timeout_seconds=3.0,
            opener=fake_opener,
        )

    assert str(exc_info.value) == "Parallel Search returned a non-JSON response"
    assert "not json" not in str(exc_info.value)
    assert "secret-test-key" not in str(exc_info.value)


def test_parallel_search_cli_writes_full_response_and_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from leaders_db import env as leaders_env

    output_path = tmp_path / "parallel-search.json"
    leaders_env._LOADED = False
    monkeypatch.setenv("LEADERSDB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PARALLEL_API_KEY", "secret-test-key")

    def fake_call(
        request: ParallelSearchRequest,
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> tuple[dict[str, Any], float]:
        assert request.objective == "Find election evidence."
        assert request.search_queries == ["OSCE Belarus 2020", "Belarus court election 2020"]
        assert api_key == "secret-test-key"
        assert timeout_seconds == 7.0
        return (
            {
                "search_id": "search_fixture",
                "results": [
                    {
                        "url": "https://example.test/report",
                        "title": "Election report",
                        "publish_date": "2020-12-01",
                        "excerpts": ["Fixture excerpt"],
                    }
                ],
                "usage": [{"name": "sku_search", "count": 1}],
                "session_id": "session_fixture",
            },
            0.4567,
        )

    monkeypatch.setattr("leaders_db.research.parallel_api.call_parallel_search", fake_call)

    result = runner.invoke(
        app,
        [
            "research",
            "parallel-search",
            "--objective",
            "Find election evidence.",
            "--query",
            "OSCE Belarus 2020",
            "--query",
            "Belarus court election 2020",
            "--output",
            str(output_path),
            "--timeout",
            "7",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["search_id"] == "search_fixture"
    assert saved["results"][0]["excerpts"] == ["Fixture excerpt"]
    assert saved["usage"] == [{"name": "sku_search", "count": 1}]
    summary = json.loads(result.stdout)
    assert summary == {
        "elapsed_seconds": 0.457,
        "output_path": str(output_path),
        "result_count": 1,
        "search_id": "search_fixture",
        "session_id": "session_fixture",
        "usage": [{"name": "sku_search", "count": 1}],
    }


def test_parallel_search_cli_failure_does_not_write_success_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from leaders_db import env as leaders_env

    output_path = tmp_path / "parallel-search.json"
    leaders_env._LOADED = False
    monkeypatch.setenv("LEADERSDB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("PARALLEL_API_KEY", "secret-test-key")

    def fake_call(
        request: ParallelSearchRequest,
        *,
        api_key: str,
        timeout_seconds: float,
    ) -> tuple[dict[str, Any], float]:
        raise ParallelApiError("Parallel Search request failed: network unavailable")

    monkeypatch.setattr("leaders_db.research.parallel_api.call_parallel_search", fake_call)

    result = runner.invoke(
        app,
        [
            "research",
            "parallel-search",
            "--objective",
            "Find election evidence.",
            "--query",
            "OSCE Belarus 2020",
            "--output",
            str(output_path),
            "--json",
        ],
    )

    assert result.exit_code == 1, result.stdout
    assert json.loads(result.stdout) == {
        "error": "Parallel Search request failed: network unavailable"
    }
    assert "secret-test-key" not in result.stdout
    assert not output_path.exists()


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeBytesResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeBytesResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
