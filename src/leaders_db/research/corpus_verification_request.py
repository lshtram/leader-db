"""Versioned request binding for the existing corpus verification call."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .corpus_reader_models import BatchVerification, BoundEvidence, EvidenceCitation
from .corpus_verification import verification_prompt


def bind_verification_request(
    *,
    output_dir: Path,
    groups: tuple[tuple[BoundEvidence, ...], ...],
    candidates: dict[str, tuple[EvidenceCitation, ...]],
    profile_name: str,
    profile_config_sha256: str,
    model: str,
    create: bool,
) -> Path:
    """Create or exactly validate one verifier request/partition manifest."""

    schema = BatchVerification.model_json_schema()
    make_strict_response_schema(schema)
    path = output_dir / "request-manifest.json"
    manifest_exists = path.is_file()
    if create and not manifest_exists and (output_dir / "output.json").is_file():
        raise ValueError("verification output exists without a request binding")
    parts = []
    for number, group in enumerate(groups, start=1):
        directory = output_dir if len(groups) == 1 else output_dir / f"part-{number:03d}"
        prompt = verification_prompt(group, candidates)
        if create and not manifest_exists and (directory / "output.json").is_file():
            raise ValueError("verification output exists without a request binding")
        parts.append({
            "directory": "." if len(groups) == 1 else directory.name,
            "evidence_ids": [item.evidence_id for item in group],
            "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        })
        _validate_saved_transport(directory, prompt, schema)
    payload = {
        "schema_version": "corpus_verification_request_v1",
        "profile": profile_name,
        "profile_config_sha256": profile_config_sha256,
        "model": model,
        "response_schema_sha256": _payload_sha256(schema),
        "candidate_sha256": _payload_sha256({
            key: [item.model_dump(mode="json") for item in value]
            for key, value in candidates.items()
        }),
        "parts": parts,
    }
    if path.is_file():
        if json.loads(path.read_text(encoding="utf-8")) != payload:
            raise ValueError("persisted corpus verification request binding differs")
    elif create:
        output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        raise ValueError("corpus verification request binding is missing")
    return path


def load_bound_verification_result(
    *,
    output_dir: Path,
    groups: tuple[tuple[BoundEvidence, ...], ...],
    require_complete: bool,
) -> BatchVerification | None:
    """Rebuild one verifier result from its exact ordered request partitions."""

    verdicts = []
    missing = []
    for number, group in enumerate(groups, start=1):
        directory = output_dir if len(groups) == 1 else output_dir / f"part-{number:03d}"
        output_path = directory / "output.json"
        if not output_path.is_file():
            missing.append(output_path)
            continue
        result = BatchVerification.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )
        expected_ids = tuple(item.evidence_id for item in group)
        actual_ids = tuple(item.evidence_id for item in result.verdicts)
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
            raise ValueError("verification partition evidence IDs differ from its request")
        verdicts.extend(result.verdicts)
    if missing:
        if require_complete:
            raise ValueError("verification partition output is incomplete")
        return None
    combined = BatchVerification(verdicts=tuple(verdicts))
    root_path = output_dir / "output.json"
    if len(groups) > 1 and root_path.is_file():
        stored = BatchVerification.model_validate_json(root_path.read_text(encoding="utf-8"))
        if stored != combined:
            raise ValueError("combined verification output differs from its partitions")
    elif len(groups) > 1:
        if require_complete:
            raise ValueError("combined verification output is missing")
        return None
    return combined


def _validate_saved_transport(directory: Path, prompt: str, schema: dict) -> None:
    output = directory / "output.json"
    if not output.is_file():
        return
    prompt_path = directory / "prompt.txt"
    schema_path = directory / "schema.json"
    if not prompt_path.is_file() or prompt_path.read_text(encoding="utf-8") != prompt:
        raise ValueError("saved corpus verification prompt differs")
    if (
        not schema_path.is_file()
        or json.loads(schema_path.read_text(encoding="utf-8")) != schema
    ):
        raise ValueError("saved corpus verification schema differs")


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


__all__ = ["bind_verification_request", "load_bound_verification_result"]
