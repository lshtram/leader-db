import json
from pathlib import Path

from leaders_db.research.compact_handoff import build_compact_research_handoff


def test_compact_handoff_keeps_ledger_and_accounting_without_raw_claims(
    tmp_path: Path,
) -> None:
    manifest = {
        "schema_version": "ruler_research_ledger_manifest_v1",
        "entries": [{"canonical_fact_key": "fact-1", "claim": "retained"}],
    }
    (tmp_path / "research-ledger-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "research-chapter-1B.md").write_text(
        "SOURCE_CLAIM_JSON: " + ("x" * 10_000) + "\nResearch accounting:\n- accepted 1",
        encoding="utf-8",
    )

    result = build_compact_research_handoff(
        attempt_dir=tmp_path,
        fallback_notebook="fallback",
    )

    assert "--- RESEARCH LEDGER MANIFEST ---" in result
    assert '"canonical_fact_key":"fact-1"' in result
    assert "Research accounting:\n- accepted 1" in result
    assert "x" * 100 not in result
    assert len(result) < 1_000


def test_compact_handoff_falls_back_without_manifest(tmp_path: Path) -> None:
    assert (
        build_compact_research_handoff(
            attempt_dir=tmp_path,
            fallback_notebook="complete notebook",
        )
        == "complete notebook"
    )


def test_compact_handoff_tolerates_malformed_manifest(tmp_path: Path) -> None:
    (tmp_path / "research-ledger-manifest.json").write_text("{", encoding="utf-8")

    assert (
        build_compact_research_handoff(
            attempt_dir=tmp_path,
            fallback_notebook="complete notebook",
        )
        == "complete notebook"
    )


def test_compact_handoff_rejects_empty_manifest(tmp_path: Path) -> None:
    (tmp_path / "research-ledger-manifest.json").write_text(
        '{"schema_version":"ruler_research_ledger_manifest_v1","entries":[]}',
        encoding="utf-8",
    )

    assert (
        build_compact_research_handoff(
            attempt_dir=tmp_path,
            fallback_notebook="complete notebook",
        )
        == "complete notebook"
    )
