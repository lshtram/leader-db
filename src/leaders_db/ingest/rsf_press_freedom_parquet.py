"""Stage 2 -- RSF World Press Freedom Index: parquet writer."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .rsf_press_freedom_io import (
    RSF_PRESS_FREEDOM_ATTRIBUTION,
    RSF_PRESS_FREEDOM_SOURCE_KEY,
    default_processed_parquet_path,
)

_logger = logging.getLogger(__name__)

_PARQUET_META_ATTRIBUTION: str = "rsf_press_freedom_attribution"
_PARQUET_META_SOURCE_KEY: str = "rsf_press_freedom_source_key"


def write_rsf_press_freedom_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the narrow frame as parquet with attribution metadata.

    Mirrors the V-Dem / WGI / UCDP / SIPRI milex / SIPRI Yearbook
    Ch.7 / PTS / UNDP HDI parquet writers: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the RSF
    attribution + source key attached as file-level schema metadata
    (Always-On Rule #15). Best-effort on the metadata rewrite -- if
    pyarrow fails, the data parquet is still valid and a warning is
    logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or RSF_PRESS_FREEDOM_ATTRIBUTION,
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the RSF attribution + source key to the parquet metadata."""
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = RSF_PRESS_FREEDOM_SOURCE_KEY.encode(
            "utf-8",
        )
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the
        # audit metadata is lost. Log and continue -- the attribution
        # is also carried in the run manifest, so the audit trail
        # survives.
        _logger.warning(
            "Failed to attach RSF attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit "
            "fallback.",
            parquet_path,
            exc,
        )


__all__ = ["write_rsf_press_freedom_parquet"]
