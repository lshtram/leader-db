"""Transform Wikipedia Action API long-format rows into normalized observations.

The Wikipedia clean adapter consumes the legacy long-format pandas
DataFrame emitted by
:func:`leaders_db.ingest.wikipedia_search_extract_parse.parse_extracts_response`
and
:func:`leaders_db.ingest.wikipedia_search_extract_parse.parse_search_response`
(one row per Action API response page / search hit with columns
``action``, ``query``, ``pageid``, ``title``, ``extract``, ``raw_value``,
``source_row_reference_hint``) and emits one
:class:`NormalizedObservation` per parsed row.

Observation family: ``leader_identity_context`` (the documented
clean-slice family -- distinguished from the Wikidata
``leader_identity_country_year`` family so the two leader-context
sources can co-exist in the registry without collision).

Indicator codes: the two legacy catalog variables
(``wikipedia_extract_lead`` for the ``extracts`` action;
``wikipedia_search_results`` for the ``search`` action). The unified
transform emits one observation per parsed row whose ``action`` matches
a catalog ``raw_column``.

Per-observation ``value`` payload:

- ``extracts`` action: ``value`` is the verbatim ``extract`` text
  (the article lead paragraph from the Action API response).
- ``search`` action: ``value`` is the verbatim ``extract`` text
  (which the legacy parser populates with the search snippet, with
  ``<span class="searchmatch">`` tags stripped -- the audit trail
  preserves the unstripped raw_value via ``extension.raw_value``).
- ``value_type='text'`` for both actions.

Per-observation identity fields:

- ``year=None`` -- the Action API does not return a year for
  ``extracts`` or ``search`` responses (Stage 4 may resolve the year
  from the page metadata if needed).
- ``country_code=None`` -- the Action API does not return country-coded
  rows (Stage 3 country match resolves the source-native title to a
  country when applicable).
- ``leader_id=None`` -- Stage 4 is the resolver.
- ``leader_name=None`` -- the unified adapter does NOT claim resolved
  leader identity for Action API snippets; the title is preserved on
  the audit-trail extension payload as ``extension.title`` and
  ``extension.query``.

Per-observation ``extension`` payload (audit trail): the
``source_row_reference`` follows the legacy DB-writer convention
``wikipedia:<variable_name>:<hint>`` where ``<hint>`` is the
parser-emitted per-row ``wikipedia:<pageid>:<title>`` (extracts) or
``wikipedia:search:<pageid>:<title>`` (search); the raw cache path
``wikipedia:<action>:<pageid>:<title>``; the verbatim per-row payload
JSON; the verbatim query string; the action name; the ``title`` (when
present); the ``pageid`` (when present); the verbatim ``extract``
text (the post-HTML-strip snippet for search rows); the canonical
attribution text ``Wikipedia (CC BY-SA 4.0).`` per Rule #15;
``value_type='text'``, ``raw_scale='text'``,
``normalized_scale_target='text'``, ``higher_is_better=True``; and
``request.queries`` on every observation so downstream audit code can
see the input contract.

Stage 2 emits NO observations for rows missing ``title`` (defensive
only -- the canonical parser already drops such rows; the transform
defends against a future reader that doesn't filter).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    RawReadResult,
    SourceIngestRequest,
    TransformLocator,
)

from ._constants import (
    WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR,
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
    WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME,
)


def emit_wikipedia_search_extract_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    """Convert raw Wikipedia Action API long frames into normalized observations.

    The transform iterates every cached frame in
    ``raw.payload["long_frames"]`` (one frame per (query, action)
    cache file) and emits one observation per parsed row whose
    ``action`` matches a catalog ``raw_column``. The country filter
    is intentionally NOT applied (the Action API does not return
    country-coded rows); the readiness gate surfaces a structured
    ``UNSUPPORTED_FILTER`` warning when ``request.countries`` is set.
    The leader filter is intentionally NOT applied (Stage 4 is the
    resolver); the request ``leaders=`` is the query-string list.
    """
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    long_frames = payload.get("long_frames") or []
    specs = payload.get("specs") or []
    raw_payloads: list[tuple[str, str, dict[str, Any]]] = (
        payload.get("raw_payloads") or []
    )
    if not specs:
        return iter(())

    observations: list[NormalizedObservation] = []
    for frame_idx, frame in enumerate(long_frames):
        if frame is None or getattr(frame, "empty", True):
            continue
        action: str | None = None
        cache_key: str | None = None
        if frame_idx < len(raw_payloads):
            action, cache_key, _ = raw_payloads[frame_idx]
        if action is None:
            continue
        indicator_code = WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR.get(
            action
        )
        if indicator_code is None:
            # Defensive: only the two canonical actions are supported.
            continue
        for row in frame.itertuples(index=False):
            observation = _row_to_observation(
                request=request,
                row=row,
                indicator_code=indicator_code,
                action=action,
                cache_key=cache_key,
            )
            if observation is not None:
                observations.append(observation)
    return iter(observations)


def _row_to_observation(
    *,
    request: SourceIngestRequest,
    row: Any,
    indicator_code: str,
    action: str,
    cache_key: str | None,
) -> NormalizedObservation | None:
    """Convert one legacy long-format row to a normalized observation."""
    action_value = _text(getattr(row, "action", None))
    query_value = _text(getattr(row, "query", None))
    pageid = _coerce_int(getattr(row, "pageid", None))
    title = _text(getattr(row, "title", None))
    extract_text = _text_or_none(getattr(row, "extract", None))
    raw_value_text = _text_or_none(getattr(row, "raw_value", None))
    hint = _text(getattr(row, "source_row_reference_hint", None))

    if not title:
        # Defensive: the canonical parser drops rows missing ``title``,
        # but a future reader might not. Skip rather than emit a row
        # without a stable identifier.
        return None
    if action_value and action_value != action:
        # Defensive: the per-frame ``action`` must match the row's
        # ``action`` (the canonical parser guarantees this). A
        # mismatch means a future reader mixed actions; skip the row
        # rather than mislabel it.
        return None

    value = extract_text if extract_text is not None else title
    value_type = "text"
    source_row_reference = (
        f"wikipedia:{indicator_code}:{hint}"
        if hint
        else f"wikipedia:{indicator_code}:wikipedia:{pageid}:{title}"
    )

    cache_path_part = f"wikipedia:{action}"
    if pageid is not None:
        cache_path_part = f"{cache_path_part}:{pageid}:{title}"
    else:
        cache_path_part = f"{cache_path_part}:-:{title}"

    extension: dict[str, Any] = {
        "source_row_reference": source_row_reference,
        "action": action,
        "query": query_value,
        "title": title,
        "pageid": pageid,
        "extract": extract_text,
        "raw_value": raw_value_text,
        "raw_row_payload": (
            _safe_loads(raw_value_text) if raw_value_text else None
        ),
        "source_row_reference_hint": hint,
        "value_type": value_type,
        "raw_scale": "text",
        "normalized_scale_target": "text",
        "higher_is_better": True,
        "attribution": WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT,
        "cache_path_reference": cache_path_part,
    }
    if cache_key is not None:
        extension["cache_key"] = cache_key

    asset_id = (
        f"{WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY}:cache:{action}:"
        f"{cache_key}"
        if cache_key
        else (
            f"{WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY}:cache:{action}:"
            f"{pageid}:{title}"
        )
    )

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=(
            f"{WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY}:{action}:"
            f"{pageid}:{title}"
            if pageid is not None
            else (
                f"{WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY}:{action}:"
                f"-:{title}"
            )
        ),
        observation_family=(
            WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY
        ),
        indicator_code=indicator_code,
        value=value,
        value_type=value_type,
        year=None,
        country_code=None,
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit="text",
        scale="text",
        source_version=WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=asset_id,
            path=None,
            url=WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
            api_endpoint=WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
            api_params_hash=cache_key,
            row_number=None,
            column_name=action,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=(
                WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME
            ),
            catalog_key=WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
            rule_id=source_row_reference,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _text(value: Any) -> str:
    """Return ``str(value).strip()`` or ``""`` when value is None/empty."""
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _text_or_none(value: Any) -> str | None:
    """Return ``str(value).strip()`` or ``None`` when value is None/empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: Any) -> int | None:
    """Return ``int(value)`` or ``None`` when value is missing / non-numeric."""
    as_int = _coerce_int_raw(value)
    if as_int is None or as_int <= 0:
        return None
    return as_int


def _coerce_int_raw(value: Any) -> int | None:
    """Coerce ``value`` to ``int`` without the > 0 filter.

    Returns ``None`` for missing / non-numeric / bool / NaN / inf
    values. The caller applies the > 0 filter.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _safe_loads(raw_value_text: str | None) -> Any:
    """Return the parsed JSON payload of the row's ``raw_value`` or ``None``."""
    if not raw_value_text:
        return None
    try:
        return json.loads(raw_value_text)
    except (TypeError, ValueError):
        return None


__all__ = [
    "emit_wikipedia_search_extract_observations",
]
