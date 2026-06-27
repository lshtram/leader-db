import csv
import json
from pathlib import Path

from leaders_db.research.models import DimensionFilter, ResearchQuestion, ScopeFilter
from leaders_db.research.runner import run_research_question
from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceId,
    TransformLocator,
)
from leaders_db.sources.query import InMemoryEvidenceRepository


def test_runner_writes_required_artifacts_with_direct_evidence_links(tmp_path: Path) -> None:
    repository = InMemoryEvidenceRepository(observations=(_observation(),))
    question = ResearchQuestion(
        question_id="conflict-usa-2020",
        question_key="conflict_fatalities_structured",
        display_text="Get conflict fatalities for USA in 2020.",
        concepts=("conflict_fatalities",),
        scope_filter=ScopeFilter(
            filters=(
                DimensionFilter(key="country", values=("USA",), role="entity"),
                DimensionFilter(key="year", values=(2020,), role="time"),
            )
        ),
        analyses=("coverage",),
        preferred_sources=("ucdp",),
    )

    result = run_research_question(
        question=question,
        repository=repository,
        output_root=tmp_path,
        run_id="run-001",
    )

    assert result.status == "success"
    output_dir = tmp_path / "run-001"
    assert {path.name for path in output_dir.iterdir()} == {
        "question.json",
        "plan.json",
        "evidence-gap-report.json",
        "acquisition-tasks.json",
        "analytical-dataset.csv",
        "findings.json",
        "manifest.json",
    }
    with (output_dir / "analytical-dataset.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["coverage_status"] == "direct"
    assert json.loads(rows[0]["row_scope_json"])["dimensions"][0]["value"] == "USA"
    assert json.loads(rows[0]["source_observation_ids"]) == ["ucdp-usa-2020"]
    assert rows[0]["source_id"] == "ucdp"
    assert "raw_locator_summary" in json.loads(rows[0]["provenance_json"])

    findings = json.loads((output_dir / "findings.json").read_text(encoding="utf-8"))
    assert findings[0]["source_observation_ids"] == ["ucdp-usa-2020"]

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_row_count"] == 1
    assert manifest["evidence_query"]["indicator_codes"] == ["conflict_fatalities"]


def _observation() -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug="ucdp"),
        observation_id="ucdp-usa-2020",
        observation_family="conflict",
        indicator_code="conflict_fatalities",
        value=12,
        value_type="numeric",
        year=2020,
        country_code="USA",
        country_name="United States",
        leader_id=None,
        leader_name=None,
        unit="deaths",
        scale=None,
        source_version="fixture",
        raw_locator=RawLocator(asset_id="fixture-csv", path="fixture.csv", row_number=2),
        transform_locator=TransformLocator(transform_name="fixture-transform"),
    )
