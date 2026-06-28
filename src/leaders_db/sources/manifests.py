"""Manifest seams for unified source runs."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import SourceManifest


def manifest_path(processed_root: Path, manifest: SourceManifest) -> Path:
    """Return the canonical local manifest path for a source run."""

    return processed_root / manifest.source_id.slug / f"manifest-{manifest.run_id}.json"


def write_manifest(processed_root: Path, manifest: SourceManifest) -> Path:
    """Write a source-run manifest as deterministic JSON."""

    path = manifest_path(processed_root, manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest_payload(manifest)
    ensure_manifest_writable(processed_root, manifest)
    path.write_text(payload, encoding="utf-8")
    return path


def ensure_manifest_writable(processed_root: Path, manifest: SourceManifest) -> None:
    """Raise if writing ``manifest`` would mutate an existing immutable run."""

    path = manifest_path(processed_root, manifest)
    if path.exists() and path.read_text(encoding="utf-8") != manifest_payload(manifest):
        raise FileExistsError(f"Refusing to overwrite immutable source manifest: {path}")


def manifest_payload(manifest: SourceManifest) -> str:
    """Return deterministic JSON text for ``manifest``."""

    return json.dumps(_to_json(manifest), indent=2, sort_keys=True) + "\n"


def read_manifest(path: Path) -> dict[str, Any]:
    """Read a previously written manifest JSON payload."""

    return json.loads(path.read_text(encoding="utf-8"))


def _to_json(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _to_json(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple | list):
        return [_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    return value


__all__ = [
    "SourceManifest",
    "ensure_manifest_writable",
    "manifest_path",
    "manifest_payload",
    "read_manifest",
    "write_manifest",
]
