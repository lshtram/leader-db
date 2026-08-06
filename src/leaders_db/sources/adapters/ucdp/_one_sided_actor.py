"""UCDP 26.1 one-sided-violence actor and location aggregates."""

from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceIngestRequest,
    TransformLocator,
)

ONE_SIDED_ZIP = "ucdp-onesided-261-csv.zip"
ONE_SIDED_VERSION = "One-sided Violence 26.1"
ONE_SIDED_ATTRIBUTION = "UCDP One-sided Violence 26.1 (UCDP 2026)."
_REQUIRED_COLUMNS = frozenset(
    {
        "conflict_id",
        "dyad_id",
        "actor_id",
        "actor_name",
        "year",
        "best_fatality_estimate",
        "low_fatality_estimate",
        "high_fatality_estimate",
        "is_government_actor",
        "location",
        "gwno_location",
        "gwnoa",
        "version",
    }
)


def read_one_sided_actor_year(
    bundle_dir: Path,
) -> tuple[pd.DataFrame | None, Path | None]:
    """Read the optional staged one-sided actor-year archive."""
    path = bundle_dir / ONE_SIDED_ZIP
    if not path.is_file():
        return None, None
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not members:
            raise KeyError(f"No CSV member found in {path}")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, low_memory=False)
    missing = sorted(_REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise KeyError(f"UCDP 26.1 one-sided file is missing columns: {missing}")
    return frame, path


def emit_one_sided_actor_observations(
    frame: pd.DataFrame | None,
    request: SourceIngestRequest,
    asset_path: Path | None,
) -> Iterable[NormalizedObservation]:
    """Emit separate government-actor, non-state, and location totals."""
    if frame is None or asset_path is None:
        return iter(())
    filtered = frame.copy()
    if request.years:
        filtered = filtered.loc[filtered["year"].astype(int).isin(request.years)]
    if request.countries:
        wanted = {str(value).strip() for value in request.countries}
        location_codes = filtered["gwno_location"].map(_numeric_code)
        actor_codes = filtered["gwnoa"].map(_numeric_code)
        filtered = filtered.loc[location_codes.isin(wanted) | actor_codes.isin(wanted)]

    observations: list[NormalizedObservation] = []
    government = filtered.loc[filtered["is_government_actor"].astype(int) == 1]
    for keys, rows in government.groupby(["year", "actor_id", "actor_name"], dropna=False):
        year, actor_id, actor_name = keys
        observations.append(
            _observation(
                request=request,
                asset_path=asset_path,
                indicator_code="ucdp_onesided_government_actor_killings_best",
                year=int(year),
                country_code=_single_code(rows["gwnoa"]),
                country_name=_government_country_name(str(actor_name)),
                group_key=f"actor:{int(actor_id)}",
                rows=rows,
                semantic_role="government_actor_perpetrator",
                actor_names=(str(actor_name),),
            )
        )

    nonstate = filtered.loc[filtered["is_government_actor"].astype(int) == 0]
    for keys, rows in nonstate.groupby(["year", "location"], dropna=False):
        year, location = keys
        observations.append(
            _observation(
                request=request,
                asset_path=asset_path,
                indicator_code="ucdp_onesided_nonstate_actor_killings_best",
                year=int(year),
                country_code=_single_code(rows["gwno_location"]),
                country_name=str(location),
                group_key=f"location:{_slug(str(location))}",
                rows=rows,
                semantic_role="nonstate_perpetrator_at_location",
                actor_names=tuple(sorted({str(value) for value in rows["actor_name"]})),
            )
        )

    for keys, rows in filtered.groupby(["year", "location"], dropna=False):
        year, location = keys
        observations.append(
            _observation(
                request=request,
                asset_path=asset_path,
                indicator_code="ucdp_onesided_location_killings_best",
                year=int(year),
                country_code=_single_code(rows["gwno_location"]),
                country_name=str(location),
                group_key=f"location:{_slug(str(location))}",
                rows=rows,
                semantic_role="event_location",
                actor_names=tuple(sorted({str(value) for value in rows["actor_name"]})),
            )
        )
    return iter(observations)


def _observation(
    *,
    request: SourceIngestRequest,
    asset_path: Path,
    indicator_code: str,
    year: int,
    country_code: str | None,
    country_name: str,
    group_key: str,
    rows: pd.DataFrame,
    semantic_role: str,
    actor_names: tuple[str, ...],
) -> NormalizedObservation:
    rule_id = f"ucdp:onesided:{year}:{group_key}:{indicator_code}"
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=rule_id,
        observation_family="domestic_violence_country_year",
        indicator_code=indicator_code,
        value=float(pd.to_numeric(rows["best_fatality_estimate"]).sum()),
        value_type="numeric",
        year=year,
        country_code=country_code,
        country_name=country_name,
        leader_id=None,
        leader_name=None,
        unit="deaths",
        scale="count",
        source_version=ONE_SIDED_VERSION,
        raw_locator=RawLocator(
            asset_id=f"ucdp:{ONE_SIDED_ZIP}",
            path=str(asset_path),
            column_name="best_fatality_estimate",
        ),
        transform_locator=TransformLocator(
            transform_name="ucdp_one_sided_actor_year_v1",
            catalog_key="ucdp",
            rule_id=rule_id,
        ),
        quality_flags=("ucdp_actor_year_aggregate", "actor_role_preserved"),
        extension={
            "attribution": ONE_SIDED_ATTRIBUTION,
            "ucdp_semantic_role": semantic_role,
            "ucdp_actor_names": actor_names,
            "ucdp_actor_ids": tuple(sorted({int(value) for value in rows["actor_id"]})),
            "ucdp_conflict_ids": tuple(sorted({int(value) for value in rows["conflict_id"]})),
            "ucdp_dyad_ids": tuple(sorted({int(value) for value in rows["dyad_id"]})),
            "uncertainty_low": float(pd.to_numeric(rows["low_fatality_estimate"]).sum()),
            "uncertainty_high": float(pd.to_numeric(rows["high_fatality_estimate"]).sum()),
            "interpretation_warning": (
                "Government-actor responsibility, non-state perpetration, and event "
                "location are separate. Location alone does not establish host-ruler "
                "responsibility; actor totals do not establish personal ruler direction."
            ),
            "higher_is_better": False,
        },
    )


def _government_country_name(actor_name: str) -> str:
    prefix = "Government of "
    return actor_name[len(prefix) :] if actor_name.startswith(prefix) else actor_name


def _numeric_code(value: Any) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "" if pd.isna(numeric) else str(int(numeric))


def _single_code(values: pd.Series) -> str | None:
    codes = sorted({_numeric_code(value) for value in values} - {""})
    return codes[0] if len(codes) == 1 else None


def _slug(value: str) -> str:
    return "-".join(value.casefold().split())


__all__ = [
    "ONE_SIDED_ATTRIBUTION",
    "ONE_SIDED_VERSION",
    "ONE_SIDED_ZIP",
    "emit_one_sided_actor_observations",
    "read_one_sided_actor_year",
]
