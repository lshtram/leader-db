"""Request-scoping warning builders + QID normalization helpers.

Split out of :mod:`._readiness` so the readiness-gate
orchestrator can stay focused on the metadata + cache-policy +
cache-availability + version gates.

Owns:

- :data:`_QID_RE` -- the canonical Wikidata QID regex pattern
  (``^Q\\d+$``).
- :func:`normalize_country_qids` -- strip the ``wd:`` prefix,
  validate against ``_QID_RE``, return a sorted tuple of
  bare QIDs (drop non-QID inputs silently so the
  ``wikidata_non_qid_country_filter`` warning can name them
  at readiness time).
- :func:`non_qid_country_values` -- return the non-QID values
  from a country filter (used by the request-warnings builder).
- :func:`request_warnings` -- the canonical
  :class:`SourceWarning` envelope for
  ``UNSUPPORTED_FILTER`` (``leaders=`` set) +
  ``wikidata_non_qid_country_filter`` (``countries=`` contains
  non-QID values).
"""

from __future__ import annotations

import re

from leaders_db.sources.contracts import (
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import UNSUPPORTED_FILTER

from ._constants import WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY

_QID_RE = re.compile(r"^Q\d+$")


def normalize_country_qids(
    countries: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """Return the country filter as a sorted tuple of bare QIDs.

    Strips the ``wd:`` prefix defensively (the legacy parser's
    convention), validates each value against ``_QID_RE``, and
    returns the sorted unique QIDs. Non-QID inputs are silently
    dropped (the request-warnings layer surfaces a structured
    ``wikidata_non_qid_country_filter`` warning naming the
    offending values so a caller can switch to QIDs).
    """
    if not countries:
        return None
    valid: list[str] = []
    for raw in countries:
        cleaned = str(raw).strip()
        if not cleaned:
            continue
        if cleaned.lower().startswith("wd:"):
            cleaned = cleaned[3:].strip()
        if _QID_RE.match(cleaned):
            valid.append(cleaned)
    if not valid:
        return tuple()
    return tuple(sorted(set(valid)))


def non_qid_country_values(
    countries: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the non-QID values from a country filter."""
    bad: list[str] = []
    for raw in countries:
        cleaned = str(raw).strip()
        if not cleaned:
            continue
        if cleaned.lower().startswith("wd:"):
            cleaned = cleaned[3:].strip()
        if not _QID_RE.match(cleaned):
            bad.append(str(raw))
    return tuple(bad)


def request_warnings(
    request: SourceIngestRequest,
) -> tuple[SourceWarning, ...]:
    """Build the request-scoping warning list for the readiness envelope.

    Surfaces:

    - ``UNSUPPORTED_FILTER`` when ``leaders=`` is set (Wikidata
      is a per-binding leader-identity source with no leader
      filter at the Stage 2 layer; downstream Stage 4 is the
      resolver; SRC-REQ-005).
    - ``wikidata_non_qid_country_filter`` when ``countries=``
      contains values that are NOT Wikidata QIDs (the unified
      adapter never invents ISO3 codes; non-QID filters match
      zero rows; the warning names the offending values so a
      caller can switch to QIDs).
    """
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "Wikidata heads-of-state is per-binding "
                    "leader-identity evidence; leader filters are "
                    "ignored at Stage 2 (Stage 4 is the resolver)."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            )
        )
    if request.countries:
        non_qid = non_qid_country_values(request.countries)
        if non_qid:
            warnings.append(
                SourceWarning(
                    code=(
                        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY
                    ),
                    message=(
                        "Wikidata heads-of-state uses source-native "
                        "Wikidata QIDs (e.g. 'Q30' for USA); the "
                        "request countries filter contains values "
                        "that are not QIDs and will match zero rows. "
                        "Use Wikidata QIDs to opt in to evidence; "
                        "ISO3 filtering happens in Stage 3 via the "
                        "canonical country mapping."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={"non_qid_countries": list(non_qid)},
                )
            )
    return tuple(warnings)


__all__ = [
    "_QID_RE",
    "non_qid_country_values",
    "normalize_country_qids",
    "request_warnings",
]
