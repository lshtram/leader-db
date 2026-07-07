"""Bridge processed PTS country-year rows into normalized observations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from leaders_db.db.engine import build_engine
from leaders_db.db.session import default_sqlite_url
from leaders_db.normalize.countries import alias_to_iso3, normalize_country_name
from leaders_db.scope._country_seed import ISO3_COUNTRY_SEED
from leaders_db.sources.concepts import (
    PTS_AMNESTY_SCORE_INDICATOR_CODE,
    PTS_HUMAN_RIGHTS_WATCH_SCORE_INDICATOR_CODE,
    PTS_SOURCE_KEY,
    PTS_STATE_DEPT_SCORE_INDICATOR_CODE,
)
from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceId,
    TransformLocator,
)
from leaders_db.sources.country_codes import iso3_from_source_country

from .pts_io import default_processed_parquet_path

_PTS_INDICATOR_CODES: tuple[str, ...] = (
    PTS_AMNESTY_SCORE_INDICATOR_CODE,
    PTS_HUMAN_RIGHTS_WATCH_SCORE_INDICATOR_CODE,
    PTS_STATE_DEPT_SCORE_INDICATOR_CODE,
)
_COUNTRY_NAME_TO_ISO3: dict[str, str] = {
    normalize_country_name(country_name): iso3 for iso3, country_name in ISO3_COUNTRY_SEED
}


@dataclass(frozen=True)
class PtsNormalizedObservationResult:
    """Summary of a PTS normalized-observation bridge run."""

    rows_written: int
    rows_skipped_missing_value: int
    rows_unresolved_country: int


def write_pts_normalized_observations(
    *,
    engine: Engine | None = None,
    parquet_path: Path | None = None,
    source_version: str = "PTS-2025",
    replace_existing: bool = True,
) -> PtsNormalizedObservationResult:
    """Write PTS processed parquet rows to ``normalized_observations``.

    PTS Stage 2 historically wrote ``source_observations`` only. This bridge
    gives the concept publisher the same normalized-observation contract used by
    newer source adapters while preserving the legacy table for auditability.
    """

    db_engine = engine or build_engine(default_sqlite_url())
    df = pd.read_parquet(parquet_path or default_processed_parquet_path())
    observations: list[NormalizedObservation] = []
    skipped_missing = 0
    unresolved_country = 0
    for row in df.to_dict(orient="records"):
        year = _int_value(row.get("year"))
        country_name = _text_value(row.get("country"))
        cow_code = _text_value(row.get("cow_code"))
        country_code = _project_country_code(country_name, cow_code, year)
        if country_code is None:
            unresolved_country += len(_present_indicator_codes(row))
            continue
        for indicator_code in _PTS_INDICATOR_CODES:
            value = _int_value(row.get(indicator_code))
            if value is None:
                skipped_missing += 1
                continue
            observations.append(
                NormalizedObservation(
                    source_id=SourceId(slug=PTS_SOURCE_KEY),
                    observation_id=(
                        f"pts:{_observation_country_token(country_name, cow_code)}:"
                        f"{year}:{indicator_code}"
                    ),
                    observation_family="rights_country_year",
                    indicator_code=indicator_code,
                    value=value,
                    value_type="numeric",
                    year=year,
                    country_code=country_code,
                    country_name=country_name,
                    leader_id=None,
                    leader_name=None,
                    unit="ordinal_score",
                    scale="1-5_higher_worse",
                    source_version=source_version,
                    raw_locator=RawLocator(
                        asset_id="pts:PTS-2025.xlsx",
                        sheet="PTS-2025",
                        column_name=indicator_code,
                    ),
                    transform_locator=TransformLocator(
                        adapter_version="pts_normalized:v1",
                        transform_name="processed_pts_country_year_to_normalized_observations",
                    ),
                    quality_flags=(),
                    warnings=(),
                    extension={
                        "region": _text_value(row.get("region")),
                        "cow_code": cow_code,
                    },
                )
            )
    if replace_existing:
        with db_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM normalized_observations WHERE source_slug = :source_slug"),
                {"source_slug": PTS_SOURCE_KEY},
            )
    from leaders_db.research.sql_repository import write_observations

    write_observations(db_engine, observations)
    return PtsNormalizedObservationResult(
        rows_written=len(observations),
        rows_skipped_missing_value=skipped_missing,
        rows_unresolved_country=unresolved_country,
    )


def _present_indicator_codes(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        indicator_code
        for indicator_code in _PTS_INDICATOR_CODES
        if _int_value(row.get(indicator_code)) is not None
    )


def _project_country_code(
    country_name: str | None,
    cow_code: str | None,
    year: int | None,
) -> str | None:
    if country_name is not None:
        country_code = iso3_from_source_country(country_name, year=year)
        if country_code is not None:
            return country_code
        normalized_name = normalize_country_name(country_name)
        country_code = _COUNTRY_NAME_TO_ISO3.get(normalized_name) or alias_to_iso3(
            normalized_name
        )
        if country_code is not None:
            return country_code
    return iso3_from_source_country(cow_code, year=year)


def _observation_country_token(country_name: str | None, cow_code: str | None) -> str:
    if country_name is not None:
        return normalize_country_name(country_name).replace(" ", "_")
    if cow_code is not None:
        return cow_code.lower()
    return "unknown_country"


def _int_value(value: Any) -> int | None:
    if pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text_value(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


__all__ = ["PtsNormalizedObservationResult", "write_pts_normalized_observations"]
