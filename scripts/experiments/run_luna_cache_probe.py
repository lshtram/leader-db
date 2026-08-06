"""Run a two-request GPT-5.6 Luna explicit prompt-cache proof."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv

MODEL = "gpt-5.6-luna"
API_URL = "https://api.openai.com/v1/responses"
FRESH_INPUT_PER_MILLION = 1.00
CACHED_INPUT_PER_MILLION = 0.10
CACHE_WRITE_PER_MILLION = 1.25
OUTPUT_PER_MILLION = 6.00
MAX_BUDGET_USD = 5.00
MAX_OUTPUT_TOKENS = 200
MAX_PROBE_CHARS = 360_000


def main() -> int:
    args = _arguments()
    load_dotenv(args.env_file, override=False)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not available")
    evidence = _evidence_prefix(args.package)
    worst_case = _worst_case_cost(len(evidence), requests=2)
    prior_cost = _ledger_total(args.ledger)
    if prior_cost + worst_case >= MAX_BUDGET_USD:
        raise SystemExit(
            f"preflight total ${prior_cost + worst_case:.4f} exceeds budget"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_key = "leaders-db:cache-proof:" + sha256(evidence.encode()).hexdigest()[:40]
    profiles = []
    cumulative = prior_cost
    for chapter_id in ("1B", "2B"):
        response, elapsed = _request(api_key, evidence, chapter_id, cache_key)
        profile = _profile(response, chapter_id, elapsed)
        if profile["model"] != MODEL:
            raise RuntimeError(f"unexpected billed model: {profile['model']}")
        cumulative += profile["estimated_cost_usd"]
        profile["cumulative_estimated_cost_usd"] = round(cumulative, 8)
        if cumulative >= MAX_BUDGET_USD:
            raise RuntimeError("cumulative cost reached the $5 stop boundary")
        _append_ledger(args.ledger, profile)
        profiles.append(profile)
        (args.output_dir / f"{chapter_id}-profile.json").write_text(
            json.dumps(profile, indent=2) + "\n", encoding="utf-8"
        )
    result = {
        "model": MODEL,
        "cache_key_sha256": sha256(cache_key.encode()).hexdigest(),
        "evidence_chars": len(evidence),
        "budget_usd": MAX_BUDGET_USD,
        "worst_case_preflight_usd": round(worst_case, 8),
        "prior_ledger_cost_usd": round(prior_cost, 8),
        "probe_estimated_cost_usd": round(cumulative - prior_cost, 8),
        "cumulative_estimated_cost_usd": round(cumulative, 8),
        "profiles": profiles,
        "cache_pass": profiles[1]["cached_input_tokens"] >= (
            profiles[0]["cache_write_tokens"] * 0.9
        ),
    }
    (args.output_dir / "cache-probe-result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    return 0 if result["cache_pass"] else 2


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("research/runs/openai-api-cost-ledger.jsonl"),
    )
    return parser.parse_args()


def _evidence_prefix(package_path: Path) -> str:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    records = []
    size = 0
    for record in package["evidence"]:
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if records and size + len(encoded) > MAX_PROBE_CHARS:
            break
        records.append(record)
        size += len(encoded)
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return (
        "IMMUTABLE EVIDENCE CACHE PROBE. Read the complete evidence packet below. "
        "Use only supplied evidence IDs. This is a cache test, not a ruler score.\n\n"
        f"EVIDENCE:\n{payload}\n\nEND IMMUTABLE EVIDENCE."
    )


def _request(api_key: str, evidence: str, chapter_id: str, cache_key: str):
    suffix = (
        f"For chapter {chapter_id}, identify at most one materially relevant evidence ID "
        "from the packet and explain its relevance in one sentence. If none is relevant, "
        "say none. Do not score."
    )
    body = {
        "model": MODEL,
        "reasoning": {"effort": "none"},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "prompt_cache_key": cache_key,
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": evidence,
                        "prompt_cache_breakpoint": {"mode": "explicit"},
                    },
                    {"type": "input_text", "text": suffix},
                ],
            }
        ],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Responses API returned HTTP {error.code}: {detail}") from error
    return payload, round(time.monotonic() - started, 3)


def _profile(response: dict, chapter_id: str, elapsed: float) -> dict:
    usage = response["usage"]
    details = usage.get("input_tokens_details", {})
    input_tokens = int(usage.get("input_tokens", 0))
    cached = int(details.get("cached_tokens", 0))
    written = int(details.get("cache_write_tokens", 0))
    output = int(usage.get("output_tokens", 0))
    cost = _cost(input_tokens, cached, written, output)
    return {
        "chapter_id": chapter_id,
        "response_id": response.get("id"),
        "model": response.get("model"),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "cache_write_tokens": written,
        "fresh_non_write_input_tokens": max(0, input_tokens - cached - written),
        "output_tokens": output,
        "elapsed_seconds": elapsed,
        "estimated_cost_usd": round(cost, 8),
        "output_text": _output_text(response),
    }


def _output_text(response: dict) -> str:
    return "".join(
        block.get("text", "")
        for item in response.get("output", ())
        for block in item.get("content", ())
        if block.get("type") == "output_text"
    )


def _ledger_total(path: Path) -> float:
    if not path.is_file():
        return 0.0
    return sum(
        float(json.loads(line)["estimated_cost_usd"])
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _append_ledger(path: Path, profile: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        key: value
        for key, value in profile.items()
        if key not in {"output_text", "cumulative_estimated_cost_usd"}
    }
    with path.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(record, sort_keys=True) + "\n")


def _cost(input_tokens: int, cached: int, written: int, output: int) -> float:
    fresh = max(0, input_tokens - cached - written)
    return (
        fresh * FRESH_INPUT_PER_MILLION
        + cached * CACHED_INPUT_PER_MILLION
        + written * CACHE_WRITE_PER_MILLION
        + output * OUTPUT_PER_MILLION
    ) / 1_000_000


def _worst_case_cost(chars: int, *, requests: int) -> float:
    conservative_tokens = chars
    return requests * (
        conservative_tokens * CACHE_WRITE_PER_MILLION
        + MAX_OUTPUT_TOKENS * OUTPUT_PER_MILLION
    ) / 1_000_000


if __name__ == "__main__":
    raise SystemExit(main())
