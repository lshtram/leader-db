from __future__ import annotations

from pathlib import Path

import pytest

from simple_evidence.source import load_sources, resolve_span


def test_prepares_stable_sentences_and_exact_span(manifest_path: Path) -> None:
    source = load_sources(manifest_path)["DOC-1"]

    assert len(source.sentences) == 4
    assert source.sentences[0].text.endswith("2022.")
    locator, excerpt, start, end = resolve_span(source, 1, 2)

    original = dict(source.locator_texts)[locator]
    assert excerpt == original[start:end]
    assert "\n" not in excerpt
    assert excerpt.endswith("3 percent.")


def test_rejects_cross_locator_span(manifest_path: Path) -> None:
    source = load_sources(manifest_path)["DOC-1"]

    with pytest.raises(ValueError, match="cross locator"):
        resolve_span(source, 3, 4)


def test_rejects_unknown_sentence(manifest_path: Path) -> None:
    source = load_sources(manifest_path)["DOC-1"]

    with pytest.raises(ValueError, match="within"):
        resolve_span(source, 99)

