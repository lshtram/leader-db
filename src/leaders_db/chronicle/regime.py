"""Political-regime-bucket derivation for the Country-Year Chronicle slice.

The mapping is intentionally a single function,
:func:`derive_regime_bucket`, that takes a :class:`RegimeSource` and
returns a typed :class:`RegimeBucketResult`. The function is pure so
it is straightforward to unit-test.

The mapping follows Increment 0 §5.1:

1. Direct ``v2x_regime`` (integer 0-3) -> the canonical CYC bucket
   (Authoritarian / Hybrid / Flawed / Full democracy).
2. If ``v2x_regime`` is missing but ``v2x_polyarchy`` is present, fall
   back to the conservative thresholds in
   :data:`VDEM_POLYARCHY_FALLBACK_THRESHOLDS`.
3. If both are missing, return ``Unknown`` + ``regime_source_gap``.

The function does NOT consume the LLM or the client matrix; both are
explicitly out of scope per the Increment 1 design contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    FLAG_PROXY_YEAR_USED,
    FLAG_REGIME_SOURCE_GAP,
    SOURCE_TAG_VDEM,
    VDEM_DIRECT_CONFIDENCE,
    VDEM_POLYARCHY_FALLBACK_THRESHOLDS,
    VDEM_PROXY_CONFIDENCE,
    VDEM_REGIME_TO_BUCKET,
)
from .sources import RegimeSource


@dataclass(frozen=True)
class RegimeBucketResult:
    """Output of :func:`derive_regime_bucket`.

    Attributes:
        bucket: One of ``"Full democracy"``, ``"Flawed democracy"``,
            ``"Hybrid regime"``, ``"Authoritarian"``, ``"Unknown"``.
        raw_score: The V-Dem ``v2x_regime`` integer when present;
            otherwise the ``v2x_polyarchy`` score (0-1) when the
            polyarchy fallback was used; otherwise empty.
        source: Short source tag (``"vdem"``).
        source_year_used: Year actually read from V-Dem.
        confidence: 0-100 confidence for the bucket (sourced from
            :data:`VDEM_DIRECT_CONFIDENCE` or
            :data:`VDEM_PROXY_CONFIDENCE`).
        flags: Tuple of pipe-able flag strings to merge into the
            row's ``data_quality_flags``.
    """

    bucket: str
    raw_score: str
    source: str
    source_year_used: int
    confidence: int
    flags: tuple[str, ...]


def derive_regime_bucket(source: RegimeSource) -> RegimeBucketResult:
    """Map a :class:`RegimeSource` to a CYC political-regime bucket.

    The function is deterministic. It honors the documented proxy
    behavior (Increment 0 §5.1): when ``is_proxy`` is true the
    ``proxy_year_used`` flag is added and the confidence is dropped
    to the proxy level.
    """
    # Direct v2x_regime mapping.
    if source.regime is not None:
        try:
            regime_int = int(source.regime)
        except (TypeError, ValueError):
            regime_int = None
        if regime_int is not None and regime_int in VDEM_REGIME_TO_BUCKET:
            bucket = VDEM_REGIME_TO_BUCKET[regime_int]
            flags: tuple[str, ...] = ()
            confidence = (
                VDEM_PROXY_CONFIDENCE if source.is_proxy else VDEM_DIRECT_CONFIDENCE
            )
            if source.is_proxy:
                flags = (FLAG_PROXY_YEAR_USED,)
            return RegimeBucketResult(
                bucket=bucket,
                raw_score=str(regime_int),
                source=SOURCE_TAG_VDEM,
                source_year_used=source.source_year_used,
                confidence=confidence,
                flags=flags,
            )

    # Polyarchy fallback.
    if source.polyarchy is not None:
        for bucket_name, (low, high) in VDEM_POLYARCHY_FALLBACK_THRESHOLDS.items():
            if low <= source.polyarchy < high:
                confidence = (
                    VDEM_PROXY_CONFIDENCE
                    if source.is_proxy
                    else VDEM_DIRECT_CONFIDENCE - 10
                )
                # Polyarchy-derived buckets are slightly less confident
                # than the native ``v2x_regime`` mapping.
                flags_list: list[str] = [FLAG_REGIME_SOURCE_GAP]
                if source.is_proxy:
                    flags_list.append(FLAG_PROXY_YEAR_USED)
                return RegimeBucketResult(
                    bucket=bucket_name,
                    raw_score=f"{source.polyarchy:.4f}",
                    source=SOURCE_TAG_VDEM,
                    source_year_used=source.source_year_used,
                    confidence=confidence,
                    flags=tuple(flags_list),
                )

    # Nothing matched.
    confidence = (
        VDEM_PROXY_CONFIDENCE
        if source.is_proxy
        else VDEM_PROXY_CONFIDENCE - 10
    )
    flags_list = [FLAG_REGIME_SOURCE_GAP]
    if source.is_proxy:
        flags_list.append(FLAG_PROXY_YEAR_USED)
    return RegimeBucketResult(
        bucket="Unknown",
        raw_score="",
        source=SOURCE_TAG_VDEM,
        source_year_used=source.source_year_used,
        confidence=max(confidence, 0),
        flags=tuple(flags_list),
    )


__all__ = ["RegimeBucketResult", "derive_regime_bucket"]
