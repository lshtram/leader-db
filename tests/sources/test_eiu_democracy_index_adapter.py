"""EIU Democracy Index clean-source adapter tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from leaders_db.sources import RawReadResult, SourceId, SourceIngestRequest
from leaders_db.sources.adapters.eiu_democracy_index import (
    EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT,
    EIU_DEMOCRACY_INDEX_DEFAULT_VERSION,
    EIU_DEMOCRACY_INDEX_INDICATORS,
    EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY,
    EIU_DEMOCRACY_INDEX_SOURCE_KEY,
    EiuDemocracyIndexTextPage,
    create_eiu_democracy_index_adapter,
    parse_eiu_democracy_index_rows,
    register_eiu_democracy_index,
)
from leaders_db.sources.adapters.eiu_democracy_index._constants import (
    EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH,
    EIU_DEMOCRACY_INDEX_MISSING_REQUESTED_PDF,
)
from leaders_db.sources.registry import InMemorySourceRegistry, build_default_source_registry
from leaders_db.sources.warnings import MISSING_RAW


def _stage_bundle(raw_root: Path, *, years: tuple[int, ...] = (2023, 2024)) -> Path:
    bundle = raw_root / EIU_DEMOCRACY_INDEX_SOURCE_KEY
    bundle.mkdir(parents=True, exist_ok=True)
    local_files = []
    checksums: dict[str, str] = {}
    for year in years:
        name = f"democracy-index-{year}.pdf"
        local_files.append(name)
        path = bundle / name
        path.write_bytes(b"%PDF-1.4\n% test placeholder\n")
        checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload: dict[str, Any] = {
        "source_name": "Economist Intelligence Unit Democracy Index",
        "source_version": EIU_DEMOCRACY_INDEX_DEFAULT_VERSION,
        "download_date": "2026-06-29",
        "coverage": "country-year democracy scores and regime types",
        "years_available": "2006, 2008, 2010-2019, 2021-2024 staged locally",
        "license_note": "User-managed copyrighted PDFs; do not redistribute raw reports.",
        "local_files": local_files,
        "missing_local_files": ["democracy-index-2020.pdf"],
        "not_expected_years": ["democracy-index-2007.pdf", "democracy-index-2009.pdf"],
        "ingestion_status": "downloaded_partial",
        "source_url": "https://www.eiu.com/n/global-themes/democracy-index/",
        "source_urls": {str(year): f"https://example.test/{year}.pdf" for year in years},
        "checksum_sha256": checksums,
    }
    (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def _request(raw_root: Path, **kwargs: Any) -> SourceIngestRequest:
    return SourceIngestRequest(
        source_id=SourceId(EIU_DEMOCRACY_INDEX_SOURCE_KEY),
        raw_root=raw_root,
        **kwargs,
    )


def test_descriptor_factory_and_default_registry_wiring() -> None:
    adapter = create_eiu_democracy_index_adapter()
    descriptor = adapter.descriptor
    assert descriptor.source_id.slug == EIU_DEMOCRACY_INDEX_SOURCE_KEY
    assert descriptor.source_type == "document"
    assert descriptor.requires_network is False
    assert descriptor.requires_manual_approval is True
    assert descriptor.supported_observation_families == (EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY,)

    registry = InMemorySourceRegistry()
    register_eiu_democracy_index(registry)
    assert registry.get_adapter(SourceId(EIU_DEMOCRACY_INDEX_SOURCE_KEY)).descriptor == descriptor
    assert (
        build_default_source_registry()
        .get_descriptor(
            SourceId(EIU_DEMOCRACY_INDEX_SOURCE_KEY),
        )
        .source_id.slug
        == EIU_DEMOCRACY_INDEX_SOURCE_KEY
    )


def test_parse_representative_table_row_with_rank_change_and_regime_type() -> None:
    text = """
    Overall Rank Change in rank I Electoral process II Functioning of government
    III Political participation IV Political culture V Civil liberties Regime type
    United States of America 7.85 29 1 9.17 6.43 8.89 6.25 8.53 Flawed democracy
    Norway 9.81 1 0 10.00 9.64 10.00 10.00 9.41 Full democracy
    """
    rows = parse_eiu_democracy_index_rows(text, page_number=11)
    assert len(rows) == 2
    row = rows[0]
    assert row.country_name == "United States of America"
    assert row.overall_score == 7.85
    assert row.rank == 29
    assert row.rank_change == 1
    assert row.electoral_process_pluralism == 9.17
    assert row.functioning_government == 6.43
    assert row.political_participation == 8.89
    assert row.political_culture == 6.25
    assert row.civil_liberties == 8.53
    assert row.regime_type == "Flawed democracy"
    assert row.page_number == 11


def test_readiness_years_none_skips_missing_2020_2007_2009(tmp_path: Path) -> None:
    _stage_bundle(tmp_path, years=(2006, 2008, 2010, 2023, 2024))
    readiness = create_eiu_democracy_index_adapter().check_ready(_request(tmp_path))
    assert readiness.ready is True
    assert readiness.errors == ()


def test_readiness_valid_checksum_map_passes_for_requested_pdf(tmp_path: Path) -> None:
    _stage_bundle(tmp_path, years=(2023, 2024))
    readiness = create_eiu_democracy_index_adapter().check_ready(
        _request(tmp_path, years=(2023,)),
    )
    assert readiness.ready is True
    assert readiness.errors == ()


def test_readiness_checksum_mismatch_reports_structured_error(tmp_path: Path) -> None:
    bundle = _stage_bundle(tmp_path, years=(2023, 2024))
    payload = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    payload["checksum_sha256"]["democracy-index-2023.pdf"] = "0" * 64
    (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")

    readiness = create_eiu_democracy_index_adapter().check_ready(
        _request(tmp_path, years=(2023,)),
    )

    assert readiness.ready is False
    assert readiness.errors[0].code == EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH
    assert readiness.errors[0].context["file"] == "democracy-index-2023.pdf"
    assert readiness.errors[0].context["expected_sha256"] == "0" * 64
    assert readiness.errors[0].context["actual_sha256"] != "0" * 64


def test_readiness_missing_checksum_entry_reports_structured_error(tmp_path: Path) -> None:
    bundle = _stage_bundle(tmp_path, years=(2023, 2024))
    payload = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    del payload["checksum_sha256"]["democracy-index-2023.pdf"]
    (bundle / "metadata.json").write_text(json.dumps(payload), encoding="utf-8")

    readiness = create_eiu_democracy_index_adapter().check_ready(
        _request(tmp_path, years=(2023,)),
    )

    assert readiness.ready is False
    assert readiness.errors[0].code == EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH
    assert readiness.errors[0].context["missing_checksum_files"] == ("democracy-index-2023.pdf",)


def test_readiness_missing_listed_pdf_still_reports_missing_raw(tmp_path: Path) -> None:
    bundle = _stage_bundle(tmp_path, years=(2023, 2024))
    (bundle / "democracy-index-2023.pdf").unlink()

    readiness = create_eiu_democracy_index_adapter().check_ready(
        _request(tmp_path, years=(2023,)),
    )

    assert readiness.ready is False
    assert readiness.errors[0].code == MISSING_RAW
    assert readiness.errors[0].context["missing_files"] == ("democracy-index-2023.pdf",)


def test_readiness_missing_requested_year_reports_structured_error(tmp_path: Path) -> None:
    _stage_bundle(tmp_path, years=(2023, 2024))
    readiness = create_eiu_democracy_index_adapter().check_ready(
        _request(tmp_path, years=(2020,)),
    )
    assert readiness.ready is False
    assert readiness.errors[0].code == EIU_DEMOCRACY_INDEX_MISSING_REQUESTED_PDF
    assert readiness.errors[0].context["missing_years"] == (2020,)


def test_transform_emits_observations_with_provenance() -> None:
    adapter = create_eiu_democracy_index_adapter()
    page = EiuDemocracyIndexTextPage(
        year=2023,
        path=Path("data/raw/eiu_democracy_index/democracy-index-2023.pdf"),
        page_number=41,
        source_url="https://example.test/2023.pdf",
        text=(
            "Overall Rank Change in rank I Electoral process II Functioning of government "
            "III Political participation IV Political culture V Civil liberties Regime type\n"
            "Freedonia 8.12 20 -2 9.58 7.50 8.33 7.50 8.24 Full democracy"
        ),
    )
    raw = RawReadResult(
        source_id=SourceId(EIU_DEMOCRACY_INDEX_SOURCE_KEY),
        payload={
            "metadata": {"source_version": EIU_DEMOCRACY_INDEX_DEFAULT_VERSION},
            "pages": (page,),
        },
    )
    observations = tuple(adapter.transform(_request(Path("data/raw")), raw))
    assert [obs.indicator_code for obs in observations] == list(EIU_DEMOCRACY_INDEX_INDICATORS)
    overall = observations[0]
    assert overall.source_id.slug == EIU_DEMOCRACY_INDEX_SOURCE_KEY
    assert overall.observation_family == EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY
    assert overall.year == 2023
    assert overall.country_name == "Freedonia"
    assert overall.country_code is None
    assert overall.value == 8.12
    assert overall.extension["raw_value"] == "8.12"
    assert overall.raw_locator.page_number == 41
    assert overall.raw_locator.path == "data/raw/eiu_democracy_index/democracy-index-2023.pdf"
    assert overall.extension["source_native_country_name"] == "Freedonia"
    assert overall.extension["source_key"] == EIU_DEMOCRACY_INDEX_SOURCE_KEY
    metadata_by_indicator = {
        obs.indicator_code: (obs.unit, obs.scale, obs.value_type) for obs in observations
    }
    assert metadata_by_indicator == {
        "eiu_democracy_index_overall_score": ("index_score", "0-10", "numeric"),
        "eiu_democracy_index_rank": ("rank", None, "numeric"),
        "eiu_democracy_index_rank_change": ("rank_change", None, "numeric"),
        "eiu_democracy_index_electoral_process_pluralism": (
            "index_score",
            "0-10",
            "numeric",
        ),
        "eiu_democracy_index_functioning_government": (
            "index_score",
            "0-10",
            "numeric",
        ),
        "eiu_democracy_index_political_participation": (
            "index_score",
            "0-10",
            "numeric",
        ),
        "eiu_democracy_index_political_culture": ("index_score", "0-10", "numeric"),
        "eiu_democracy_index_civil_liberties": ("index_score", "0-10", "numeric"),
        "eiu_democracy_index_regime_type": (None, None, "categorical"),
    }
    regime = observations[-1]
    assert regime.indicator_code == "eiu_democracy_index_regime_type"
    assert overall.extension["attribution"].endswith("report year 2023).")
    assert "{year}" not in overall.extension["attribution"]
    assert regime.value == "Full democracy"
    assert regime.value_type == "categorical"


def test_attribution_text_matches_attributions_doc() -> None:
    text = Path("docs/sources/attributions.md").read_text(encoding="utf-8")
    assert EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT in text
