"""Dedicated model runner whose accepted extraction output is a citation ledger."""

from __future__ import annotations

import json
import sys
import time
from hashlib import sha256
from pathlib import Path

from leaders_db.research.codex_worker_command import build_codex_exec_command
from leaders_db.research.model_profiles import load_research_model_profiles

from .artifacts import ArtifactStore, sha256_file
from .calibration_prompts import (
    SHELL_SAFE_JSON_INSTRUCTION,
    citation_cli_instructions,
    extraction_prompt,
)
from .citation_ledger import CitationLedger
from .citation_models import LocatorIndex
from .cli_attempts import extraction_profiles, plan_cli_attempts
from .config import EvidenceFunnelConfig
from .execution import read_stage_usage
from .ingest import load_frozen_extractions
from .low_cost import EvidenceIntentBatch, LocatorDisposition
from .models import SourceDescriptor
from .process import run_isolated_process
from .sources import load_source_descriptors


def run_cli_extraction(
    *,
    project_root: Path,
    config_path: Path,
    frozen_root: Path,
    ledger_root: Path,
    config: EvidenceFunnelConfig,
    source: SourceDescriptor,
    locator_indexes: tuple[LocatorIndex, ...],
    questions: str,
    profiles_path: Path,
    stage_root: Path,
) -> tuple[EvidenceIntentBatch, str, int]:
    """Run M3/M2.7 and accept only confirmed, code-bound ledger records."""

    profiles = load_research_model_profiles(profiles_path).profiles
    command_prefix = [
        sys.executable,
        str(project_root / "scripts/experiments/run_citation_writer.py"),
        "--config",
        str(config_path.resolve()),
        "--frozen-root",
        str(frozen_root.resolve()),
        "--ledger",
        str(ledger_root.resolve()),
    ]
    extraction_request = extraction_prompt(
        instruction=config.prompts["extraction"],
        source=source,
        locator_indexes=locator_indexes,
        questions=questions,
    )
    failures: list[str] = []
    total_tokens = 0
    from .low_cost import LOW_COST_PROFILES

    plan = plan_cli_attempts(
        stage_root=stage_root,
        profile_names=extraction_profiles(config),
        interruption_retries=config.routing.extraction_validation_retries,
    )
    total_tokens += sum(
        _attempt_tokens(path / "events.jsonl") for path in plan.prior_roots
    )
    for _attempt, profile_name, selection in plan.attempts:
        if profile_name not in LOW_COST_PROFILES:
            raise ValueError(f"forbidden extraction profile: {profile_name}")
        attempt_root = selection.root
        if selection.exhausted:
            failures.append(f"{profile_name}: interrupted attempts exhausted")
            continue
        attempt_ledger = attempt_root / "ledger"
        command_prefix[-1] = str(attempt_ledger.resolve())
        tool_surface = (
            "the exact citation CLI prefix: "
            + " ".join(command_prefix)
            + "\nFor record, pass one compact JSON argument containing draft_id, "
            "source_id, locator, start_segment_id, end_segment_id, claim, actor, "
            "action, question_ids, claim_type, and polarity. Optional fields are "
            "dates, quantities, mechanism, outcome, attribution, period_fit, "
            "source_limitations (an array of strings), and "
            "premium_verification_required. dates and quantities are arrays of "
            "strings. claim_type is observed_fact, source_assertion, interpretation, "
            "allegation, legal_status, or recommendation. polarity is favorable, "
            "adverse, mixed, exculpatory, or context. "
            + SHELL_SAFE_JSON_INSTRUCTION
        )
        prompt = citation_cli_instructions(tool_surface) + "\n\n" + extraction_request
        binding_path = attempt_root / "input-binding.json"
        completion_path = attempt_root / "completion.json"
        binding = _input_binding(
            prompt=prompt,
            config_path=config_path,
            frozen_root=frozen_root,
            profiles_path=profiles_path,
            project_root=project_root,
        )
        if attempt_root.exists():
            if not binding_path.exists() or json.loads(
                binding_path.read_text(encoding="utf-8")
            ) != binding:
                raise ValueError(f"CLI extraction resume mismatch: {attempt_root}")
            if not completion_path.exists():
                raise ValueError(f"selected CLI attempt is incomplete: {attempt_root}")
            _validate_completion(attempt_root, attempt_ledger)
            batch = _read_completed_batch(
                attempt_ledger,
                locator_indexes,
                config,
                frozen_root,
            )
            return batch, profile_name, total_tokens
        attempt_root.mkdir(parents=True)
        ArtifactStore(attempt_root).write_immutable("input-binding.json", binding)
        _write_guard(attempt_root, project_root, command_prefix)
        events_path, stderr_path, final_path = (
            attempt_root / "events.jsonl",
            attempt_root / "stderr.txt",
            attempt_root / "ignored-final.txt",
        )
        command = build_codex_exec_command(
            profile=profiles[profile_name],
            project_root=attempt_root,
            schema_path=None,
            final_message_path=final_path,
            writable_dir=ledger_root,
        )
        command = _cli_only_command(command, profile_name)
        with (
            events_path.open("w", encoding="utf-8") as events,
            stderr_path.open("w", encoding="utf-8") as stderr,
        ):
            result = run_isolated_process(
                list(command),
                input_text=prompt,
                stdout=events,
                stderr=stderr,
                timeout=config.stages["extraction"].attempt_timeout_seconds,
            )
        total_tokens += _attempt_tokens(events_path)
        if result.returncode:
            failures.append(f"{profile_name}: process exit {result.returncode}")
            continue
        try:
            _reject_blocked_commands(stderr_path)
            batch = _read_after_process_exit(
                ledger_root=attempt_ledger,
                locator_indexes=locator_indexes,
                config=config,
                frozen_root=frozen_root,
            )
        except ValueError as exc:
            failures.append(f"{profile_name}: {exc}")
            continue
        ArtifactStore(attempt_root).write_immutable(
            "completion.json",
            _completion_payload(attempt_root, attempt_ledger),
        )
        return batch, profile_name, total_tokens
    raise RuntimeError("CLI extraction failed: " + " | ".join(failures))


def _cli_only_command(
    command: tuple[str, ...],
    profile_name: str,
) -> tuple[str, ...]:
    overrides: tuple[tuple[str, object], ...] = ()
    if profile_name == "minimax-m3-long-context":
        overrides += tuple(
            (f"mcp_servers.{name}.enabled", False)
            for name in ("minimax", "brave", "parallel", "fetch")
        )
    additions: list[str] = [
        "--dangerously-bypass-hook-trust",
        "--disable",
        "code_mode_host",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "multi_agent",
        "--disable",
        "goals",
    ]
    for key, value in overrides:
        additions.extend(("-c", f"{key}={json.dumps(value)}"))
    updated = list((*command[:2], *additions, *command[2:]))
    sandbox_index = updated.index("--sandbox") + 1
    updated[sandbox_index] = "danger-full-access"
    return tuple(updated)


def _write_guard(
    attempt_root: Path,
    project_root: Path,
    command_prefix: list[str],
) -> None:
    hook_command = " ".join(
        (
            sys.executable,
            str(project_root / "scripts/experiments/citation_command_guard.py"),
            "--allowed-prefix-json",
            repr(json.dumps(command_prefix)),
        )
    )
    ArtifactStore(attempt_root).write_immutable(
        ".codex/hooks.json",
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": hook_command,
                            }
                        ],
                    }
                ]
            }
        },
    )


def _read_completed_batch(
    ledger_root: Path,
    locator_indexes: tuple[LocatorIndex, ...],
    config: EvidenceFunnelConfig,
    frozen_root: Path,
) -> EvidenceIntentBatch:
    expected = {
        (item.source_id, item.locator, item.source_sha256)
        for item in locator_indexes
    }
    inspected = {
        (
            item.source_id,
            item.locator,
            item.source_sha256,
        )
        for path in (ledger_root / "inspections").glob("*.json")
        for item in (
            LocatorIndex.model_validate_json(path.read_text(encoding="utf-8")),
        )
    }
    if inspected != expected:
        raise ValueError(
            "inspection ledger does not exactly match the routed source locators"
        )
    extractions = load_frozen_extractions(
        frozen_root / "extracted",
        config.frozen_document_ids,
    )
    ledger = CitationLedger(
        root=ledger_root,
        extractions=extractions,
        sources=load_source_descriptors(
            extractions,
            frozen_root / "document_reader_experiment.json",
        ),
        segment_characters=config.citations.segment_characters,
        maximum_attempts=config.citations.maximum_binding_attempts,
    )
    intents = ledger.confirmed_intents()
    allowed_questions = set(config.methodology_ids)
    for intent in intents:
        if not set(intent.question_ids).issubset(allowed_questions):
            raise ValueError("confirmed intent contains an out-of-chapter question ID")
    evidence_locators = {intent.citation.locator for intent in intents}
    dispositions = tuple(
        LocatorDisposition(
            locator=locator,
            disposition=(
                "evidence_extracted"
                if locator in evidence_locators
                else "no_material_evidence"
            ),
            explanation=(
                "At least one CLI-confirmed evidence record."
                if locator in evidence_locators
                else "Inspected through the CLI; no evidence record was confirmed."
            ),
        )
        for locator in sorted(item[1] for item in expected)
    )
    return EvidenceIntentBatch(
        intents=intents,
        inspected_locator_count=len(inspected),
        locator_dispositions=dispositions,
    )


def _attempt_tokens(events_path: Path) -> int:
    if not events_path.exists():
        return 0
    usage = read_stage_usage(events_path)
    return usage.get("total_tokens", 0) or (
        usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    )


def _reject_blocked_commands(stderr_path: Path) -> None:
    stderr = stderr_path.read_text(encoding="utf-8")
    if "Command blocked by PreToolUse hook" in stderr:
        raise ValueError("citation CLI command was blocked by the command guard")


def _directory_sha256(root: Path) -> str:
    digest = sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _validate_completion(attempt_root: Path, ledger_root: Path) -> None:
    completion = json.loads(
        (attempt_root / "completion.json").read_text(encoding="utf-8")
    )
    expected = {
        "events_sha256": sha256_file(attempt_root / "events.jsonl"),
        "stderr_sha256": sha256_file(attempt_root / "stderr.txt"),
        "hooks_sha256": sha256_file(attempt_root / ".codex/hooks.json"),
        "ledger_sha256": _directory_sha256(ledger_root),
    }
    if any(completion.get(key) != value for key, value in expected.items()):
        raise ValueError(f"CLI extraction completion changed: {attempt_root}")


def _completion_payload(attempt_root: Path, ledger_root: Path) -> dict[str, str]:
    return {
        "schema_version": "cli_extraction_completion_v1",
        "events_sha256": sha256_file(attempt_root / "events.jsonl"),
        "stderr_sha256": sha256_file(attempt_root / "stderr.txt"),
        "hooks_sha256": sha256_file(attempt_root / ".codex/hooks.json"),
        "ledger_sha256": _directory_sha256(ledger_root),
    }


def _read_after_process_exit(
    *,
    ledger_root: Path,
    locator_indexes: tuple[LocatorIndex, ...],
    config: EvidenceFunnelConfig,
    frozen_root: Path,
) -> EvidenceIntentBatch:
    error: ValueError | None = None
    for retry in range(3):
        try:
            return _read_completed_batch(
                ledger_root,
                locator_indexes,
                config,
                frozen_root,
            )
        except ValueError as exc:
            error = exc
            if retry < 2:
                time.sleep(0.25)
    raise error or ValueError("citation ledger did not settle after process exit")


def _input_binding(
    *,
    prompt: str,
    config_path: Path,
    frozen_root: Path,
    profiles_path: Path,
    project_root: Path,
) -> dict[str, str]:
    contract_paths = (
        project_root / "scripts/experiments/citation_command_guard.py",
        project_root / "scripts/experiments/run_citation_writer.py",
        Path(__file__),
        project_root / "src/leaders_db/evidence_funnel/citation_ledger.py",
        project_root / "src/leaders_db/evidence_funnel/citation_index.py",
        project_root / "src/leaders_db/evidence_funnel/citation_models.py",
        project_root / "uv.lock",
    )
    return {
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "config_sha256": _file_sha256(config_path),
        "profiles_sha256": _file_sha256(profiles_path),
        "implementation_sha256": sha256(
            "".join(_file_sha256(path) for path in contract_paths).encode()
        ).hexdigest(),
        "python_version": sys.version,
        "frozen_root": str(frozen_root.resolve()),
    }


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


__all__ = ["run_cli_extraction"]
