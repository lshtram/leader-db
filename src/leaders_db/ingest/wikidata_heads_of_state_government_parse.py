"""SPARQL JSON response parser for the Wikidata heads-of-state-and-government adapter.

This module owns the SPARQL-JSON -> long-format DataFrame parser
(:func:`parse_sparql_bindings`) and the canonical SPARQL query
builder (:func:`build_head_of_state_government_query`).

The SPARQL response shape:

```json
{
  "head": {"vars": ["country", "countryLabel", ...]},
  "results": {
    "bindings": [
      {
        "country": {"type": "uri", "value": "http://www.wikidata.org/entity/Q30"},
        "countryLabel": {"type": "literal", "value": "United States of America", "xml:lang": "en"},
        "person": {"type": "uri", "value": "http://www.wikidata.org/entity/Q6279"},
        "personLabel": {"type": "literal", "value": "Joe Biden", "xml:lang": "en"},
        "office": {"type": "uri", "value": "http://www.wikidata.org/entity/Q30461"},
        "officeLabel": {"type": "literal", "value": "President of the United States",
                        "xml:lang": "en"},
        "start": {"type": "date", "value": "2021-01-20T00:00:00Z"},
        "end": {"type": "date", "value": "2025-01-20T00:00:00Z"}
      }
    ]
  }
}
```

The parser turns each binding row into a flat record with columns:

- ``country_qid`` (e.g. ``Q30`` -- the QID suffix of the URI)
- ``country_label`` (English label of the country)
- ``person_qid`` (e.g. ``Q6279``)
- ``person_label`` (English label of the person)
- ``office_qid`` (the value node of P39, e.g. ``Q30461`` for head of state)
- ``office_label`` (English label of the office)
- ``start_date`` (ISO date string, or None if absent)
- ``end_date`` (ISO date string, or None if absent -- means "still in office")
- ``year`` (the calendar year of the start date, integer; None if the
  start date is absent)
- ``raw_value`` (JSON of the binding row, the verbatim audit trail)

The orchestrator then builds one source_observations row per binding
plus per catalog ``IndicatorSpec`` whose ``raw_column`` (office QID)
matches ``office_qid``.

The SPARQL query builder is also here (not in the http module) because
the query shape is the source's data contract, not the network
protocol. The query is parameterised by:

- a fixed set of office QIDs (passed via the catalog's ``raw_column``
  values);
- an optional year filter (``start_date <= year AND (end_date IS NULL
  OR end_date >= year)`` to find holders active during that year); and
- an optional country QID filter (VALUES clause on the ``country``
  variable).

The query always includes ``SERVICE wikibase:label`` for human-
readable labels in the response. The query returns all 8 columns
(country, countryLabel, person, personLabel, office, officeLabel,
start, end) plus the statement URI for the audit trail.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import pandas as pd

_logger = logging.getLogger(__name__)

#: Wikidata URI prefix -- the entity URI looks like
#: ``http://www.wikidata.org/entity/Q30``. The parser strips the
#: prefix to leave the bare QID (e.g. ``Q30``).
_WIKIDATA_ENTITY_URI_PREFIX: str = "http://www.wikidata.org/entity/"

#: A 10-character SHA-256 prefix is enough to disambiguate query
#: templates without bloating the cache key filename. See
#: :func:`wikidata_heads_of_state_government_http.build_cache_key`.
_QUERY_TEMPLATE_HASH_PREFIX_LEN: int = 10


# ---------------------------------------------------------------------------
# SPARQL query builder
# ---------------------------------------------------------------------------


def build_head_of_state_government_query(
    *,
    office_qids: list[str],
    year: int | None = None,
    country_qids: list[str] | None = None,
) -> str:
    """Build the canonical SPARQL query for "head of state / government" offices.

    Returns the SPARQL query string. The query is parameterised by:

    - ``office_qids`` -- the Wikidata office QIDs to look up (the
      catalog's ``raw_column`` values for the relevant rows). For
      example, ``Q30461`` (head of state) or ``Q22857062`` (head
      of government).
    - ``year`` (optional) -- when set, the query applies a start /
      end-date filter so only holders active during that calendar
      year are returned. When ``None``, the query returns every
      holder for every country.
    - ``country_qids`` (optional) -- when set, the query is
      ``VALUES``-scoped to those country QIDs only. When ``None``,
      the query returns holders for every country.

    The query uses the canonical Wikidata pattern for "who is / was
    the head of state of country X":

    - ``?person wdt:P39 ?office`` (truthy: person has the office)
    - ``?person wdt:P27 ?country`` (truthy: person's country of
      citizenship)
    - ``?person p:P39 ?statement`` (full statement)
    - ``?statement pq:P580 ?start`` (start time qualifier)
    - ``OPTIONAL { ?statement pq:P582 ?end }`` (end time qualifier)

    The country-of-citizenship qualifier pattern is more reliable
    than ``pq:P27`` on the P39 statement (which is inconsistently
    populated across Wikidata). The country is linked via the
    person item, which has consistent ``wdt:P27`` for every
    historical leader.

    Returns:
        A SPARQL query string with no leading whitespace; the query
        is suitable for direct URL submission via the SPARQL GET
        endpoint.

    Examples:
        >>> q = build_head_of_state_government_query(
        ...     office_qids=["Q30461"], year=2023
        ... )
        >>> "Q30461" in q
        True
        >>> "FILTER" in q  # year filter applied
        True
    """
    if not office_qids:
        raise ValueError("office_qids must be a non-empty list")
    # Normalise QIDs: strip leading "wd:" prefix if present (defensive),
    # strip whitespace, ensure they look like Qxxx.
    normalised: list[str] = []
    for raw in office_qids:
        cleaned = str(raw).strip()
        if cleaned.lower().startswith("wd:"):
            cleaned = cleaned[3:].strip()
        if not cleaned.startswith("Q"):
            raise ValueError(
                f"office_qid must start with 'Q'; got {raw!r}"
            )
        normalised.append(cleaned)
    office_values = " ".join(f"wd:{q}" for q in normalised)

    country_clause = ""
    if country_qids:
        cleaned_q: list[str] = []
        for raw in country_qids:
            q = str(raw).strip()
            if q.lower().startswith("wd:"):
                q = q[3:].strip()
            if not q.startswith("Q"):
                raise ValueError(
                    f"country_qid must start with 'Q'; got {raw!r}"
                )
            cleaned_q.append(q)
        country_values = " ".join(f"wd:{q}" for q in cleaned_q)
        country_clause = f"    VALUES ?country {{ {country_values} }}\n"

    year_clause = ""
    if year is not None:
        year_int = int(year)
        year_clause = (
            f"    FILTER(YEAR(?start) <= {year_int})\n"
            f"    FILTER(!BOUND(?end) || YEAR(?end) >= {year_int})\n"
        )

    # Build one triple-pattern UNION per office_qid so a single
    # SPARQL query can fetch multiple roles (head of state + head
    # of government) in a single round-trip.
    patterns: list[str] = []
    for office_qid in normalised:
        patterns.append(
            "    {\n"
            f"      ?person wdt:P39 wd:{office_qid} .\n"
            "    }"
        )
    office_union = "\n    UNION\n".join(patterns)

    query = (
        "SELECT ?country ?countryLabel ?person ?personLabel "
        "?office ?officeLabel ?start ?end ?statement WHERE {\n"
        f"    VALUES ?office {{ {office_values} }}\n"
        f"{country_clause}"
        f"{office_union}\n"
        "    ?person wdt:P27 ?country .\n"
        "    ?person p:P39 ?statement .\n"
        "    ?statement ps:P39 ?office .\n"
        "    ?statement pq:P580 ?start .\n"
        "    OPTIONAL { ?statement pq:P582 ?end }\n"
        "    SERVICE wikibase:label "
        "{ bd:serviceParam wikibase:language \"en\" }\n"
        f"{year_clause}"
        "}\n"
    )
    return query


def query_template_hash(office_qids: list[str]) -> str:
    """Return a short SHA-256 prefix that uniquely identifies the query template.

    The hash is over the **sorted** office QIDs only -- not over the
    year / country filters -- so the cache key distinguishes "I want
    to fetch different offices" (different template) from "I want to
    fetch the same offices for a different year / different country
    set" (same template, different parameter set; the cache key
    already encodes those parameters). This keeps the cache key
    stable across year-only changes while still invalidating if the
    SPARQL query shape itself changes in a future adapter
    revision.
    """
    joined = ",".join(sorted(office_qids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[
        :_QUERY_TEMPLATE_HASH_PREFIX_LEN
    ]


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _strip_wikidata_uri(uri: str) -> str:
    """Strip the Wikidata entity URI prefix from a SPARQL URI value.

    Example: ``http://www.wikidata.org/entity/Q30`` -> ``Q30``.
    Returns the input unchanged if it does not start with the prefix
    (defensive: some servers return the bare QID under a different
    binding shape).
    """
    if uri.startswith(_WIKIDATA_ENTITY_URI_PREFIX):
        return uri[len(_WIKIDATA_ENTITY_URI_PREFIX):]
    return uri


def _binding_value(
    binding: dict[str, Any],
    key: str,
    *,
    allow_none: bool = False,
) -> str:
    """Extract the ``value`` string from a SPARQL binding entry.

    The SPARQL JSON shape is ``{"<key>": {"type": "uri", "value": "..."}}``.
    For ``OPTIONAL`` clauses the entry may be ``None`` (the key is
    present with a JSON ``null`` value); for missing clauses the
    key may be absent. Returns ``""`` for both cases when
    ``allow_none`` is ``False``; returns ``None`` for the
    present-but-null case when ``allow_none`` is ``True``.
    """
    entry = binding.get(key)
    if entry is None:
        return "" if not allow_none else None
    if not isinstance(entry, dict):
        return "" if not allow_none else None
    value = entry.get("value")
    if value is None:
        return "" if not allow_none else None
    return str(value)


def _extract_year_from_date(date_value: str | None) -> int | None:
    """Extract the calendar year from an ISO date string.

    Returns ``None`` if the date is missing or malformed (defensive).
    Handles the ``YYYY-MM-DD...`` Wikidata date format (truncated
    before the ``T``).
    """
    if not isinstance(date_value, str) or not date_value:
        return None
    head = date_value.split("T", 1)[0]
    if len(head) < 4:
        return None
    try:
        return int(head[:4])
    except ValueError:
        return None


def parse_sparql_bindings(
    payload: dict[str, Any],
    *,
    office_qid: str,
    year: int | None = None,
) -> pd.DataFrame:
    """Parse a Wikidata SPARQL response into a long-format DataFrame.

    The returned frame has one row per SPARQL ``bindings`` entry and
    the columns documented in the module docstring. ``raw_value``
    carries the verbatim binding JSON so the audit trail survives a
    re-run that filters rows downstream.

    The ``office_qid`` argument is used as the ``office_qid`` column
    default when the binding does not include a literal office column
    (defensive -- the canonical SPARQL query always selects
    ``?office`` but a custom caller may pass a simpler query).

    The optional ``year`` argument is the requested year for the
    orchestrator's ``requested_year`` audit trail. It is NOT used to
    filter the bindings (the orchestrator handles that at the SPARQL
    query layer); the parser only records it for the audit trail
    column.
    """
    if not isinstance(payload, dict):
        raise ValueError(
            f"Wikidata SPARQL response is not a dict; got "
            f"{type(payload).__name__}"
        )
    bindings_obj = payload.get("results", {}).get("bindings", [])
    if not isinstance(bindings_obj, list):
        raise ValueError(
            f"Wikidata SPARQL response .results.bindings is not a "
            f"list; got {type(bindings_obj).__name__}"
        )

    rows: list[dict[str, object]] = []
    for binding in bindings_obj:
        if not isinstance(binding, dict):
            continue
        # Defensive: the SPARQL ``OPTIONAL ?end`` clause emits the
        # value ``null`` (Python ``None``) for "no end date" rather
        # than an empty dict. ``.get("end", {})`` would short-circuit
        # to an empty dict for a missing key, but a present-but-null
        # binding value (``"end": None``) requires an explicit
        # dict-or-None check before ``.get``.
        country = _binding_value(binding, "country")
        country_label = _binding_value(binding, "countryLabel")
        person = _binding_value(binding, "person")
        person_label = _binding_value(binding, "personLabel")
        office = _binding_value(binding, "office")
        office_label = _binding_value(binding, "officeLabel")
        start_date = _binding_value(binding, "start", allow_none=True)
        end_date = _binding_value(binding, "end", allow_none=True)
        statement_uri = _binding_value(binding, "statement")

        office_qid_resolved = (
            _strip_wikidata_uri(office) if office else office_qid
        )
        country_qid_resolved = (
            _strip_wikidata_uri(country) if country else ""
        )
        person_qid_resolved = (
            _strip_wikidata_uri(person) if person else ""
        )

        rows.append(
            {
                "country_qid": country_qid_resolved,
                "country_label": country_label,
                "person_qid": person_qid_resolved,
                "person_label": person_label,
                "office_qid": office_qid_resolved,
                "office_label": office_label,
                "start_date": start_date,
                "end_date": end_date,
                "statement_uri": statement_uri,
                "year": _extract_year_from_date(start_date),
                "requested_year": int(year) if year is not None else None,
                "raw_value": json.dumps(binding, ensure_ascii=False),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "country_qid",
            "country_label",
            "person_qid",
            "person_label",
            "office_qid",
            "office_label",
            "start_date",
            "end_date",
            "statement_uri",
            "year",
            "requested_year",
            "raw_value",
        ],
    )


__all__ = [
    "build_head_of_state_government_query",
    "parse_sparql_bindings",
    "query_template_hash",
]
