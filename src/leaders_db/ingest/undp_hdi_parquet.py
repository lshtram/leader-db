"""Stage 2 -- UNDP HDI parquet writer."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .undp_hdi_io import (
    UNDP_HDI_ATTRIBUTION,
    UNDP_HDI_SOURCE_KEY,
    default_processed_parquet_path,
)

_logger = logging.getLogger(__name__)

_PARQUET_META_ATTRIBUTION: str = "undp_hdi_attribution"
_PARQUET_META_SOURCE_KEY: str = "undp_hdi_source_key"


def write_undp_hdi_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the narrow frame as parquet with attribution metadata."""
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or UNDP_HDI_ATTRIBUTION
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach UNDP HDI attribution and source key to parquet metadata."""
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = UNDP_HDI_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        _logger.warning(
            "Failed to attach UNDP HDI attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = ["write_undp_hdi_parquet"]
