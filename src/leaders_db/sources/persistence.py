"""Persistence seams for normalized source observations."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.engine import Engine

from .contracts import NormalizedObservation, OutputFormat, RawAsset, SourceIngestRequest


class SourcePersistenceService:
    """Persist normalized observations through the shared SQL evidence store."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def persist_observations(
        self,
        request: SourceIngestRequest,
        observations: Sequence[NormalizedObservation],
        *,
        run_id: str,
        source_version: str | None,
    ) -> tuple[RawAsset, ...]:
        """Persist processed artifacts and DB rows idempotently."""

        output_assets = self.plan_output_assets(
            request,
            run_id=run_id,
            source_version=source_version,
        )
        _write_processed_observations(request, observations, output_assets)
        from leaders_db.research.sql_repository import write_observations

        write_observations(self._engine, observations)
        return output_assets

    def plan_output_assets(
        self,
        request: SourceIngestRequest,
        *,
        run_id: str,
        source_version: str | None,
    ) -> tuple[RawAsset, ...]:
        """Return processed observation assets that would be written."""

        return tuple(
            _output_asset(
                request,
                run_id=run_id,
                source_version=source_version,
                output_format=output_format,
            )
            for output_format in request.output_formats
        )


def _output_asset(
    request: SourceIngestRequest,
    *,
    run_id: str,
    source_version: str | None,
    output_format: OutputFormat,
) -> RawAsset:
    if output_format == "parquet":
        media_type = "application/vnd.apache.parquet"
    elif output_format == "csv":
        media_type = "text/csv"
    else:
        raise ValueError(f"Unsupported output format: {output_format!r}")
    path = (
        request.processed_root
        / request.source_id.slug
        / f"observations-{run_id}.{output_format}"
    )
    return RawAsset(
        asset_id=path.name,
        source_id=request.source_id,
        version=source_version,
        media_type=media_type,
        path=path,
        immutable=True,
    )


def _write_processed_observations(
    request: SourceIngestRequest,
    observations: Sequence[NormalizedObservation],
    output_assets: Sequence[RawAsset],
) -> None:
    import pandas as pd

    from leaders_db.research.sql_repository import observation_to_row

    source_dir = request.processed_root / request.source_id.slug
    source_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([observation_to_row(observation) for observation in observations])
    for asset in output_assets:
        if asset.path is None:
            raise ValueError(f"Processed output asset is missing a path: {asset.asset_id}")
        if asset.path.suffix == ".parquet":
            frame.to_parquet(asset.path, index=False)
        elif asset.path.suffix == ".csv":
            frame.to_csv(asset.path, index=False)
        else:
            raise ValueError(f"Unsupported processed output suffix: {asset.path.suffix!r}")


__all__ = ["SourcePersistenceService"]
