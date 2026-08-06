from __future__ import annotations

import pytest
from pydantic import ValidationError

from leaders_db.evidence_funnel.citation_models import (
    LocatorIndex,
    SourceSegment,
)


def test_segment_rejects_text_width_mismatch() -> None:
    with pytest.raises(ValidationError, match="offset width"):
        SourceSegment(
            segment_id="S00001",
            start_char=0,
            end_char=3,
            text="five",
        )


def test_locator_index_requires_ordered_contiguous_segments() -> None:
    first = SourceSegment(
        segment_id="S00001",
        start_char=0,
        end_char=3,
        text="one",
    )
    second = SourceSegment(
        segment_id="S00002",
        start_char=4,
        end_char=7,
        text="two",
    )

    with pytest.raises(ValidationError, match="contiguous"):
        LocatorIndex(
            source_id="LAW-005",
            source_sha256="a" * 64,
            locator="page 1",
            segments=(first, second),
        )
