"""Direct Parallel Search API client for restricted research workers."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

PARALLEL_SEARCH_ENDPOINT = "https://api.parallel.ai/v1/search"


class ParallelApiError(RuntimeError):
    """Raised when a Parallel API call cannot complete safely."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ParallelSearchRequest(BaseModel):
    """Request body for Parallel's v1 Search endpoint."""

    objective: str | None = None
    search_queries: list[str] = Field(min_length=1)


class ParallelSearchSummary(BaseModel):
    """Stable CLI summary for a persisted Parallel Search response."""

    output_path: str
    result_count: int
    usage: Any = None
    search_id: str | None = None
    session_id: str | None = None
    elapsed_seconds: float


UrlOpen = Callable[..., Any]


def call_parallel_search(
    request: ParallelSearchRequest,
    *,
    api_key: str,
    timeout_seconds: float,
    opener: UrlOpen = urlopen,
) -> tuple[dict[str, Any], float]:
    """Call Parallel Search and return the decoded response plus elapsed seconds.

    The API key is only placed in the outbound header and is never included in
    exceptions or returned payloads.
    """

    body = json.dumps(request.model_dump(exclude_none=True)).encode("utf-8")
    http_request = Request(
        PARALLEL_SEARCH_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with opener(http_request, timeout=timeout_seconds) as response:
            raw = response.read()
    except HTTPError as exc:
        raise ParallelApiError(
            _safe_http_error_message(exc, api_key=api_key),
            status_code=exc.code,
        ) from exc
    except TimeoutError as exc:
        message = f"Parallel Search request timed out after {timeout_seconds:g}s"
        raise ParallelApiError(message) from exc
    except URLError as exc:
        raise ParallelApiError(_safe_url_error_message(exc, api_key=api_key)) from exc
    elapsed_seconds = time.monotonic() - started

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParallelApiError("Parallel Search returned a non-JSON response") from exc
    if not isinstance(payload, dict):
        raise ParallelApiError("Parallel Search returned JSON that is not an object")
    return payload, elapsed_seconds


def write_parallel_search_response(
    payload: dict[str, Any],
    *,
    output_path: Path,
    elapsed_seconds: float,
) -> ParallelSearchSummary:
    """Persist a raw Parallel response and return a concise summary."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    results = payload.get("results")
    result_count = len(results) if isinstance(results, list) else 0
    search_id = payload.get("search_id")
    session_id = payload.get("session_id")
    return ParallelSearchSummary(
        output_path=str(output_path),
        result_count=result_count,
        usage=payload.get("usage"),
        search_id=search_id if isinstance(search_id, str) else None,
        session_id=session_id if isinstance(session_id, str) else None,
        elapsed_seconds=round(elapsed_seconds, 3),
    )


def _safe_http_error_message(exc: HTTPError, *, api_key: str) -> str:
    detail = _extract_error_detail(exc)
    if detail:
        detail = _redact_secret(detail, api_key)
        return f"Parallel Search API returned HTTP {exc.code}: {detail}"
    return f"Parallel Search API returned HTTP {exc.code}"


def _extract_error_detail(exc: HTTPError) -> str | None:
    try:
        raw = exc.read()
    except OSError:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(payload.get("message"), str):
            return payload["message"]
    return None


def _safe_url_error_message(exc: URLError, *, api_key: str) -> str:
    reason = exc.reason
    if isinstance(reason, TimeoutError):
        return "Parallel Search request timed out"
    if isinstance(reason, str) and reason:
        return f"Parallel Search request failed: {_redact_secret(reason, api_key)}"
    return "Parallel Search request failed"


def _redact_secret(message: str, secret: str) -> str:
    if not secret:
        return message
    return message.replace(secret, "[REDACTED]")


__all__ = [
    "PARALLEL_SEARCH_ENDPOINT",
    "ParallelApiError",
    "ParallelSearchRequest",
    "ParallelSearchSummary",
    "call_parallel_search",
    "write_parallel_search_response",
]
