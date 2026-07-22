from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from leaders_db.ingest.source_availability import (
    check_all_sources,
    write_source_readiness_report,
)


def _stage_wdi(tmp_path: Path, *, with_observations: bool = True) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    source_raw = raw / "world_bank_wdi"
    source_raw.mkdir(parents=True)
    (source_raw / "metadata.json").write_text('{"source_name": "WDI"}\n')
    (source_raw / "scores.xlsx").write_bytes(b"fixture")
    if with_observations:
        folder = processed / "world_bank_wdi"
        folder.mkdir(parents=True)
        parquet = folder / "observations-world-bank-wdi-test.parquet"
        pq.write_table(
            pa.table(
                {
                    "year": [2022, 2023],
                    "country_code": ["RUS", "USA"],
                    "observation_family": [
                        "economic_country_year",
                        "economic_country_year",
                    ],
                    "indicator_code": ["governance", "economy"],
                }
            ),
            parquet,
        )
        manifest = {
            "observation_count": 2,
            "coverage": {"years": [2022, 2023]},
            "output_assets": [{"path": str(parquet)}],
        }
        (folder / "manifest-world-bank-wdi-test.json").write_text(json.dumps(manifest))
    return raw, processed


def test_audit_calls_source_available_only_after_researcher_routing(tmp_path: Path) -> None:
    raw, processed = _stage_wdi(tmp_path)

    rows = check_all_sources(2023, raw_root=raw, processed_root=processed)
    bti = next(row for row in rows if row.source_slug == "world_bank_wdi")

    assert bti.observation_count == 2
    assert bti.country_count == 2
    assert (bti.year_min, bti.year_max) == (2022, 2023)
    assert bti.concept_mapped is True
    assert bti.researcher_routed is True
    assert bti.validated is True
    assert bti.available is True
    assert bti.blocking_issue == ""


def test_audit_exposes_first_real_blocker_instead_of_claiming_available(
    tmp_path: Path,
) -> None:
    raw, processed = _stage_wdi(tmp_path, with_observations=False)

    bti = next(
        row
        for row in check_all_sources(2023, raw_root=raw, processed_root=processed)
        if row.source_slug == "world_bank_wdi"
    )

    assert bti.raw_available is True
    assert bti.adapter_works is False
    assert bti.available is False
    assert bti.blocking_issue == "no successful processed manifest with observations"


def test_audit_includes_unregistered_local_source_and_writes_consistent_views(
    tmp_path: Path,
) -> None:
    raw, processed = _stage_wdi(tmp_path)
    local = raw / "unregistered_local"
    local.mkdir()
    (local / "metadata.json").write_text("{}")
    (local / "data.csv").write_text("value\n1\n")
    rows = check_all_sources(2023, raw_root=raw, processed_root=processed)

    unregistered = next(row for row in rows if row.source_slug == "unregistered_local")
    assert unregistered.identified is True
    assert unregistered.vetted is False
    assert unregistered.blocking_issue == (
        "clean adapter registration or valid local metadata is missing"
    )

    paths = write_source_readiness_report(rows, tmp_path / "outputs", target_year=2023)
    payload = json.loads(paths[0].read_text())
    assert payload["available_definition"] == "validated and researcher_routed"
    assert len(payload["sources"]) == len(rows)
    assert "unregistered_local" in paths[1].read_text()
    assert "unregistered_local" in paths[2].read_text()
