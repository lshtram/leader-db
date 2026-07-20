import json
from pathlib import Path

import pytest

from leaders_db.conversational_evidence.hybrid_experiment import batch
from leaders_db.conversational_evidence.hybrid_experiment.batch_models import (
    BatchManifest,
)


def _manifest(cases: int = 2) -> dict[str, object]:
    return {
        "schema_version": "hybrid_experiment_batch_v1",
        "batch_id": "pilot",
        "year": 2022,
        "researcher": "gpt-5.4-mini",
        "per_ruler_cost_ceiling_usd": 3.0,
        "batch_cost_ceiling_usd": 6.0,
        "maximum_failures_per_case": 2,
        "stages": [{"completed": 0, "workers": 1}],
        "cases": [
            {
                "iso3": f"AA{chr(ord('A') + number)}",
                "country": f"Country {number}",
                "ruler": f"Ruler {number}",
                "identity_status": "reviewed_locked",
                "identity_rationale": "Reviewed principal national executive.",
            }
            for number in range(cases)
        ],
    }


def test_manifest_rejects_duplicate_identities() -> None:
    value = _manifest()
    value["cases"][1]["iso3"] = "AAA"

    with pytest.raises(ValueError, match="unique ISO3"):
        BatchManifest.model_validate(value)


def test_preflight_builds_all_local_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = _manifest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(value), encoding="utf-8")

    def fake_prepare(
        root: Path,
        output: Path,
        ruler: str,
        country: str,
        iso3: str,
        year: int,
        ruler_id: str,
    ) -> None:
        del root, ruler, country, iso3, year, ruler_id
        path = output / "inputs" / "local-priors.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps([{"status": "evidence_found"}] * 80), encoding="utf-8"
        )

    monkeypatch.setattr(batch, "prepare_inputs", fake_prepare)

    result = batch.preflight(manifest_path, tmp_path / "run", tmp_path)

    assert result["ready"] is True
    assert len(result["cases"]) == 2
    assert all(item["prior_rows"] == 80 for item in result["cases"])


def test_full_and_pilot_manifests_are_valid_and_locked() -> None:
    root = Path(__file__).resolve().parents[2]
    data = (
        root
        / "src/leaders_db/conversational_evidence/hybrid_experiment/data"
    )

    full = BatchManifest.model_validate_json(
        (data / "2022-top20-reviewed.json").read_text(encoding="utf-8")
    )
    pilot = BatchManifest.model_validate_json(
        (data / "2022-pilot-3-reviewed.json").read_text(encoding="utf-8")
    )

    assert len(full.cases) == 20
    assert len(pilot.cases) == 3
    assert {item.iso3 for item in pilot.cases} == {"BRA", "IND", "RUS"}
    assert all(item.identity_status == "reviewed_locked" for item in full.cases)
