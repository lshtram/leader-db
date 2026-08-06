"""Immutable artifact persistence and hash-safe phase resumption."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .models import FunnelRunManifest, PhaseRecord


def canonical_json_bytes(value: BaseModel | Mapping[str, Any] | list[Any]) -> bytes:
    """Serialize one artifact deterministically for storage and hashing."""

    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest of bytes."""

    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash one file without loading it fully into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def combined_input_hash(inputs: Mapping[str, str]) -> str:
    """Bind stable input names to their individual hashes."""

    return sha256_bytes(canonical_json_bytes(dict(sorted(inputs.items()))))


class ArtifactConflictError(RuntimeError):
    """Raised when an immutable artifact path already has different content."""


class ResumeMismatchError(RuntimeError):
    """Raised when a completed phase no longer matches inputs or configuration."""


class ArtifactStore:
    """Write-once JSON store rooted in one run directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def write_immutable(self, relative_path: str, value: BaseModel | Mapping[str, Any]) -> str:
        """Write an artifact once, returning its content hash."""

        path = self._path(relative_path)
        content = canonical_json_bytes(value)
        digest = sha256_bytes(content)
        if path.exists():
            if sha256_file(path) != digest:
                raise ArtifactConflictError(f"immutable artifact differs: {relative_path}")
            return digest
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_suffix(path.suffix + ".pending")
        pending.write_bytes(content)
        os.replace(pending, path)
        return digest

    def write_manifest(self, manifest: FunnelRunManifest) -> None:
        """Atomically replace the mutable run manifest."""

        path = self._path("manifest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_suffix(".json.pending")
        pending.write_bytes(canonical_json_bytes(manifest))
        os.replace(pending, path)

    def load_manifest(self) -> FunnelRunManifest | None:
        """Load the manifest when this run has already started."""

        path = self._path("manifest.json")
        if not path.exists():
            return None
        return FunnelRunManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def assert_resumable(
        self,
        manifest: FunnelRunManifest,
        phase: str,
        *,
        input_hash: str,
        config_hash: str,
    ) -> bool:
        """Return true for a matching completed phase, otherwise require execution."""

        record = manifest.phases.get(phase)
        if record is None or record.status != "completed":
            return False
        if manifest.config_sha256 != config_hash:
            raise ResumeMismatchError("run manifest does not match current configuration")
        if record.input_hash != input_hash or record.config_hash != config_hash:
            raise ResumeMismatchError(
                f"completed phase {phase!r} does not match current inputs/config"
            )
        for relative_path, expected_hash in zip(
            record.output_paths, record.output_hashes, strict=True
        ):
            path = self._path(relative_path)
            if not path.exists() or sha256_file(path) != expected_hash:
                raise ResumeMismatchError(f"completed phase output changed: {relative_path}")
        return True

    def completed_record(
        self,
        *,
        input_hash: str,
        config_hash: str,
        output_paths: tuple[str, ...],
        started_at: datetime,
        attempts: int,
    ) -> PhaseRecord:
        """Build a completion marker after validating every output."""

        hashes = tuple(sha256_file(self._path(path)) for path in output_paths)
        return PhaseRecord(
            status="completed",
            input_hash=input_hash,
            config_hash=config_hash,
            output_paths=output_paths,
            output_hashes=hashes,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            attempts=attempts,
        )

    def _path(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("artifact path escapes the run directory")
        return path


__all__ = [
    "ArtifactConflictError",
    "ArtifactStore",
    "ResumeMismatchError",
    "canonical_json_bytes",
    "combined_input_hash",
    "sha256_bytes",
    "sha256_file",
]
