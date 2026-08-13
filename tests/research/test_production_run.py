from pathlib import Path

from leaders_db.research.production_run import (
    build_production_run_manifest,
    load_production_run_manifest,
)


def test_production_run_binds_batch_release_and_all_stage_versions(
    tmp_path: Path,
) -> None:
    root = Path.cwd()
    output = root / "tmp" / "test-production-run.yaml"
    try:
        build_production_run_manifest(
            project_root=root,
            run_id="test-five-ruler-v1",
            batch_manifest_path=root
                / "configs/research-batches/2023-netanyahu-pilot.yaml",
            release_config_path=root
            / "configs/evidence-funnel/production-2023-v4.yaml",
            output_path=output,
        )
        manifest = load_production_run_manifest(output)
        assert manifest.target_year == 2023
        assert manifest.pipeline_provenance.release_id == "production-2023-v4"
        assert manifest.pipeline_provenance.methodology_freeze_sha256
        assert manifest.pipeline_provenance.methodology_aggregate_sha256 == (
            "12dc95bf8f8b7c967e0d445a8b79155f55e8149717ebf4b1456d1e0510a5ffef"
        )
        assert len(manifest.pipeline_provenance.stages) == 12
    finally:
        output.unlink(missing_ok=True)
