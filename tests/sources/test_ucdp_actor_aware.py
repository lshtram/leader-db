"""Actor-aware UCDP 26.1 regression tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from leaders_db.sources.adapters.ucdp._actor_aware import (
    emit_actor_aware_observations,
    read_actor_aware_country_year,
)
from leaders_db.sources.contracts import SourceId, SourceIngestRequest


def _stage_current_bundle(root: Path) -> Path:
    bundle = root / "ucdp"
    bundle.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {
                "country": "Exampleland",
                "country_id": 999,
                "year": 2022,
                "Version": 26.1,
                "sb_intrastate_deaths_best": 11,
                "sb_intrastate_deaths_low": 8,
                "sb_intrastate_deaths_high": 15,
                "sb_intrastate_dyad_names": "Government - Rebels",
                "sb_interstate_deaths_best": 2,
                "sb_interstate_deaths_low": 1,
                "sb_interstate_deaths_high": 3,
                "sb_interstate_dyad_names": "Exampleland - Neighbour",
                "ns_total_deaths_best": 7,
                "ns_total_deaths_low": 6,
                "ns_total_deaths_high": 9,
                "ns_dyad_names": "Group A - Group B",
                "os_govt_killings_best": 3,
                "os_govt_killings_low": 2,
                "os_govt_killings_high": 5,
                "os_any_govt_killings_best": 4,
                "os_any_govt_killings_low": 3,
                "os_any_govt_killings_high": 6,
                "os_nsgroup_killings_best": 20,
                "os_nsgroup_killings_low": 18,
                "os_nsgroup_killings_high": 25,
                "os_total_deaths_best": 24,
                "os_total_deaths_low": 21,
                "os_total_deaths_high": 31,
                "os_dyad_names": "Government; Armed group",
            }
        ]
    )
    path = bundle / "organizedviolencecy-261-csv.zip"
    csv = frame.to_csv(index=False).encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("OrganizedViolenceCYDataSet26_1.csv", csv)
    return path


def test_actor_roles_and_location_are_distinct(tmp_path: Path) -> None:
    path = _stage_current_bundle(tmp_path)
    frame, found_path = read_actor_aware_country_year(tmp_path / "ucdp")
    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=tmp_path,
        years=(2022,),
        countries=("999",),
    )

    observations = list(emit_actor_aware_observations(frame, request, found_path))
    values = {item.indicator_code: item for item in observations}

    assert found_path == path
    assert values["ucdp_onesided_government_killings_best"].value == 3.0
    assert values["ucdp_onesided_nonstate_killings_best"].value == 20.0
    location = values["ucdp_onesided_location_deaths_best"]
    assert location.value == 24.0
    assert location.extension["ucdp_semantic_role"] == "event_location"
    assert "not evidence that the ruler" in location.extension["interpretation_warning"]
    assert values["ucdp_onesided_government_killings_best"].extension["uncertainty_high"] == 5.0


def test_actor_aware_reader_is_optional(tmp_path: Path) -> None:
    frame, path = read_actor_aware_country_year(tmp_path)
    assert frame is None
    assert path is None


def test_actor_aware_filter_never_uses_future_year(tmp_path: Path) -> None:
    _stage_current_bundle(tmp_path)
    frame, path = read_actor_aware_country_year(tmp_path / "ucdp")
    request = SourceIngestRequest(source_id=SourceId(slug="ucdp"), raw_root=tmp_path, years=(2021,))
    assert list(emit_actor_aware_observations(frame, request, path)) == []
