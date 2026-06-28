"""Attribution lookup for source-run manifests."""

from __future__ import annotations

import re
from pathlib import Path

from leaders_db.paths import project_root

from .contracts import SourceAttribution, SourceDescriptor

_ATTRIBUTION_LINE_RE = re.compile(r'- \*\*Attribution text in reports:\*\* "(?P<text>.+)"')
_LICENSE_LINE_RE = re.compile(r"- \*\*License:\*\* (?P<license>.+)")
_URL_RE = re.compile(r'https?://[^\s)>"]+')


def source_attribution_from_descriptor(descriptor: SourceDescriptor) -> SourceAttribution:
    """Return canonical attribution metadata for ``descriptor`` when available."""

    section = _attribution_section(descriptor.source_id.slug)
    text = descriptor.attribution_key
    license_name: str | None = None
    citation_url = descriptor.homepage_url
    if section is not None:
        if match := _ATTRIBUTION_LINE_RE.search(section):
            text = match.group("text")
        if match := _LICENSE_LINE_RE.search(section):
            license_name = match.group("license").strip()
        if match := _URL_RE.search(section):
            citation_url = match.group(0).rstrip(".")

    return SourceAttribution(
        attribution_key=descriptor.attribution_key,
        source_id=descriptor.source_id,
        text=text,
        citation_url=citation_url,
        license_name=license_name,
    )


def _attribution_section(source_slug: str) -> str | None:
    path = project_root() / "docs" / "sources" / "attributions.md"
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "docs" / "sources" / "attributions.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    marker = f"### `{source_slug}`"
    start = text.find(marker)
    if start == -1:
        return None
    next_section = text.find("\n### `", start + len(marker))
    if next_section == -1:
        return text[start:]
    return text[start:next_section]


__all__ = ["source_attribution_from_descriptor"]
