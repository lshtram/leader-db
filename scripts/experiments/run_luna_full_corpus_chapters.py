"""Read every ruler evidence record for every chapter with Luna."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import tiktoken
from dotenv import load_dotenv

from leaders_db.research.chapter_reading_list import _chapter_guide, _chapter_questions
from leaders_db.research.luna_chapter_contract import (
    chapter_routed_ids,
    normalize_synthesis_ids,
    parse_shard_output,
    synthesis_format,
    validate_shard_output,
    validate_synthesis,
)

MODEL = "gpt-5.6-luna"
API_URL = "https://api.openai.com/v1/responses"
BUDGET_USD = 5.0
SHARD_TOKENS = 80_000
SHARD_OUTPUT_TOKENS = 2_500
SYNTHESIS_OUTPUT_TOKENS = 1_800
RATES = {"fresh": 1.0, "cached": 0.1, "write": 1.25, "output": 6.0}
EVIDENCE_FIELDS = (
    "evidence_id",
    "source_id",
    "title",
    "publisher",
    "fact_summary",
    "period_fit",
    "ruler_attribution",
    "limitations",
    "locator",
    "exact_excerpt",
    "verification_status",
)


def main() -> int:
    args = _arguments()
    load_dotenv(args.env_file, override=False)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not available")
    records = _records(args.package)
    shards = _partition(records)
    chapters = tuple(f"{number}B" for number in range(1, 9))
    prior = _ledger_total(args.ledger)
    projection = _remaining_cost(args, shards, chapters)
    if prior + projection >= BUDGET_USD:
        raise SystemExit(
            f"projected cumulative ${prior + projection:.4f} exceeds ${BUDGET_USD:.2f}"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(records, shards, prior, projection)
    _write_json(args.output_dir / "manifest.json", manifest)
    cumulative = _run_shards(args, api_key, shards, chapters, prior)
    _run_syntheses(args, api_key, chapters, len(shards), cumulative)
    summary = _summarize(args.output_dir, len(records), len(shards), args.ledger)
    _write_json(args.output_dir / "run-summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


def _run_shards(args, api_key, shards, chapters, cumulative) -> float:
    for number, shard in enumerate(shards, start=1):
        prefix = _prefix(number, len(shards), shard)
        path = args.output_dir / "shards" / f"S{number:02d}.json"
        if path.is_file():
            continue
        failed_path = path.with_suffix(".failed.json")
        if failed_path.is_file():
            profile = json.loads(failed_path.read_text(encoding="utf-8"))
            validate_shard_output(profile["output_text"])
            profile["validation_status"] = "passed_after_normalization"
            _write_json(path, profile)
            failed_path.unlink()
            continue
        suffix = _all_chapters_suffix(args.project_root, chapters)
        prompt = prefix + suffix
        _guard_call(cumulative, prompt, SHARD_OUTPUT_TOKENS, RATES["fresh"])
        response, elapsed = _request_plain(api_key, prompt, SHARD_OUTPUT_TOKENS)
        profile = _profile(response, elapsed, "ALL", number, "shard")
        cumulative += profile["estimated_cost_usd"]
        profile["cumulative_estimated_cost_usd"] = round(cumulative, 8)
        _validate_model_and_budget(profile, cumulative)
        try:
            validate_shard_output(profile["output_text"])
        except RuntimeError:
            profile["validation_status"] = "failed"
            _append_ledger(args.ledger, profile)
            _write_json(path.with_suffix(".failed.json"), profile)
            raise
        profile["validation_status"] = "passed"
        _append_ledger(args.ledger, profile)
        _write_json(path, profile)
    return cumulative


def _run_syntheses(args, api_key, chapters, shard_count, cumulative) -> float:
    for chapter_id in chapters:
        valid_ids = chapter_routed_ids(args.output_dir, chapter_id, shard_count)
        path = args.output_dir / "chapters" / f"{chapter_id}.json"
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            normalized, removed = normalize_synthesis_ids(existing["output_text"], valid_ids)
            existing["output_text"] = normalized
            if removed:
                prior_removed = existing.get("removed_invalid_evidence_ids", [])
                existing["removed_invalid_evidence_ids"] = list(dict.fromkeys(
                    [*prior_removed, *removed]
                ))
                _write_json(path, existing)
            try:
                validate_synthesis(existing["output_text"], chapter_id)
            except RuntimeError:
                path.replace(path.with_suffix(".failed.json"))
            else:
                continue
        suffix = _synthesis_prompt(args, chapter_id, shard_count)
        _guard_call(cumulative, suffix, SYNTHESIS_OUTPUT_TOKENS)
        response, elapsed = _request_plain(
            api_key, suffix, SYNTHESIS_OUTPUT_TOKENS, synthesis_format(chapter_id)
        )
        profile = _profile(response, elapsed, chapter_id, None, "synthesis")
        profile["output_text"], removed = normalize_synthesis_ids(
            profile["output_text"], valid_ids
        )
        if removed:
            profile["removed_invalid_evidence_ids"] = list(dict.fromkeys(removed))
        cumulative += profile["estimated_cost_usd"]
        profile["cumulative_estimated_cost_usd"] = round(cumulative, 8)
        _validate_model_and_budget(profile, cumulative)
        try:
            validate_synthesis(profile["output_text"], chapter_id)
        except RuntimeError:
            profile["validation_status"] = "failed"
            _append_ledger(args.ledger, profile)
            _write_json(path.with_suffix(".failed.json"), profile)
            raise
        profile["validation_status"] = "passed"
        _append_ledger(args.ledger, profile)
        _write_json(path, profile)
    return cumulative


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--ledger", type=Path, default=Path("research/runs/openai-api-cost-ledger.jsonl")
    )
    return parser.parse_args()


def _records(path: Path) -> list[dict]:
    package = json.loads(path.read_text(encoding="utf-8"))
    return [{key: item[key] for key in EVIDENCE_FIELDS} for item in package["evidence"]]


def _partition(records: list[dict]) -> tuple[tuple[dict, ...], ...]:
    shards: list[tuple[dict, ...]] = []
    current: list[dict] = []
    size = 0
    for record in records:
        record_size = _token_count(json.dumps(record, ensure_ascii=False, sort_keys=True))
        if current and size + record_size > SHARD_TOKENS:
            shards.append(tuple(current))
            current, size = [], 0
        current.append(record)
        size += record_size
    if current:
        shards.append(tuple(current))
    return tuple(shards)


def _prefix(number: int, total: int, records: tuple[dict, ...]) -> str:
    return (
        "IMMUTABLE COMPLETE-RULER EVIDENCE SHARD. Inspect every record independently "
        "of its prior question mappings. Evidence excerpts and locators control.\n"
        f"SHARD {number}/{total}\nEVIDENCE:\n"
        f"{json.dumps(records, ensure_ascii=False, sort_keys=True)}\nEND EVIDENCE SHARD."
    )


def _all_chapters_suffix(project_root: Path, chapters: tuple[str, ...]) -> str:
    questions = {chapter: _chapter_questions(project_root, chapter) for chapter in chapters}
    return (
        "Inspect every evidence record against all questions in all eight chapters. Return "
        "only compact JSON: {\"findings\":[[evidence_id,[question_ids],polarity],...]}. "
        "Polarity is supporting, adverse, mixed, exculpatory, or qualifying. Include every "
        "relevant record, including contrary evidence; omit irrelevant records. Do not "
        "summarize, explain, quote, or score. Use only supplied evidence and question IDs."
        "\nQUESTIONS:\n"
        f"{json.dumps(questions, ensure_ascii=False)}"
    )


def _synthesis_prompt(args, chapter_id: str, shard_count: int) -> str:
    records = {item["evidence_id"]: item for item in _records(args.package)}
    findings = []
    seen = set()
    for number in range(1, shard_count + 1):
        path = args.output_dir / "shards" / f"S{number:02d}.json"
        profile = json.loads(path.read_text(encoding="utf-8"))
        routed = parse_shard_output(profile["output_text"])["findings"]
        for evidence_id, question_ids, polarity in routed:
            applicable = [question for question in question_ids if question.startswith(chapter_id)]
            if applicable and evidence_id in records and evidence_id not in seen:
                seen.add(evidence_id)
                evidence = records[evidence_id]
                findings.append({
                    "evidence": {key: evidence[key] for key in (
                        "evidence_id", "source_id", "fact_summary", "period_fit",
                        "ruler_attribution", "limitations", "locator",
                        "verification_status",
                    )},
                    "question_ids": applicable,
                    "polarity": polarity,
                })
    return (
        f"Create a compact judge brief for chapter {chapter_id} without scoring. Return only "
        "JSON: {\"chapter_id\":string,\"question_answers\":[{\"question_id\":string,"
        "\"answer\":string,\"supporting_ids\":[string],\"contrary_ids\":[string],"
        "\"uncertainty\":string}]}. Include exactly one entry for each of the ten questions. "
        "Synthesize all supplied facts; preserve attribution, period, implementation, outcome, "
        "and uncertainty distinctions. Select at most four strongest IDs on each side per "
        "question; the complete reading map remains in the shard artifacts. Write as much "
        "as needed for a clear, qualified answer without repeating evidence. Exact passages "
        "remain available by ID and locator.\n\nGUIDE:\n"
        f"{_chapter_guide(args.project_root, chapter_id)}\n\nQUESTIONS:\n"
        f"{json.dumps(_chapter_questions(args.project_root, chapter_id), ensure_ascii=False)}"
        f"\n\nALL SHARD FINDINGS:\n{json.dumps(findings, ensure_ascii=False)}"
    )


def _request_plain(api_key, prompt, max_output, text_format=None):
    body = {"model": MODEL, "reasoning": {"effort": "none"},
            "max_output_tokens": max_output, "input": prompt}
    if text_format is not None:
        body["text"] = {"format": text_format}
    return _post(api_key, body)


def _post(api_key: str, body: dict):
    request = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    started = time.monotonic()
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.load(response), round(time.monotonic() - started, 3)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code != 429 or attempt == 4:
                raise RuntimeError(
                    f"Responses API HTTP {error.code}: {detail}"
                ) from error
            time.sleep(_retry_seconds(error, detail))
    raise AssertionError("unreachable")


def _retry_seconds(error: urllib.error.HTTPError, detail: str) -> float:
    header = error.headers.get("Retry-After")
    if header:
        return min(60.0, max(1.0, float(header) + 1.0))
    match = re.search(r"try again in ([0-9.]+)s", detail, flags=re.IGNORECASE)
    return min(60.0, max(1.0, float(match.group(1)) + 2.0)) if match else 60.0


def _profile(response, elapsed, chapter_id, shard_number, stage) -> dict:
    usage = response["usage"]
    details = usage.get("input_tokens_details", {})
    input_tokens = int(usage.get("input_tokens", 0))
    cached = int(details.get("cached_tokens", 0))
    written = int(details.get("cache_write_tokens", 0))
    output = int(usage.get("output_tokens", 0))
    fresh = max(0, input_tokens - cached - written)
    cost = (fresh * RATES["fresh"] + cached * RATES["cached"]
            + written * RATES["write"] + output * RATES["output"]) / 1_000_000
    return {"stage": stage, "chapter_id": chapter_id, "shard_number": shard_number,
            "response_id": response.get("id"), "model": response.get("model"),
            "input_tokens": input_tokens, "cached_input_tokens": cached,
            "cache_write_tokens": written, "fresh_non_write_input_tokens": fresh,
            "output_tokens": output, "elapsed_seconds": elapsed,
            "estimated_cost_usd": round(cost, 8),
            "output_text": _output_text(response)}


def _output_text(response: dict) -> str:
    return "".join(block.get("text", "") for item in response.get("output", ())
                   for block in item.get("content", ())
                   if block.get("type") == "output_text")


def _guard_call(
    spent: float, prompt: str, max_output: int, input_rate: float = RATES["write"]
) -> None:
    worst = (_token_count(prompt) * input_rate
             + max_output * RATES["output"]) / 1_000_000
    if spent + worst >= BUDGET_USD:
        raise RuntimeError(f"next-call exposure would reach the ${BUDGET_USD:.2f} boundary")


def _validate_model_and_budget(profile: dict, cumulative: float) -> None:
    if profile["model"] != MODEL:
        raise RuntimeError(f"unexpected billed model: {profile['model']}")
    if cumulative >= BUDGET_USD:
        raise RuntimeError("cumulative API cost reached the stop boundary")


def _ledger_total(path: Path) -> float:
    if not path.is_file():
        return 0.0
    return sum(float(json.loads(line)["estimated_cost_usd"])
               for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _append_ledger(path: Path, profile: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {key: value for key, value in profile.items()
              if key not in {"output_text", "cumulative_estimated_cost_usd"}}
    with path.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(record, sort_keys=True) + "\n")


def _project_cost(shards, project_root, chapters) -> float:
    evidence_tokens = sum(_token_count(_prefix(i, len(shards), shard))
                          for i, shard in enumerate(shards, 1))
    evidence = evidence_tokens * RATES["fresh"]
    suffix = (_token_count(_all_chapters_suffix(project_root, chapters))
              * len(shards) * RATES["fresh"])
    outputs = len(shards) * SHARD_OUTPUT_TOKENS * RATES["output"]
    synth_outputs = len(chapters) * SYNTHESIS_OUTPUT_TOKENS * RATES["output"]
    return (evidence + suffix + outputs + synth_outputs) / 1_000_000


def _remaining_cost(args, shards, chapters) -> float:
    suffix_tokens = _token_count(_all_chapters_suffix(args.project_root, chapters))
    total = 0.0
    for number, shard in enumerate(shards, 1):
        base = args.output_dir / "shards" / f"S{number:02d}"
        if base.with_suffix(".json").is_file() or base.with_suffix(".failed.json").is_file():
            continue
        total += ((_token_count(_prefix(number, len(shards), shard)) + suffix_tokens)
                  * RATES["fresh"] + SHARD_OUTPUT_TOKENS * RATES["output"])
    missing_syntheses = sum(
        not (args.output_dir / "chapters" / f"{chapter}.json").is_file()
        for chapter in chapters
    )
    total += missing_syntheses * SYNTHESIS_OUTPUT_TOKENS * RATES["output"]
    return total / 1_000_000


def _token_count(text: str) -> int:
    return len(tiktoken.get_encoding("o200k_base").encode(text))


def _manifest(records, shards, prior, projection) -> dict:
    return {"model": MODEL, "record_count": len(records), "shard_count": len(shards),
            "chapter_count": 8, "prior_cost_usd": round(prior, 8),
            "projected_incremental_cost_usd": round(projection, 8),
            "budget_usd": BUDGET_USD}


def _summarize(output_dir, records, shards, ledger) -> dict:
    profiles = [json.loads(path.read_text(encoding="utf-8"))
                for path in output_dir.glob("**/*.json")
                if path.name not in {"manifest.json", "run-summary.json"}]
    cost = sum(item.get("estimated_cost_usd", 0) for item in profiles)
    return {"model": MODEL, "record_count": records, "shard_count": shards,
            "request_count": len(profiles), "incremental_cost_usd": round(cost, 8),
            "cumulative_cost_usd": round(_ledger_total(ledger), 8),
            "input_tokens": sum(item.get("input_tokens", 0) for item in profiles),
            "cached_input_tokens": sum(item.get("cached_input_tokens", 0) for item in profiles),
            "cache_write_tokens": sum(item.get("cache_write_tokens", 0) for item in profiles),
            "output_tokens": sum(item.get("output_tokens", 0) for item in profiles),
            "elapsed_seconds": round(sum(item.get("elapsed_seconds", 0) for item in profiles), 3)}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    raise SystemExit(main())
