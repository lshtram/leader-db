"""Version-bound manifest for the sole production ruler-quality pipeline."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .batch_manifest import load_batch_manifest
from .deep_corpus_release import load_deep_corpus_release, pipeline_provenance
from .pipeline_provenance import ProductionPipelineProvenance


class ProductionRunManifest(BaseModel):
    """Inputs and complete pipeline identity for one ruler/year production run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["production_run_manifest_v1"] = "production_run_manifest_v1"
    run_id: str = Field(min_length=1)
    target_year: int
    batch_manifest: str = Field(min_length=1)
    batch_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_config: str = Field(min_length=1)
    pipeline_provenance: ProductionPipelineProvenance


class ProductionRunReference(BaseModel):
    """Hash-bound reference copied into every result produced by the run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    batch_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_production_run_manifest(
    *,
    project_root: Path,
    run_id: str,
    batch_manifest_path: Path,
    release_config_path: Path,
    output_path: Path,
) -> Path:
    """Create the immutable provenance root required by all production stages."""

    root = project_root.resolve()
    batch = load_batch_manifest(batch_manifest_path)
    release = load_deep_corpus_release(release_config_path)
    if release.status != "production":
        raise ValueError("production run requires a production-status release")
    if release.target_year != batch.year:
        raise ValueError("production release and batch target years differ")
    manifest = ProductionRunManifest(
        run_id=run_id,
        target_year=batch.year,
        batch_manifest=str(batch_manifest_path.resolve().relative_to(root)),
        batch_manifest_sha256=batch.resolved_content_sha256,
        release_config=str(release_config_path.resolve().relative_to(root)),
        pipeline_provenance=pipeline_provenance(
            release_config_path, release, project_root=root
        ),
    )
    resolved_output = output_path.resolve()
    if not resolved_output.is_relative_to(root):
        raise ValueError("production run manifest must remain inside the project")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return resolved_output


def load_production_run_manifest(
    path: Path, *, project_root: Path | None = None
) -> ProductionRunManifest:
    """Load and, when rooted, revalidate one production-run version identity."""

    manifest = ProductionRunManifest.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if project_root is None:
        return manifest
    root = project_root.resolve()
    batch_path = (root / manifest.batch_manifest).resolve()
    release_path = (root / manifest.release_config).resolve()
    if not batch_path.is_relative_to(root) or not release_path.is_relative_to(root):
        raise ValueError("production-run inputs must remain inside the project")
    batch = load_batch_manifest(batch_path)
    if batch.resolved_content_sha256 != manifest.batch_manifest_sha256:
        raise ValueError("production-run batch changed after initialization")
    release = load_deep_corpus_release(release_path)
    expected = pipeline_provenance(release_path, release, project_root=root)
    if expected != manifest.pipeline_provenance:
        raise ValueError("production release or methodology changed after initialization")
    return manifest


def production_run_reference(
    path: Path, *, project_root: Path
) -> ProductionRunReference:
    """Create a project-local immutable reference to a validated run manifest."""

    root = project_root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("production-run manifest must remain inside the project")
    manifest = load_production_run_manifest(resolved, project_root=root)
    return ProductionRunReference(
        run_id=manifest.run_id,
        path=str(resolved.relative_to(root)),
        sha256=sha256(resolved.read_bytes()).hexdigest(),
        batch_manifest_sha256=manifest.batch_manifest_sha256,
    )


__all__ = [
    "ProductionRunManifest",
    "ProductionRunReference",
    "build_production_run_manifest",
    "load_production_run_manifest",
    "production_run_reference",
]
