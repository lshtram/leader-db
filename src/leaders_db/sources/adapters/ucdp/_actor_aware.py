"""Read UCDP 26.1 country-year data without collapsing actor roles."""

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

CURRENT_COUNTRY_YEAR_ZIP = "organizedviolencecy-261-csv.zip"
CURRENT_VERSION = "Organized Violence 26.1"
CURRENT_ATTRIBUTION_TEXT = "UCDP Organized Violence 26.1 (UCDP 2026)."

# These are deliberately separate concepts. In particular, location totals
# and non-state killings must never be represented as government conduct.
_INDICATORS: tuple[tuple[str, str, str], ...] = (
    (
        "ucdp_state_intrastate_fatalities_best",
        "sb_intrastate_deaths_best",
        "international_peace_country_year",
    ),
    (
        "ucdp_state_interstate_fatalities_best",
        "sb_interstate_deaths_best",
        "international_peace_country_year",
    ),
    (
        "ucdp_nonstate_conflict_fatalities_best",
        "ns_total_deaths_best",
        "international_peace_country_year",
    ),
    (
        "ucdp_onesided_government_killings_best",
        "os_govt_killings_best",
        "domestic_violence_country_year",
    ),
    (
        "ucdp_onesided_any_government_killings_best",
        "os_any_govt_killings_best",
        "domestic_violence_country_year",
    ),
    (
        "ucdp_onesided_nonstate_killings_best",
        "os_nsgroup_killings_best",
        "domestic_violence_country_year",
    ),
    (
        "ucdp_onesided_location_deaths_best",
        "os_total_deaths_best",
        "domestic_violence_country_year",
    ),
)


def read_actor_aware_country_year(bundle_dir: Path) -> tuple[pd.DataFrame | None, Path | None]:
    """Return the staged 26.1 country-year frame when it is available."""
    path = bundle_dir / CURRENT_COUNTRY_YEAR_ZIP
    if not path.is_file():
        return None, None
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not members:
            raise KeyError(f"No CSV member found in {path}")
        with archive.open(members[0]) as handle:
            frame = pd.read_csv(handle, low_memory=False)
    required = {"country", "country_id", "year", "Version"}
    required.update(raw_column for _, raw_column, _ in _INDICATORS)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise KeyError(f"UCDP 26.1 country-year file is missing columns: {missing}")
    return frame, path


def emit_actor_aware_observations(
    frame: pd.DataFrame | None,
    request: SourceIngestRequest,
    asset_path: Path | None,
) -> Iterable[NormalizedObservation]:
    """Emit actor-aware observations with location and responsibility separate."""
    if frame is None or asset_path is None:
        return iter(())
    filtered = frame
    if request.years:
        filtered = filtered.loc[filtered["year"].astype(int).isin(request.years)]
    if request.countries:
        wanted = {int(value) for value in request.countries if str(value).isdigit()}
        filtered = (
            filtered.loc[filtered["country_id"].astype(int).isin(wanted)]
            if wanted
            else filtered.iloc[0:0]
        )

    observations: list[NormalizedObservation] = []
    for row_number, row in filtered.iterrows():
        country_id = int(row["country_id"])
        year = int(row["year"])
        for indicator_code, raw_column, family in _INDICATORS:
            value = pd.to_numeric(row[raw_column], errors="coerce")
            if pd.isna(value):
                continue
            rule_id = f"ucdp:{country_id}:{year}:{indicator_code}"
            prefix = raw_column.removesuffix("_best")
            extension: dict[str, Any] = {
                "attribution": CURRENT_ATTRIBUTION_TEXT,
                "source_row_reference": f"ucdp:{country_id}",
                "ucdp_country_id": country_id,
                "ucdp_country_name": str(row["country"]),
                "ucdp_raw_column": raw_column,
                "ucdp_semantic_role": (
                    "event_location"
                    if indicator_code.endswith("location_deaths_best")
                    else "government_actor_involved"
                    if "government_killings" in indicator_code
                    else "nonstate_perpetrator"
                    if "nonstate_killings" in indicator_code
                    else "conflict_exposure"
                ),
                "ucdp_dyad_names": _dyad_names(row, raw_column),
                "interpretation_warning": (
                    "Country-year location is not evidence that the ruler initiated, "
                    "perpetrated, or supported the violence. Use actor and dyad fields "
                    "for attribution."
                ),
                "higher_is_better": False,
            }
            for bound in ("low", "high"):
                bound_column = f"{prefix}_{bound}"
                if bound_column in row and not pd.isna(row[bound_column]):
                    extension[f"uncertainty_{bound}"] = float(row[bound_column])
            observations.append(
                NormalizedObservation(
                    source_id=request.source_id,
                    observation_id=rule_id,
                    observation_family=family,
                    indicator_code=indicator_code,
                    value=float(value),
                    value_type="numeric",
                    year=year,
                    country_code=str(country_id),
                    country_name=str(row["country"]),
                    leader_id=None,
                    leader_name=None,
                    unit="deaths",
                    scale="count",
                    source_version=CURRENT_VERSION,
                    raw_locator=RawLocator(
                        asset_id=f"ucdp:{CURRENT_COUNTRY_YEAR_ZIP}",
                        path=str(asset_path),
                        row_number=int(row_number) + 2,
                        column_name=raw_column,
                    ),
                    transform_locator=TransformLocator(
                        transform_name="ucdp_actor_aware_country_year_v1",
                        catalog_key="ucdp",
                        rule_id=rule_id,
                    ),
                    quality_flags=("ucdp_country_year_aggregate", "actor_role_preserved"),
                    extension=extension,
                )
            )
    return iter(observations)


def _dyad_names(row: pd.Series, raw_column: str) -> str | None:
    if raw_column.startswith("sb_intrastate"):
        value = row.get("sb_intrastate_dyad_names")
    elif raw_column.startswith("sb_interstate"):
        value = row.get("sb_interstate_dyad_names")
    elif raw_column.startswith("ns_"):
        value = row.get("ns_dyad_names")
    else:
        value = row.get("os_dyad_names")
    return None if pd.isna(value) else str(value)


__all__ = [
    "CURRENT_ATTRIBUTION_TEXT",
    "CURRENT_COUNTRY_YEAR_ZIP",
    "CURRENT_VERSION",
    "emit_actor_aware_observations",
    "read_actor_aware_country_year",
]
