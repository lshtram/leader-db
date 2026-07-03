"""Transform Wikidata HoS/HoG long-format rows into normalized observations.

The Wikidata clean adapter consumes the legacy long-format pandas
DataFrame emitted by
:func:`leaders_db.ingest.wikidata_heads_of_state_government_parse.parse_sparql_bindings`
(one row per SPARQL binding with columns ``country_qid``,
``country_label``, ``person_qid``, ``person_label``,
``office_qid``, ``office_label``, ``start_date``, ``end_date``,
``statement_uri``, ``year``, ``requested_year``, ``raw_value``)
and emits one :class:`NormalizedObservation` per matching
``(office_qid, spec)`` pair.

Year semantics:

- ``years=(YYYY,)`` (explicit-year request): emits one
  observation per binding with ``year=YYYY`` (the parsed
  ``year`` column from the row's ``start_date`` when present,
  else ``YYYY``). The original ``start_date`` / ``end_date``
  qualifiers are preserved on every emitted observation's
  ``extension.start_date`` / ``extension.end_date`` audit
  fields so downstream audit code can see the full temporal
  envelope.
- ``years=None`` (all-current-holders run): emits one
  observation per binding with ``year`` taken from the parsed
  row's ``start_date`` year, OR ``None`` only when the row's
  ``start_date`` is absent.

Country semantics: the unified transform never invents ISO3
codes. For the recent-rulers cache bridge, ``country_code`` is
the source-provided ``countryISO3`` binding; otherwise it remains
``None``. ``country_name`` carries the Wikidata English label
verbatim. The Wikidata QID is preserved on every emitted
observation's ``extension.country_qid`` / ``extension.country_label``
audit fields.

Leader semantics: ``leader_id`` is always ``None`` (Stage 4 is
the resolver). ``leader_name`` carries the Wikidata person
English label verbatim. The person QID is preserved on every
emitted observation's ``extension.person_qid`` /
``extension.person_label`` audit fields.

Observation family: ``leader_identity_country_year``.

Indicator codes: the two legacy catalog variables
(``wikidata_head_of_state_held`` for Q30461, and
``wikidata_head_of_government_held`` for Q22857062). The
unified transform emits one observation per binding whose
``office_qid`` or broad ``role_qid`` matches a catalog
``raw_column``. Recent-rulers rows whose broad role is Q14212
(prime minister) are retained as head-of-government evidence while
the concrete office QID and role QID remain in the audit payload.

Per-observation ``extension`` payload (audit trail):
``source_row_reference`` (the legacy DB writer's
``wikidata:<country_qid>:<office_qid>:<person_qid>:<statement_hash>``
pattern), ``person_qid`` / ``person_label``, ``country_qid`` /
``country_label``, ``office_qid`` / ``office_label``,
``start_date`` / ``end_date``, ``statement_uri`` /
``statement_hash``, ``requested_year``, ``raw_binding``
(verbatim SPARQL binding JSON), ``value_type="categorical"``,
``raw_scale="qid_list"`` / ``normalized_scale_target="qid_list"``,
``higher_is_better=True``, and ``attribution="Wikidata (CC0 1.0).'``
per Rule #15. ``RawLocator`` carries the cache file path +
SPARQL endpoint URL + asset id; ``row_number`` is intentionally
``None`` (the binding index is recoverable from the
``statement_hash`` audit field).

Stage 2 emits NO observations for missing ``country_qid`` /
``person_qid`` / ``office_qid`` (defensive only -- the canonical
SPARQL query always selects all three).
"""

from __future__ import annotations

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
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME,
)
from ._readiness import cache_file as _cache_file_path
from ._transform_helpers import (
    coerce_int,
    parse_raw_binding,
    statement_hash,
    text,
    text_or_none,
)

_HEAD_OF_GOVERNMENT_QID = "Q22857062"
_PRIME_MINISTER_QID = "Q14212"
_ROLE_TO_INDICATOR_OFFICE_QID = {
    _PRIME_MINISTER_QID: _HEAD_OF_GOVERNMENT_QID,
}


def emit_wikidata_heads_of_state_government_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    """Convert raw Wikidata long frames into ``NormalizedObservation`` records.

    The country filter is a case-sensitive QID match against the
    ``country_qid`` column. Non-QID inputs are silently ignored
    (the readiness gate surfaces a structured
    ``wikidata_non_qid_country_filter`` warning). The transform
    layer never invents values, ISO3 codes, leader IDs, or proxy
    years: bindings with missing ``country_qid`` / ``person_qid``
    / ``office_qid`` are skipped.
    """
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    long_frames = payload.get("long_frames") or []
    specs = payload.get("specs") or []
    raw_payloads: list[tuple[str, dict[str, Any]]] = (
        payload.get("raw_payloads") or []
    )
    if not specs:
        return iter(())
    spec_by_office_qid: dict[str, Any] = {
        spec.raw_column: spec for spec in specs
    }

    country_filter = _country_qid_filter(request)

    requested_year = (
        int(request.years[0]) if request.years else None
    )

    cache_root_path = _extract_cache_root(payload)
    request_countries = (
        payload.get("request_countries") or None
    )

    observations: list[NormalizedObservation] = []
    for frame_idx, frame in enumerate(long_frames):
        if frame is None or getattr(frame, "empty", True):
            continue
        cache_key = (
            raw_payloads[frame_idx][0] if frame_idx < len(raw_payloads)
            else None
        )
        cache_file_path = _resolve_cache_file_path(
            request=request,
            cache_root=cache_root_path,
            cache_key=cache_key,
            requested_countries=request_countries,
        )
        for row in frame.itertuples(index=False):
            observation = _row_to_observation(
                request=request,
                row=row,
                spec_by_office_qid=spec_by_office_qid,
                country_filter=country_filter,
                requested_year=requested_year,
                cache_file_path=cache_file_path,
                cache_key=cache_key,
            )
            if observation is not None:
                observations.append(observation)
    return iter(observations)


def _row_to_observation(
    *,
    request: SourceIngestRequest,
    row: Any,
    spec_by_office_qid: dict[str, Any],
    country_filter: set[str] | None,
    requested_year: int | None,
    cache_file_path: Any,
    cache_key: str | None,
) -> NormalizedObservation | None:
    """Convert one legacy long-format row to a normalized observation."""
    country_qid = text(getattr(row, "country_qid", None))
    country_label = text(getattr(row, "country_label", None))
    person_qid = text(getattr(row, "person_qid", None))
    person_label = text(getattr(row, "person_label", None))
    office_qid = text(getattr(row, "office_qid", None))
    office_label = text(getattr(row, "office_label", None))
    role_qid = text(getattr(row, "role_qid", None))
    country_iso3 = text(getattr(row, "country_iso3", None))
    start_date = text_or_none(getattr(row, "start_date", None))
    end_date = text_or_none(getattr(row, "end_date", None))
    statement_uri = text(getattr(row, "statement_uri", None))
    raw_value_text = text(getattr(row, "raw_value", None))
    binding_index = text_or_none(getattr(row, "binding_index", None))
    parsed_year = coerce_int(getattr(row, "year", None))

    if not country_qid or not person_qid or not office_qid:
        # Defensive: the canonical SPARQL query always selects
        # all three. Silently skip bindings missing any of the
        # three identifiers -- the unified adapter never invents
        # values.
        return None

    if role_qid and not country_iso3:
        # The recent-rulers fallback is only usable for I4 when Wikidata
        # supplies ISO3 directly. Do not emit rows that would later be
        # country-name matched into 2023 identity coverage.
        return None

    if country_filter is not None and country_qid not in country_filter:
        return None

    spec = spec_by_office_qid.get(office_qid)
    indicator_office_qid = office_qid
    if spec is None and role_qid:
        indicator_office_qid = _ROLE_TO_INDICATOR_OFFICE_QID.get(role_qid, role_qid)
        spec = spec_by_office_qid.get(indicator_office_qid)
    if spec is None:
        # Binding for an office QID not in the catalog. The
        # SPARQL query is built from the catalog's office QIDs,
        # so this branch is defensive only. Silently skip (the
        # binding was for an office the prototype is not
        # tracking at Stage 2).
        return None

    if requested_year is not None:
        year_value = requested_year
    else:
        year_value = parsed_year

    statement_hash_value = statement_hash(
        statement_uri or f"{binding_index}:{raw_value_text}",
    )
    source_row_reference = (
        f"wikidata:{country_qid}:{office_qid}:"
        f"{person_qid}:{statement_hash_value}"
    )

    value = person_qid
    raw_binding = parse_raw_binding(raw_value_text)
    extension: dict[str, Any] = {
        "source_row_reference": source_row_reference,
        "person_qid": person_qid,
        "person_label": person_label or None,
        "country_qid": country_qid,
        "country_label": country_label or None,
        "office_qid": office_qid,
        "office_label": office_label or None,
        "role_qid": role_qid or None,
        "indicator_office_qid": indicator_office_qid,
        "country_iso3": country_iso3 or None,
        "start_date": start_date,
        "end_date": end_date,
        "statement_uri": statement_uri or None,
        "statement_hash": statement_hash_value,
        "binding_index": binding_index,
        "requested_year": requested_year,
        "value_type": "categorical",
        "raw_value": raw_value_text or None,
        "raw_binding": raw_binding,
        "raw_scale": getattr(spec, "raw_scale", "qid_list") or "qid_list",
        "normalized_scale_target": (
            getattr(spec, "normalized_scale_target", "qid_list")
            or "qid_list"
        ),
        "higher_is_better": bool(
            getattr(spec, "higher_is_better", True)
        ),
        "attribution": WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT,
    }

    asset_id = (
        f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY}:cache:{cache_key}"
        if cache_key
        else f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY}:cache:current"
    )

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=(
            f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY}:"
            f"{country_qid}:{office_qid}:{person_qid}:{statement_hash_value}"
        ),
        observation_family=(
            WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY
        ),
        indicator_code=spec.variable_name,
        value=value,
        value_type="categorical",
        year=year_value,
        country_code=country_iso3 or None,
        country_name=country_label or None,
        leader_id=None,
        leader_name=person_label or None,
        unit=getattr(spec, "unit", "qid") or "qid",
        scale=getattr(spec, "raw_scale", "qid_list") or "qid_list",
        source_version=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=asset_id,
            path=(
                str(cache_file_path) if cache_file_path is not None
                else None
            ),
            url=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
            row_number=None,
            column_name=indicator_office_qid,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=(
                WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME
            ),
            catalog_key=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
            rule_id=source_row_reference,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _country_qid_filter(
    request: SourceIngestRequest,
) -> set[str] | None:
    """Return the country filter as a set of Wikidata QIDs, or ``None``.

    The unified adapter treats ``countries=`` as a list of
    Wikidata QIDs (the source-native country identifier). The
    readiness gate validates the request countries; non-QID
    inputs are silently dropped here AND surface a structured
    ``wikidata_non_qid_country_filter`` warning at readiness
    time.
    """
    from ._request_warnings import normalize_country_qids

    normalized = normalize_country_qids(request.countries)
    if normalized is None:
        return None
    if not normalized:
        return set()
    return set(normalized)


def _extract_cache_root(payload: dict[str, Any]) -> str | None:
    """Return the cache root string from the raw payload."""
    cache_root = payload.get("cache_root")
    if isinstance(cache_root, str):
        return cache_root
    return None


def _resolve_cache_file_path(
    *,
    request: SourceIngestRequest,
    cache_root: str | None,
    cache_key: str | None,
    requested_countries: Any,
) -> Any:
    """Return the canonical cache file path for the request.

    Falls back to the canonical ``cache_file`` helper when the
    raw payload does not carry the cache key.
    """
    if cache_root is None:
        return None
    if cache_key is None:
        countries: tuple[str, ...] | None = None
        if isinstance(requested_countries, tuple):
            countries = requested_countries
        year: int | None = (
            int(request.years[0]) if request.years else None
        )
        return _cache_file_path(
            request, year=year, country_qids=countries,
        )
    from pathlib import Path as _P

    return _P(cache_root) / f"{cache_key}.json"


__all__ = [
    "emit_wikidata_heads_of_state_government_observations",
]
