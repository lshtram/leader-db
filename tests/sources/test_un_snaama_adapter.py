"""UNSD SNAAMA clean-adapter contract tests."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from leaders_db.sources import SourceId, SourceIngestRequest
from leaders_db.sources.adapters.un_snaama import (
    ATTRIBUTION,
    UnSnaamaAdapter,
    register_un_snaama,
)
from leaders_db.sources.registry import InMemorySourceRegistry
from leaders_db.sources.runner import SourceIngestRunner


def _stage(root: Path) -> None:
    bundle = root / "un_snaama"
    bundle.mkdir()
    archive_path = bundle / "snaama_gdp_expenditure_current_usd.zip"
    rows = (
        '"Country or Area","Year","Item","Value"\n'
        '"Exampleland","2022","Gross Domestic Product (GDP)","1000"\n'
        '"Exampleland","2022","Final consumption expenditure","700"\n'
        '"Exampleland","2022","Household consumption expenditure '
        '(including Non-profit institutions serving households)","500"\n'
        '"Exampleland","2022","General government final consumption expenditure","200"\n'
        '"Exampleland","2022","Gross capital formation","300"\n'
        '"Exampleland","2022","Gross fixed capital formation '
        '(including Acquisitions less disposals of valuables)","250"\n'
        '"Otherland","2021","Gross Domestic Product (GDP)","900"\n'
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("export.csv", rows)
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    metadata = {
        "source_version": "UNdata export 2026-06-19",
        "checksum_sha256": {archive_path.name: checksum},
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_un_snaama_runs_end_to_end_with_exact_current_usd_semantics(tmp_path: Path) -> None:
    _stage(tmp_path)
    registry = InMemorySourceRegistry()
    register_un_snaama(registry)
    result = SourceIngestRunner(registry).run(
        SourceIngestRequest(
            source_id=SourceId(slug="un_snaama"),
            raw_root=tmp_path,
            years=(2022,),
            countries=("Exampleland",),
        )
    )

    assert result.validation.valid
    assert len(result.observations) == 6
    gdp = next(row for row in result.observations if row.indicator_code.endswith("gdp_current_usd"))
    assert gdp.value == 1000.0
    assert gdp.unit == "current_usd"
    assert gdp.scale == "total"
    assert gdp.extension["attribution"] == ATTRIBUTION
    assert "not a real-growth measure" in gdp.extension["interpretation_warning"]


def test_un_snaama_checksum_mismatch_blocks_before_read(tmp_path: Path) -> None:
    _stage(tmp_path)
    metadata_path = tmp_path / "un_snaama" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["checksum_sha256"]["snaama_gdp_expenditure_current_usd.zip"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    request = SourceIngestRequest(source_id=SourceId(slug="un_snaama"), raw_root=tmp_path)

    readiness = UnSnaamaAdapter().check_ready(request)

    assert not readiness.ready
    assert {error.code for error in readiness.errors} == {"checksum_mismatch"}
