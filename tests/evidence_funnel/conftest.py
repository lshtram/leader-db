from __future__ import annotations

from pathlib import Path

import pytest

from leaders_db.evidence_funnel.citation_ledger import CitationLedger
from leaders_db.evidence_funnel.citation_models import (
    CitationSelection,
    EvidenceIntent,
)
from leaders_db.evidence_funnel.ingest import ExtractedUnit, FrozenExtraction
from leaders_db.evidence_funnel.models import SourceDescriptor


@pytest.fixture
def extraction() -> FrozenExtraction:
    return FrozenExtraction(
        schema_version="frozen_extraction_v1",
        source_id="LAW-005",
        title="Synthetic fiscal agreement",
        requested_url="https://example.test/law",
        final_url="https://example.test/law",
        raw_sha256="a" * 64,
        estimated_source_tokens=50,
        units=(
            ExtractedUnit(
                unit=1,
                locator="page 1",
                text=(
                    "The deficit target was 3.8 percent of GDP. "
                    "Untargeted subsidies mitigated living costs. "
                    "Gross debt was about 56 percent of GDP."
                ),
            ),
        ),
    )


@pytest.fixture
def descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        source_id="LAW-005",
        title="Synthetic fiscal agreement",
        url="https://example.test/law",
        publisher="Example",
        publication_date="2022-12-09",
        document_type="legislation",
        source_role="official_primary",
        source_family="example",
        source_sha256="a" * 64,
        access_state="open_machine_readable",
    )


@pytest.fixture
def intent(extraction: FrozenExtraction) -> EvidenceIntent:
    return EvidenceIntent(
        draft_id="D0001",
        citation=CitationSelection(
            source_id=extraction.source_id,
            source_sha256=extraction.raw_sha256,
            locator="page 1",
            start_segment_id="S00001",
            end_segment_id="S00003",
        ),
        claim="The deficit target was 3.8% of GDP and debt was about 56%.",
        claim_type="observed_fact",
        polarity="mixed",
        actor="Government",
        action="set a deficit target",
        mechanism="fiscal policy",
        outcome="deficit and debt levels were reported",
        quantities=("3.8%", "56%"),
        attribution="Official fiscal report",
        period_fit="Target year",
        question_ids=("5B.3",),
    )


@pytest.fixture
def ledger(
    tmp_path: Path,
    extraction: FrozenExtraction,
    descriptor: SourceDescriptor,
) -> CitationLedger:
    return CitationLedger(
        root=tmp_path / "ledger",
        extractions=(extraction,),
        sources={descriptor.source_id: descriptor},
        segment_characters=80,
        maximum_attempts=3,
    )
