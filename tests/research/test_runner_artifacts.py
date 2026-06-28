import csv
import json
from pathlib import Path

from leaders_db.research.models import DimensionFilter, ResearchQuestion, ScopeFilter
from leaders_db.research.runner import run_research_question
from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceAttribution,
    SourceId,
    TransformLocator,
)
from leaders_db.sources.query import InMemoryEvidenceRepository


def test_runner_writes_required_artifacts_with_direct_evidence_links(tmp_path: Path) -> None:
    repository = InMemoryEvidenceRepository(
        observations=(_observation(),),
        attributions=(
            SourceAttribution(
                attribution_key="ucdp",
                source_id=SourceId(slug="ucdp"),
                text="UCDP fixture attribution text.",
                citation_url="https://example.test/ucdp",
                license_name="fixture license",
            ),
        ),
    )

    result = run_research_question(
        question=_conflict_question(),
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
        "evidence-appendix.csv",
        "findings.json",
        "report.md",
        "manifest.json",
    }
    assert result.report_path == output_dir / "report.md"
    with (output_dir / "analytical-dataset.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["coverage_status"] == "direct"
    assert json.loads(rows[0]["row_scope_json"])["dimensions"][0]["value"] == "USA"
    assert json.loads(rows[0]["source_observation_ids"]) == ["ucdp-usa-2020"]
    assert rows[0]["source_id"] == "ucdp"
    assert "raw_locator_summary" in json.loads(rows[0]["provenance_json"])

    findings = json.loads((output_dir / "findings.json").read_text(encoding="utf-8"))
    assert findings[0]["source_observation_ids"] == ["ucdp-usa-2020"]

    with (output_dir / "evidence-appendix.csv").open(encoding="utf-8", newline="") as handle:
        appendix_rows = list(csv.DictReader(handle))
    assert appendix_rows[0]["question_id"] == "conflict-usa-2020"
    assert appendix_rows[0]["coverage_status"] == "direct"
    assert json.loads(appendix_rows[0]["source_observation_ids"]) == ["ucdp-usa-2020"]

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_row_count"] == 1
    assert manifest["evidence_query"]["indicator_codes"] == ["conflict_fatalities"]
    assert manifest["artifact_files"]["report"] == "report.md"
    assert manifest["artifact_files"]["appendix"] == "evidence-appendix.csv"

    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "## Method" in report
    assert "deterministic registered planning" in report
    assert "EvidenceRepository" in report
    assert "## Findings" in report
    assert "ucdp-usa-2020" in report
    assert "## Evidence and provenance" in report
    assert "evidence-appendix.csv" in report
    assert "## Caveats and warnings" in report
    assert "## Source attributions" in report
    assert "UCDP fixture attribution text." in report


def test_report_explicitly_notes_when_attributions_are_unavailable(tmp_path: Path) -> None:
    run_research_question(
        question=_conflict_question(),
        repository=InMemoryEvidenceRepository(observations=(_observation(),)),
        output_root=tmp_path,
        run_id="run-no-attribution",
    )

    report = (tmp_path / "run-no-attribution" / "report.md").read_text(encoding="utf-8")
    assert "## Source attributions" in report
    assert "No source attributions available" in report
    assert "Missing source attributions for direct row source IDs: `ucdp`." in report


def test_report_lists_partial_missing_attributions_for_direct_sources(tmp_path: Path) -> None:
    repository = InMemoryEvidenceRepository(
        observations=(
            _observation(source_slug="ucdp", observation_id="ucdp-usa-2020"),
            _observation(source_slug="alternate_conflict", observation_id="alt-usa-2020"),
        ),
        attributions=(
            SourceAttribution(
                attribution_key="ucdp",
                source_id=SourceId(slug="ucdp"),
                text="UCDP fixture attribution text.",
            ),
        ),
    )

    run_research_question(
        question=_conflict_question(preferred_sources=()),
        repository=repository,
        output_root=tmp_path,
        run_id="run-partial-attribution",
    )

    report = (tmp_path / "run-partial-attribution" / "report.md").read_text(encoding="utf-8")
    assert "UCDP fixture attribution text." in report
    assert "Missing source attributions for direct row source IDs: `alternate_conflict`." in report


def _conflict_question(
    *,
    preferred_sources: tuple[str, ...] = ("ucdp",),
) -> ResearchQuestion:
    return ResearchQuestion(
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
        preferred_sources=preferred_sources,
    )


def _observation(
    *,
    source_slug: str = "ucdp",
    observation_id: str = "ucdp-usa-2020",
) -> NormalizedObservation:
    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=observation_id,
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
