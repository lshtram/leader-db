from types import SimpleNamespace

from leaders_db.research.dossier_analysis_package import _convert


def test_convert_dossier_evidence_preserves_routing_and_locator() -> None:
    item = SimpleNamespace(
        evidence_id="E001",
        url="https://example.test/report",
        title="Report",
        publisher="Publisher",
        excerpt="Exact passage.",
        claim="A retained factual account.",
        period_fit="Target year.",
        ruler_attribution="National policy under the ruler.",
        source_confidence_reason="Primary record.",
        contrary_evidence=("Implementation remains uncertain.",),
        source_locator="page 4",
    )

    converted = _convert(item, ["2B.1", "1B.1", "2B.1"], {"context"})

    assert converted.question_ids == ("1B.1", "2B.1")
    assert converted.locator == "page 4"
    assert converted.exact_excerpt == "Exact passage."
    assert converted.verification_status == "accepted"
