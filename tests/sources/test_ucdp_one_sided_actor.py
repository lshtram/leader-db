"""UCDP one-sided actor-responsibility regression tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from leaders_db.sources.adapters.ucdp._one_sided_actor import (
    emit_one_sided_actor_observations,
    read_one_sided_actor_year,
)
from leaders_db.sources.contracts import SourceId, SourceIngestRequest


def _stage_bundle(root: Path) -> Path:
    bundle = root / "ucdp"
    bundle.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            _row(actor_id=6, actor="Government of Exampleland", government=1, best=7),
            _row(actor_id=6, actor="Government of Exampleland", government=1, best=3),
            _row(actor_id=99, actor="Example Rebels", government=0, best=20),
        ]
    )
    path = bundle / "ucdp-onesided-261-csv.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("OneSided_v26_1.csv", frame.to_csv(index=False).encode())
    return path


def _row(*, actor_id: int, actor: str, government: int, best: int) -> dict[str, object]:
    return {
        "conflict_id": actor_id + 400,
        "dyad_id": actor_id + 900,
        "actor_id": actor_id,
        "coalition_components": "",
        "actor_name": actor,
        "actor_name_fulltext": actor,
        "actor_name_mothertongue": "n/a",
        "year": 2022,
        "best_fatality_estimate": best,
        "low_fatality_estimate": best - 1,
        "high_fatality_estimate": best + 2,
        "is_government_actor": government,
        "location": "Exampleland",
        "gwno_location": 999,
        "gwnoa": 999 if government else None,
        "region": 1,
        "version": "26.1",
    }


def test_one_sided_actor_roles_remain_separate(tmp_path: Path) -> None:
    path = _stage_bundle(tmp_path)
    frame, found_path = read_one_sided_actor_year(tmp_path / "ucdp")
    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=tmp_path,
        years=(2022,),
    )

    rows = list(emit_one_sided_actor_observations(frame, request, found_path))
    by_indicator = {row.indicator_code: row for row in rows}

    assert found_path == path
    government = by_indicator["ucdp_onesided_government_actor_killings_best"]
    nonstate = by_indicator["ucdp_onesided_nonstate_actor_killings_best"]
    location = by_indicator["ucdp_onesided_location_killings_best"]
    assert government.value == 10.0
    assert government.country_code == "999"
    assert government.country_name == "Exampleland"
    assert government.extension["ucdp_semantic_role"] == "government_actor_perpetrator"
    assert government.extension["ucdp_actor_names"] == ("Government of Exampleland",)
    assert nonstate.value == 20.0
    assert nonstate.country_code == "999"
    assert nonstate.extension["ucdp_semantic_role"] == "nonstate_perpetrator_at_location"
    assert location.value == 30.0
    assert location.country_code == "999"
    assert location.extension["ucdp_semantic_role"] == "event_location"
    assert location.value != government.value


def test_one_sided_actor_reader_is_optional(tmp_path: Path) -> None:
    frame, path = read_one_sided_actor_year(tmp_path)
    assert frame is None
    assert path is None


def test_one_sided_actor_filter_excludes_future_rows(tmp_path: Path) -> None:
    _stage_bundle(tmp_path)
    frame, path = read_one_sided_actor_year(tmp_path / "ucdp")
    request = SourceIngestRequest(
        source_id=SourceId(slug="ucdp"),
        raw_root=tmp_path,
        years=(2021,),
    )
    assert list(emit_one_sided_actor_observations(frame, request, path)) == []
