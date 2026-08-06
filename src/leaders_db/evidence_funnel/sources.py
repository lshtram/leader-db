"""Source metadata adapters for frozen evidence-funnel packs."""

from __future__ import annotations

import json
from pathlib import Path

from .ingest import FrozenExtraction
from .models import SourceDescriptor


def load_source_descriptors(
    extractions: tuple[FrozenExtraction, ...],
    reader_config_path: Path,
) -> dict[str, SourceDescriptor]:
    """Build typed source descriptors from the frozen reader manifest."""

    payload = json.loads(reader_config_path.read_text(encoding="utf-8"))
    configured = {item["source_id"]: item for item in payload["document_pack"]}
    descriptors: dict[str, SourceDescriptor] = {}
    for extraction in extractions:
        try:
            item = configured[extraction.source_id]
        except KeyError as error:
            raise ValueError(
                f"reader manifest lacks source {extraction.source_id}"
            ) from error
        host = extraction.final_url.split("/")[2]
        descriptors[extraction.source_id] = SourceDescriptor(
            source_id=extraction.source_id,
            title=extraction.title,
            url=extraction.final_url,
            publisher=host,
            publication_date=str(item.get("publication_date", "unknown_not_recorded")),
            document_type=item["document_type"],
            source_role=item["source_role"],
            source_family=str(item.get("source_family", host)),
            source_sha256=extraction.raw_sha256,
            access_state="open_machine_readable",
            dependencies=tuple(item.get("dependencies", ())),
        )
    return descriptors


__all__ = ["load_source_descriptors"]
