from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from leaders_db.research.batch_manifest import (
    ResearchBatchCase,
    ResearchBatchManifest,
    compute_resolved_content_sha256,
    load_batch_manifest,
    validate_batch_manifest_cases,
)
from leaders_db.research.local_prior_slice import LocalPriorSliceCase

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "configs/research-batches/2020-diverse-20.yaml"


def test_repository_diverse_20_manifest_loads_with_frozen_identities() -> None:
    manifest = load_batch_manifest(MANIFEST_PATH)

    assert manifest.schema_version == "research_batch_manifest_v1"
    assert manifest.version == 1
    assert manifest.batch_id == "2020-diverse-20"
    assert manifest.year == 2020
    assert len(manifest.cases) == 20
    assert manifest.cases[0].model_dump() == {
        "ruler_year_id": 15125,
        "ruler_id": 2667,
        "iso3": "NZL",
        "ruler_name": "Jacinda Ardern",
    }
    assert manifest.cases[-1].model_dump() == {
        "ruler_year_id": 18823,
        "ruler_id": 3246,
        "iso3": "CAF",
        "ruler_name": "Touadera",
    }
    assert compute_resolved_content_sha256(manifest) == manifest.resolved_content_sha256


def test_canonical_hash_is_independent_of_case_presentation_order() -> None:
    manifest = load_batch_manifest(MANIFEST_PATH)
    reversed_manifest = manifest.model_copy(update={"cases": tuple(reversed(manifest.cases))})

    assert compute_resolved_content_sha256(reversed_manifest) == manifest.resolved_content_sha256


def test_duplicate_case_identity_is_rejected() -> None:
    case = ResearchBatchCase(
        ruler_year_id=1,
        ruler_id=2,
        iso3="AAA",
        ruler_name="Leader",
    )

    with pytest.raises(ValidationError, match="duplicate batch case ruler_year_id"):
        ResearchBatchManifest(
            version=1,
            batch_id="duplicate",
            year=2020,
            rationale="duplicate validation",
            resolved_content_sha256="0" * 64,
            cases=(case, case),
        )


def test_loader_rejects_resolved_content_hash_mismatch(tmp_path: Path) -> None:
    original_hash = "9fb504ec57209f1c5950aa680930d181224bb68aaa42931fb6aa306da00de2ce"
    payload = MANIFEST_PATH.read_text(encoding="utf-8").replace(
        f'resolved_content_sha256: "{original_hash}"',
        f'resolved_content_sha256: "{"f" * 64}"',
        1,
    )
    path = tmp_path / "manifest.yaml"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="resolved-content hash mismatch"):
        load_batch_manifest(path)


def test_manifest_cases_require_exact_identity_and_eligibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(
        ResearchBatchCase(
            ruler_year_id=10,
            ruler_id=20,
            iso3="AAA",
            ruler_name="Exact Leader",
        )
    )
    eligible = _local_case()
    monkeypatch.setattr(
        "leaders_db.research.batch_manifest.list_local_prior_slice_cases",
        lambda bind, *, year: (eligible,),
    )

    validated = validate_batch_manifest_cases(object(), manifest)

    assert validated == (eligible,)


def test_manifest_case_must_exist_in_current_year_slice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(
        ResearchBatchCase(
            ruler_year_id=10,
            ruler_id=20,
            iso3="AAA",
            ruler_name="Exact Leader",
        )
    )
    monkeypatch.setattr(
        "leaders_db.research.batch_manifest.list_local_prior_slice_cases",
        lambda bind, *, year: (),
    )

    with pytest.raises(ValueError, match="unavailable for year=2020"):
        validate_batch_manifest_cases(object(), manifest)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"leader_name": "Different Leader"}, "ruler_name"),
        (
            {
                "identity_research_eligible": False,
                "identity_block_reason": (
                    "identity_classification:source_conflict_manual_review"
                ),
            },
            "not research eligible",
        ),
    ],
)
def test_manifest_case_rejects_identity_drift_or_quarantine(
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, object],
    message: str,
) -> None:
    manifest = _manifest(
        ResearchBatchCase(
            ruler_year_id=10,
            ruler_id=20,
            iso3="AAA",
            ruler_name="Exact Leader",
        )
    )
    monkeypatch.setattr(
        "leaders_db.research.batch_manifest.list_local_prior_slice_cases",
        lambda bind, *, year: (_local_case(**updates),),
    )

    with pytest.raises(ValueError, match=message):
        validate_batch_manifest_cases(object(), manifest)


def _manifest(case: ResearchBatchCase) -> ResearchBatchManifest:
    manifest = ResearchBatchManifest(
        version=1,
        batch_id="test",
        year=2020,
        rationale="test manifest",
        resolved_content_sha256="0" * 64,
        cases=(case,),
    )
    return manifest.model_copy(
        update={"resolved_content_sha256": compute_resolved_content_sha256(manifest)}
    )


def _local_case(**updates: object) -> LocalPriorSliceCase:
    values: dict[str, object] = {
        "iso3": "AAA",
        "country_name": "Example",
        "year": 2020,
        "leader_name": "Exact Leader",
        "leader_id": 20,
        "ruler_year_id": 10,
        "identity_classification": "resolved_auto_single_candidate",
        "identity_review_status": "resolved",
        "persisted_identity_classification": "resolved_auto_single_candidate",
        "persisted_identity_review_status": "resolved",
        "identity_research_eligible": True,
        "identity_block_reason": None,
    }
    values.update(updates)
    return LocalPriorSliceCase.model_validate(values)
