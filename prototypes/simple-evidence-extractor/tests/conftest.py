from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "units": [
                    {
                        "locator": "page 1",
                        "text": (
                            "The authority adopted Rule A on 1 January 2022. "
                            "The rule reduced the fee to 3 percent.\n"
                            "A separate recommendation was not implemented."
                        ),
                    },
                    {
                        "locator": "page 2",
                        "text": "The audit found implementation incomplete.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "ruler": "Example Ruler",
                "country_iso3": "EXT",
                "target_period": "2022",
                "sources": [
                    {
                        "source_id": "DOC-1",
                        "title": "Example",
                        "publisher": "Example Publisher",
                        "extracted_text_path": "source.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest

