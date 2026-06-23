"""Compatibility facade — SIPRI Stage 2 (umbrella module name).

This module is a thin compatibility facade. The real SIPRI Stage 2
implementations live in two sibling modules:

- :mod:`leaders_db.ingest.sipri_milex` — military expenditure
  database (Share of GDP, Per capita, Constant US$, Share of Govt.
  spending).
- :mod:`leaders_db.ingest.sipri_yearbook_ch7` — SIPRI Yearbook
  Chapter 7 nuclear forces (total_inventory, deployed, retired).

The dispatch table in :mod:`leaders_db.ingest` resolves
``"sipri_milex"`` to ``sipri_milex.ingest_sipri_milex`` and
``"sipri_yearbook_ch7"`` to ``sipri_yearbook_ch7.ingest_sipri_yearbook_ch7``.
This umbrella module exists only for legacy imports
(``from leaders_db.ingest.sipri import …``) and does **not**
participate in the dispatch table.

The original ``sipri.py`` was a stub that raised
:func:`NotImplementedError` for both ``download_sipri`` and
``ingest_sipri``. The ``"sipri"`` key is intentionally absent from
``STAGE2_ADAPTERS`` because the umbrella concept does not map to a
single canonical source key; callers should use the two specific
source keys (``sipri_milex``, ``sipri_yearbook_ch7``) directly.
Per AGENTS.md Always-On Rule #15, the attribution texts returned
by :func:`attribution_milex` and :func:`attribution_yearbook_ch7`
are the exact wordings from ``docs/sources/attributions.md``.
"""

from __future__ import annotations

# Re-export the canonical orchestrators + public surface from the
# real SIPRI sibling modules. This is the compatibility shim so
# legacy callers importing from ``leaders_db.ingest.sipri`` continue
# to resolve without a code change. The dispatch table does NOT
# consume this facade; it imports the two specific modules directly
# to keep the registry unambiguous.
from . import sipri_milex, sipri_yearbook_ch7
from .sipri_milex import (
    SIPRI_MILEX_ATTRIBUTION,
    SIPRI_MILEX_SOURCE_KEY,
    SipriMilexIngestResult,
)
from .sipri_yearbook_ch7 import (
    SIPRI_YEARBOOK_CH7_ATTRIBUTION,
    SIPRI_YEARBOOK_CH7_SOURCE_KEY,
    SipriYearbookCh7IngestResult,
)


def attribution() -> str:
    """Return the combined SIPRI attribution block for public output.

    Concatenates the per-subdataset attribution texts so any report
    that cites both ``sipri_milex`` and ``sipri_yearbook_ch7`` can
    carry a single combined block. Per AGENTS.md Always-On Rule #15,
    the per-subdataset wording is the exact text from
    ``docs/sources/attributions.md``.
    """
    return f"{SIPRI_MILEX_ATTRIBUTION} {SIPRI_YEARBOOK_CH7_ATTRIBUTION}"


def attribution_milex() -> str:
    """Return the SIPRI milex attribution block for public output."""
    return SIPRI_MILEX_ATTRIBUTION


def attribution_yearbook_ch7() -> str:
    """Return the SIPRI Yearbook Ch.7 attribution block for public output."""
    return SIPRI_YEARBOOK_CH7_ATTRIBUTION


# Historical aliases preserved for callers that imported the
# umbrella functions by their original (now-removed) name. These
# point at the canonical orchestrators; there is no longer a
# single ``ingest_sipri`` because the umbrella concept does not
# map to a single source key.
ingest_sipri_milex = sipri_milex.ingest_sipri_milex
ingest_sipri_yearbook_ch7 = sipri_yearbook_ch7.ingest_sipri_yearbook_ch7


def ingest_sipri(*args, **kwargs):
    """Historical umbrella alias preserved for legacy callers.

    Raises:
        NotImplementedError: Always. The umbrella ``sipri`` concept
            does not map to a single Stage 2 source; use
            ``ingest_sipri_milex`` or ``ingest_sipri_yearbook_ch7``
            directly. The dispatch table does not have a ``"sipri"``
            entry by design.
    """
    raise NotImplementedError(
        "ingest_sipri is no longer a single-source umbrella. "
        "Use ingest_sipri_milex() or ingest_sipri_yearbook_ch7() "
        "directly. The Stage 2 dispatch table keys are "
        "'sipri_milex' and 'sipri_yearbook_ch7'."
    )


def download_sipri(*args, **kwargs):
    """Historical umbrella alias preserved for legacy callers.

    Raises:
        NotImplementedError: Always. There is no single umbrella
            download; the two real adapters read their own raw files
            from ``data/raw/sipri_milex/`` and
            ``data/raw/sipri_yearbook_ch7/`` respectively.
    """
    raise NotImplementedError(
        "download_sipri is no longer a single-source umbrella. The "
        "Stage 2 adapters read from data/raw/sipri_milex/ and "
        "data/raw/sipri_yearbook_ch7/ directly."
    )


__all__ = [
    "SIPRI_MILEX_ATTRIBUTION",
    "SIPRI_MILEX_SOURCE_KEY",
    "SIPRI_YEARBOOK_CH7_ATTRIBUTION",
    "SIPRI_YEARBOOK_CH7_SOURCE_KEY",
    "SipriMilexIngestResult",
    "SipriYearbookCh7IngestResult",
    "attribution",
    "attribution_milex",
    "attribution_yearbook_ch7",
    "download_sipri",
    "ingest_sipri",
    "ingest_sipri_milex",
    "ingest_sipri_yearbook_ch7",
    "sipri_milex",
    "sipri_yearbook_ch7",
]
