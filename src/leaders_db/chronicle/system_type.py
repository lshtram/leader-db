"""Conservative system-type classifier for the Country-Year Chronicle slice.

The classifier is intentionally minimal (Increment 0 §5.2):

1. Curated country-period mappings (the pilot identities: SUN, CHN post-1949,
   and IND pre-1947). RUS is intentionally not curated and falls back from
   regime bucket labels.
2. Regime-bucket fallback for democratic market economies:
   - ``Full democracy`` / ``Flawed democracy`` -> ``Liberal capitalist
     democracy``.
   - ``Hybrid regime`` / ``Authoritarian`` -> ``Mixed / unclear``.
   - ``Unknown`` -> ``Unknown``.
3. If neither path matches, emit ``Unknown`` with low confidence and
   the ``system_type_low_confidence`` flag.

The classifier is deterministic and pure. It does NOT consult the LLM
or the client matrix.

Confidence values:

- Curated mapping match: :data:`CURATED_SYSTEM_TYPE_CONFIDENCE` (70).
- Regime-bucket fallback: :data:`FALLBACK_SYSTEM_TYPE_CONFIDENCE` (40).
- Otherwise: 20 + ``system_type_low_confidence`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    CURATED_SYSTEM_TYPE_CONFIDENCE,
    FALLBACK_SYSTEM_TYPE_CONFIDENCE,
    FLAG_SYSTEM_TYPE_LOW_CONFIDENCE,
    REGIME_BUCKET_DEFAULT_SYSTEM_TYPE,
    SOURCE_TAG_CURATED,
    SOURCE_TAG_VDEM,
    SYSTEM_TYPE_COUNTRY_PERIODS,
)


@dataclass(frozen=True)
class SystemTypeResult:
    """Output of :func:`classify_system_type`.

    Attributes:
        primary: The primary system-type label (one of the Increment 0
            §3.1 system-type values, or ``"Unknown"``).
        secondary: Optional secondary system-type label (currently
            always empty; reserved for future nuance).
        source: Short source tag.
        confidence: 0-100 confidence for the label.
        notes: Free-text notes for the CSV output.
        flags: Tuple of pipe-able flag strings.
    """

    primary: str
    secondary: str
    source: str
    confidence: int
    notes: str
    flags: tuple[str, ...]


def classify_system_type(
    *,
    iso3: str,
    year: int,
    regime_bucket: str,
) -> SystemTypeResult:
    """Apply the conservative system-type classifier.

    The curated country-period mappings take precedence over the
    regime-bucket fallback. The fallback is only used when no curated
    mapping matches.
    """
    # Curated mapping check.
    for mapping_iso3, start, end, label in SYSTEM_TYPE_COUNTRY_PERIODS:
        if mapping_iso3 == iso3 and start <= year <= end:
            notes = (
                f"Curated mapping: ({iso3}, {start}-{end}) -> {label}. "
                "Regime bucket was "
                f"{regime_bucket!r}."
            )
            return SystemTypeResult(
                primary=label,
                secondary="",
                source=SOURCE_TAG_CURATED,
                confidence=CURATED_SYSTEM_TYPE_CONFIDENCE,
                notes=notes,
                flags=(),
            )

    # Regime-bucket fallback.
    default = REGIME_BUCKET_DEFAULT_SYSTEM_TYPE.get(regime_bucket, "Unknown")
    if default == "Unknown":
        return SystemTypeResult(
            primary="Unknown",
            secondary="",
            source=SOURCE_TAG_VDEM,
            confidence=FALLBACK_SYSTEM_TYPE_CONFIDENCE - 10,
            notes=(
                f"No curated mapping for ({iso3}, {year}); "
                f"regime bucket {regime_bucket!r} defaulted to Unknown."
            ),
            flags=(FLAG_SYSTEM_TYPE_LOW_CONFIDENCE,),
        )
    return SystemTypeResult(
        primary=default,
        secondary="",
        source=SOURCE_TAG_VDEM,
        confidence=FALLBACK_SYSTEM_TYPE_CONFIDENCE,
        notes=(
            f"No curated mapping for ({iso3}, {year}); "
            f"regime bucket {regime_bucket!r} defaulted to {default}."
        ),
        flags=(),
    )


__all__ = ["SystemTypeResult", "classify_system_type"]
