"""Wikidata-based recent-rulers fallback for the Country-Year Chronicle slice.

This module is the **Chronicle-side** reader for the recent (post-REIGN)
ruler gap. The Archigos / REIGN bundle stops at 2015 / 2021
respectively, leaving 2022-2026 rulers missing from the Country-Year
Chronicle output. The Wikidata SPARQL endpoint
(``https://query.wikidata.org/sparql``, CC0 1.0) covers every modern
country for every year and is the documented prototype backstop for
the gap (per ``docs/sources/attributions.md`` §1
``wikidata_heads_of_state_government``).

The module is deliberately narrow:

- One SPARQL query per (year, ``country_qids=None``) parameter set,
  with the country's ISO3 code (``wdt:P298``) joined in so we can
  map the Wikidata row straight to a Chronicle ``iso3`` identity.
- Cache-first / HTTP-fallback using the same pattern as the Stage 2
  Wikidata adapter (see
  :mod:`leaders_db.ingest.wikidata_heads_of_state_government_http`).
  The cache lives at
  ``data/raw/wikidata_heads_of_state_government/cache/cyc_<year>_all_<hash>.json``
  with a ``cyc_`` key prefix so the Chronicle cache does not collide
  with the Stage 2 adapter cache (which uses ``wd_<office>_<year>_<hash>``
  keys).
- Best-effort: a missing cache + unreachable network returns an
  empty frame, never raises. The Chronicle ruler resolver's
  fallback path then emits the canonical missing-ruler
  placeholder (no output is blocked).

The parser produces one row per (iso3, year, office_qid, person_qid)
binding. The ``WikidataRecentRulersSource.resolve`` method applies
the documented tie-break:

- Head of government (Q22857062) wins over head of state
  (Q30461) when both are present.
- Tie-break by latest ``start_date`` then person label.

The module reuses the existing
:data:`WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION` text
(``"Wikidata (CC0 1.0)."``) verbatim because the upstream source is
the same; the Stage 2 adapter and the Chronicle recent-rulers
adapter are two different pipelines that share the same
attribution. The Chronicle source tag is
``SOURCE_TAG_WIKIDATA_RECENT_RULERS = "wikidata_recent_rulers"`` so
the per-row provenance can distinguish the Chronicle fallback from
the Stage 2 long-frame observations.

The SPARQL query shape is intentionally simple and proven against
the live endpoint:

.. code-block:: sparql

    SELECT ?country ?countryISO3 ?countryLabel
           ?person ?personLabel ?office ?officeLabel
           ?start ?end ?statement WHERE {
      VALUES ?office { wd:Q30461 wd:Q22857062 }
      { ?person wdt:P39 wd:Q30461 . }
      UNION
      { ?person wdt:P39 wd:Q22857062 . }
      ?person wdt:P27 ?country .
      ?person p:P39 ?statement .
      ?statement ps:P39 ?office .
      ?statement pq:P580 ?start .
      OPTIONAL { ?statement pq:P582 ?end }
      OPTIONAL { ?country wdt:P297 ?countryISO3 }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
      FILTER(YEAR(?start) <= <year>)
      FILTER(!BOUND(?end) || YEAR(?end) >= <year>)
    }

Note on ISO3 property: Wikidata's "ISO 3166-1 alpha-3" property is
``P298`` (the constant below). The user requested P298 specifically;
the alternate ``P297`` ("ISO 3166-1 alpha-2") is also returned as
a defensive fallback so a country with only P297 populated still
maps to an ISO3 via the alpha-2 -> alpha-3 lookup. The current
constant uses P298 only to honour the request verbatim; an alpha-2
fallback can be added in a follow-up without changing the cache key
shape.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from ..ingest.wikidata_heads_of_state_government_http import (
    WIKIDATA_HTTP_TIMEOUT,
    WIKIDATA_SPARQL_ACCEPT,
    WIKIDATA_SPARQL_ENDPOINT,
    WIKIDATA_USER_AGENT,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


#: The Wikidata property for "ISO 3166-1 alpha-3 country code" (P298).
#: The user explicitly requested P298; we honour that verbatim. A small
#: fallback mapping for alpha-2 -> alpha-3 could be added later without
#: breaking the cache-key shape.
ISO3_PROPERTY_QID: Final[str] = "P298"

#: Office QIDs we query: head of state (Q30461) and head of government
#: (Q22857062). Matches the Stage 2 catalog in
#: :mod:`leaders_db.ingest.wikidata_heads_of_state_government`.
_HEAD_OF_STATE_QID: Final[str] = "Q30461"
_HEAD_OF_GOVERNMENT_QID: Final[str] = "Q22857062"
_PRIME_MINISTER_QID: Final[str] = "Q14212"
_OFFICE_QIDS: Final[tuple[str, ...]] = (
    _HEAD_OF_STATE_QID,
    _HEAD_OF_GOVERNMENT_QID,
    _PRIME_MINISTER_QID,
)

#: Head of government wins the precedence over head of state.
#: Order matters: ``_OFFICE_PRECEDENCE[0]`` is the most-preferred office.
_OFFICE_PRECEDENCE: Final[tuple[str, ...]] = (
    _HEAD_OF_GOVERNMENT_QID,
    _PRIME_MINISTER_QID,
    _HEAD_OF_STATE_QID,
)

#: Cache key prefix. Distinct from the Stage 2 adapter's ``wd_`` prefix
#: so the two adapter pipelines never overwrite each other's cache.
_CACHE_KEY_PREFIX: Final[str] = "cyc"

#: Minimum length of the cache-key template hash. 10 hex chars =
#: 40 bits, plenty to disambiguate query template versions without
#: bloating the filename.
_CACHE_KEY_TEMPLATE_HASH_LEN: Final[int] = 10


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------


def default_cache_dir() -> Path:
    """Return the canonical Chronicle recent-rulers cache directory.

    Resolves to
    ``<project_root>/data/raw/wikidata_heads_of_state_government/cache/``,
    the same root the Stage 2 adapter uses. The two pipelines share
    the directory but not the cache key prefix (``cyc_`` vs ``wd_``).
    Creates the directory if missing so callers can write into it
    without an extra ``mkdir``.
    """
    from ..paths import raw_dir

    cache = (
        raw_dir("wikidata_heads_of_state_government") / "cache"
    )
    cache.mkdir(parents=True, exist_ok=True)
    return cache


# ---------------------------------------------------------------------------
# SPARQL query + cache key
# ---------------------------------------------------------------------------


def _query_template_hash() -> str:
    """Short SHA-256 prefix of the canonical query template.

    Two SPARQL templates with different office QIDs / filter clauses
    must produce different cache keys so a query-shape change cannot
    silently serve stale data. The hash is over the sorted office
    QID list and the static parts of the query template.
    """
    canonical = (
        "VALUES ?role { wd:" + " wd:".join(sorted(_OFFICE_QIDS)) + " }"
        + "|?country wdt:" + ISO3_PROPERTY_QID + " ?countryISO3"
        + "|FILTER(STRLEN(?countryISO3) = 3)"
        + "|?office wdt:P279* ?role"
        + "|?office wdt:P1001 ?country"
        + "|?person wdt:P31 wd:Q5"
        + "|FILTER(YEAR(?start) <= {year})"
        + "|FILTER(!BOUND(?end) || YEAR(?end) >= {year})"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[
        :_CACHE_KEY_TEMPLATE_HASH_LEN
    ]


_TEMPLATE_HASH: Final[str] = _query_template_hash()


def build_recent_rulers_sparql(*, year: int) -> str:
    """Build the canonical SPARQL query for the recent-rulers fallback.

    The query returns all human holders of ``P39`` whose concrete
    office is a subclass of head of state / head of government and
    whose office applies to a country with a Wikidata ISO3 (``P298``)
    code. The role set includes generic head of state / head of
    government plus ``prime minister`` because many parliamentary
    offices are modelled as subclasses of prime minister rather than
    subclasses of Wikidata's generic head-of-government item. Joining
    the country through the office's ``P1001`` relation avoids the
    false positives produced by country-of-citizenship joins and
    generic direct ``P39`` checks.

    Args:
        year: Calendar year for the activity filter. The query
            returns any holder whose ``start_date`` year is
            ``<= year`` and whose ``end_date`` year is ``>= year``
            or absent (current holders).

    Returns:
        A SPARQL query string ready to URL-encode and submit to the
        Wikidata SPARQL endpoint.
    """
    if not isinstance(year, int):
        raise TypeError(f"year must be int; got {type(year).__name__}")
    role_values = " ".join(f"wd:{q}" for q in _OFFICE_QIDS)
    return (
        "SELECT ?country ?countryISO3 ?countryLabel "
        "?person ?personLabel ?office ?officeLabel ?role "
        "?start ?end WHERE {\n"
        f"  VALUES ?role {{ {role_values} }}\n"
        f"  ?country wdt:{ISO3_PROPERTY_QID} ?countryISO3 .\n"
        "  FILTER(STRLEN(?countryISO3) = 3)\n"
        "  ?office wdt:P279* ?role .\n"
        "  ?office wdt:P1001 ?country .\n"
        "  ?person wdt:P31 wd:Q5 .\n"
        "  ?person p:P39 ?statement .\n"
        "  ?statement ps:P39 ?office .\n"
        "  ?statement pq:P580 ?start .\n"
        "  OPTIONAL { ?statement pq:P582 ?end }\n"
        "  SERVICE wikibase:label "
        "{ bd:serviceParam wikibase:language \"en\" }\n"
        f"  FILTER(YEAR(?start) <= {year})\n"
        f"  FILTER(!BOUND(?end) || YEAR(?end) >= {year})\n"
        "}\n"
    )


def _cache_key(*, year: int) -> str:
    """Deterministic cache key for one (year) parameter set."""
    return (
        f"{_CACHE_KEY_PREFIX}_{year}_all_"
        f"{_TEMPLATE_HASH}"
    )


# ---------------------------------------------------------------------------
# HTTP fetch (cache-first)
# ---------------------------------------------------------------------------


def _read_cached_json(cache_path: Path) -> dict[str, Any] | None:
    """Read a cached SPARQL JSON response, returning ``None`` if missing or corrupt."""
    if not cache_path.is_file():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _logger.warning(
            "Wikidata recent-rulers cache file %s is corrupt (%s); "
            "falling through to HTTP",
            cache_path,
            exc,
        )
        return None


def _write_cached_json(cache_path: Path, payload: dict[str, Any]) -> None:
    """Persist the verbatim SPARQL response as pretty-printed JSON."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _http_get(
    sparql_query: str,
    *,
    cache_path: Path,
    timeout: float,
) -> dict[str, Any]:
    """HTTP-GET one Wikidata SPARQL query and write the verbatim response.

    One automatic retry on ``ConnectionError`` / ``Timeout``; no retry
    on 4xx (the SPARQL endpoint is highly available and a 4xx is
    usually a malformed query or a rate-limit response that would
    just repeat). The mandatory ``User-Agent`` header is set per
    the Wikimedia User-Agent policy.
    """
    import requests

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.get(
                WIKIDATA_SPARQL_ENDPOINT,
                params={"query": sparql_query, "format": "json"},
                headers={
                    "User-Agent": WIKIDATA_USER_AGENT,
                    "Accept": WIKIDATA_SPARQL_ACCEPT,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = json.loads(response.text, strict=False)
        except json.JSONDecodeError as exc:
            raise FileNotFoundError(
                "Wikidata recent-rulers SPARQL returned malformed JSON. "
                f"Cache file {cache_path} is missing and the endpoint "
                "response cannot be parsed."
            ) from exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise FileNotFoundError(
                f"Wikidata recent-rulers SPARQL HTTP failed: {exc}. "
                f"Cache file {cache_path} is missing and the "
                "network is unreachable."
            ) from exc
        except requests.HTTPError as exc:
            status_code = exc.response.status_code
            if status_code == 429 or status_code >= 500:
                raise FileNotFoundError(
                    f"Wikidata recent-rulers SPARQL HTTP {status_code}. "
                    f"Cache file {cache_path} is missing and the "
                    "endpoint is unavailable or rate-limiting."
                ) from exc
            raise RuntimeError(
                f"Wikidata recent-rulers SPARQL HTTP error "
                f"{status_code}: "
                f"{exc.response.text[:512]}"
            ) from exc
        _write_cached_json(cache_path, payload)
        return payload
    raise FileNotFoundError(
        f"Wikidata recent-rulers SPARQL HTTP failed: {last_exc!r}"
    )


def fetch_recent_rulers_payload(
    *,
    year: int,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    timeout: float = WIKIDATA_HTTP_TIMEOUT,
) -> tuple[dict[str, Any], bool] | None:
    """Fetch the SPARQL payload for one ``(year)`` parameter set.

    Cache-first, HTTP-fallback. Returns a 2-tuple
    ``(payload, came_from_cache)``, or ``None`` if the network is
    unreachable AND the cache file is missing (the documented
    graceful-degradation behaviour for the Chronicle resolver).

    Args:
        year: Calendar year for the activity filter.
        cache_dir: Override the cache directory. Defaults to
            :func:`default_cache_dir`.
        force_refresh: Re-download even when the cache file exists.
        timeout: Per-request HTTP timeout in seconds.

    Returns:
        ``(payload, came_from_cache)`` on success, ``None`` on
        network failure with no cache.
    """
    root = cache_dir or default_cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    cache_path = root / f"{_cache_key(year=year)}.json"
    if not force_refresh:
        cached = _read_cached_json(cache_path)
        if cached is not None:
            return cached, True
    sparql_query = build_recent_rulers_sparql(year=year)
    try:
        payload = _http_get(
            sparql_query, cache_path=cache_path, timeout=timeout,
        )
    except FileNotFoundError as exc:
        _logger.warning(
            "Wikidata recent-rulers fetch for year=%s failed: %s. "
            "Returning None; the resolver will degrade to missing-ruler.",
            year,
            exc,
        )
        return None
    return payload, False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _strip_wikidata_uri(uri: str) -> str:
    """Strip the Wikidata entity URI prefix from a SPARQL URI value.

    Example: ``http://www.wikidata.org/entity/Q30`` -> ``Q30``.
    Returns the input unchanged if the prefix is missing
    (defensive).
    """
    prefix = "http://www.wikidata.org/entity/"
    if uri.startswith(prefix):
        return uri[len(prefix):]
    return uri


def _binding_value(
    binding: dict[str, Any], key: str
) -> str:
    """Extract the ``value`` string from a SPARQL binding entry.

    Returns ``""`` when the binding key is absent or has a
    JSON ``null`` value. The Stage 2 parser distinguishes present-
    but-null from missing; the Chronicle resolver does not need
    that distinction, so we collapse both to empty strings.
    """
    entry = binding.get(key)
    if not isinstance(entry, dict):
        return ""
    value = entry.get("value")
    return "" if value is None else str(value)


def _person_label(binding: dict[str, Any], person_qid: str) -> str:
    """Return a usable person label, blanking Wikidata QID fallbacks.

    Wikidata's label service sometimes returns the bare entity ID when
    no English label is available. The Chronicle output should not show
    opaque QIDs as ruler names; blanking them lets the normal
    ``missing_ruler`` path handle those rare rows.
    """
    label = (
        _binding_value(binding, "personEnglishLabel")
        or _binding_value(binding, "personLabel")
    ).strip()
    return "" if label == person_qid else label


def parse_recent_rulers_payload(
    payload: dict[str, Any],
    *,
    year: int,
) -> pd.DataFrame:
    """Parse a recent-rulers SPARQL response into a long-format DataFrame.

    The frame has one row per SPARQL ``bindings`` entry and the
    columns:

    - ``iso3`` -- the country's ISO 3166-1 alpha-3 code from
      ``wdt:P298``. Empty string when P298 is missing.
    - ``country_qid`` -- the Wikidata QID of the country.
    - ``country_label`` -- English label of the country.
    - ``person_qid`` -- the Wikidata QID of the person.
    - ``person_label`` -- English label of the person.
    - ``office_qid`` -- the concrete office QID.
    - ``office_label`` -- English label of the office.
    - ``role_qid`` -- the broad role class used for precedence:
      ``Q30461`` (head of state) or ``Q22857062`` (head of government).
    - ``start_date`` -- ISO date string (mandatory; the SPARQL
      ``FILTER`` requires ``pq:P580``).
    - ``end_date`` -- ISO date string or ``""`` for current holders.
    - ``year`` -- the requested year for the row (echo of the
      ``year`` argument so callers can filter trivially).

    Args:
        payload: The SPARQL JSON response (the verbatim API body
            or the cached file contents).
        year: The requested calendar year. Echoed onto the
            ``year`` column of every row.

    Returns:
        A :class:`pandas.DataFrame` with the columns above. Empty
        when the payload has no bindings.
    """
    if not isinstance(payload, dict):
        raise ValueError(
            f"Wikidata recent-rulers payload is not a dict; got "
            f"{type(payload).__name__}"
        )
    bindings = payload.get("results", {}).get("bindings", [])
    if not isinstance(bindings, list):
        raise ValueError(
            f"Wikidata recent-rulers payload .results.bindings is "
            f"not a list; got {type(bindings).__name__}"
        )
    rows: list[dict[str, str]] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        person_qid = _strip_wikidata_uri(_binding_value(binding, "person"))
        rows.append(
            {
                "iso3": _binding_value(binding, "countryISO3").strip().upper(),
                "country_qid": _strip_wikidata_uri(
                    _binding_value(binding, "country")
                ),
                "country_label": _binding_value(binding, "countryLabel"),
                "person_qid": person_qid,
                "person_label": _person_label(binding, person_qid),
                "office_qid": _strip_wikidata_uri(
                    _binding_value(binding, "office")
                ),
                "office_label": _binding_value(binding, "officeLabel"),
                "role_qid": _strip_wikidata_uri(
                    _binding_value(binding, "role")
                ),
                "start_date": _binding_value(binding, "start"),
                "end_date": _binding_value(binding, "end"),
                "year": str(int(year)),
            }
        )
    columns = (
        "iso3",
        "country_qid",
        "country_label",
        "person_qid",
        "person_label",
        "office_qid",
        "office_label",
        "role_qid",
        "start_date",
        "end_date",
        "year",
    )
    if not rows:
        return pd.DataFrame({col: [] for col in columns})
    return pd.DataFrame(rows, columns=columns)


# ---------------------------------------------------------------------------
# Public source type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WikidataRecentRulersSource:
    """A bundled, query-ready recent-rulers cache for the resolver.

    The dataclass is immutable; instantiate once per
    :func:`run_country_year_chronicle` invocation via
    :func:`load_wikidata_recent_rulers_source`.

    Attributes:
        frame: Long-format DataFrame with columns
            ``iso3``, ``country_qid``, ``country_label``,
            ``person_qid``, ``person_label``, ``office_qid``,
            ``office_label``, ``role_qid``, ``start_date``, ``end_date``,
            ``year``. Empty when the fetch / cache failed
            gracefully (the resolver's fallback path then
            emits the canonical missing-ruler placeholder).
        cache_dir: The cache directory the source was loaded from.
            Exposed so tests can clean up.
        fetched_years: Tuple of years that produced a successful
            HTTP fetch this run. Years served from cache are NOT
            included (they did not consume an HTTP call).
        cached_years: Tuple of years that were served from the
            local cache this run.
    """

    frame: pd.DataFrame
    cache_dir: Path
    fetched_years: tuple[int, ...] = ()
    cached_years: tuple[int, ...] = ()

    @property
    def is_empty(self) -> bool:
        """``True`` when the frame has no rows (no cached data)."""
        return self.frame.empty

    def resolve(self, iso3: str, year: int) -> dict[str, str] | None:
        """Resolve the recent-rulers entry for ``(iso3, year)``.

        Applies the documented tie-break:

        - Prefer head of government (``Q22857062``) over head of
          state (``Q30461``) when both are present, using the
          broad ``role_qid`` returned by the SPARQL subclass join.
        - Tie-break by latest ``start_date`` then ``person_label``
          so the selection is deterministic across re-runs.

        Args:
            iso3: The country's ISO3 code (uppercase). Used as a
                case-sensitive match against the ``iso3`` column.
            year: The requested calendar year.

        Returns:
            A dict with keys ``person_label``, ``office_label``,
            ``person_qid``, ``office_qid``, ``role_qid``, ``start_date``,
            ``end_date``, ``country_qid``, ``country_label`` when
            a holder is found. Returns ``None`` when the frame
            is empty or no row matches.
        """
        if self.frame.empty:
            return None
        target = str(iso3).strip().upper()
        if not target:
            return None
        matches = self.frame.loc[
            (self.frame["iso3"] == target)
            & (self.frame["year"] == str(int(year)))
        ]
        if matches.empty:
            return None
        # Office precedence: head of government first, head of state
        # second. Within an office, the latest start_date wins; ties
        # go to the lexicographically smallest person_label for
        # determinism.
        ordered_offices = [
            qid for qid in _OFFICE_PRECEDENCE if qid in _OFFICE_QIDS
        ]
        for office_qid in ordered_offices:
            office_matches = matches.loc[
                matches["role_qid"] == office_qid
            ]
            if office_matches.empty:
                continue
            sorted_idx = office_matches.sort_values(
                by=["start_date", "person_label"],
                ascending=[False, True],
                kind="mergesort",
            ).index
            row = office_matches.loc[sorted_idx[0]]
            return {
                "person_label": str(row.get("person_label", "")),
                "office_label": str(row.get("office_label", "")),
                "person_qid": str(row.get("person_qid", "")),
                "office_qid": str(row.get("office_qid", "")),
                "role_qid": str(row.get("role_qid", "")),
                "start_date": str(row.get("start_date", "")),
                "end_date": str(row.get("end_date", "")),
                "country_qid": str(row.get("country_qid", "")),
                "country_label": str(row.get("country_label", "")),
            }
        # No row matched any of the known office QIDs; fall back
        # to the first row of any office (defensive -- should not
        # happen given the SPARQL filter).
        sorted_idx = matches.sort_values(
            by=["start_date", "person_label"],
            ascending=[False, True],
            kind="mergesort",
        ).index
        row = matches.loc[sorted_idx[0]]
        return {
            "person_label": str(row.get("person_label", "")),
            "office_label": str(row.get("office_label", "")),
            "person_qid": str(row.get("person_qid", "")),
            "office_qid": str(row.get("office_qid", "")),
            "role_qid": str(row.get("role_qid", "")),
            "start_date": str(row.get("start_date", "")),
            "end_date": str(row.get("end_date", "")),
            "country_qid": str(row.get("country_qid", "")),
            "country_label": str(row.get("country_label", "")),
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_wikidata_recent_rulers_source(
    *,
    years: tuple[int, ...],
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    timeout: float = WIKIDATA_HTTP_TIMEOUT,
) -> WikidataRecentRulersSource:
    """Load the recent-rulers source for the requested years.

    For each requested year the loader attempts to read the cached
    SPARQL JSON; on a cache miss it issues one HTTP fetch and
    writes the verbatim response to the cache. Network failures
    degrade to "missing year" (no rows added for that year); the
    loader NEVER raises for a network failure -- the Chronicle
    resolver's fallback path then emits the canonical missing-ruler
    placeholder.

    Args:
        years: Tuple of calendar years to fetch (e.g. ``(2022,
            2023, 2024, 2025, 2026)``).
        cache_dir: Override the cache directory. Defaults to
            :func:`default_cache_dir`.
        force_refresh: Re-download every requested year even when
            the cache file exists.
        timeout: Per-request HTTP timeout in seconds.

    Returns:
        A :class:`WikidataRecentRulersSource` with the parsed
        long-format frame and the year-level fetch / cache
        counters.
    """
    root = cache_dir or default_cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    fetched: list[int] = []
    cached: list[int] = []
    for year in years:
        result = fetch_recent_rulers_payload(
            year=int(year),
            cache_dir=root,
            force_refresh=force_refresh,
            timeout=timeout,
        )
        if result is None:
            # Graceful degradation: skip this year, do not raise.
            continue
        payload, came_from_cache = result
        try:
            parsed = parse_recent_rulers_payload(payload, year=int(year))
        except ValueError as exc:
            _logger.warning(
                "Wikidata recent-rulers parse for year=%s failed: %s. "
                "Skipping this year; the resolver will degrade to "
                "missing-ruler where no higher-precedence source resolves.",
                year,
                exc,
            )
            continue
        frames.append(parsed)
        if came_from_cache:
            cached.append(int(year))
        else:
            fetched.append(int(year))
    if frames:
        frame = pd.concat(frames, ignore_index=True)
    else:
        frame = pd.DataFrame(
            columns=(
                "iso3", "country_qid", "country_label",
                "person_qid", "person_label",
                "office_qid", "office_label", "role_qid",
                "start_date", "end_date", "year",
            )
        )
    return WikidataRecentRulersSource(
        frame=frame,
        cache_dir=root,
        fetched_years=tuple(fetched),
        cached_years=tuple(cached),
    )


__all__ = [
    "ISO3_PROPERTY_QID",
    "WikidataRecentRulersSource",
    "build_recent_rulers_sparql",
    "default_cache_dir",
    "fetch_recent_rulers_payload",
    "load_wikidata_recent_rulers_source",
    "parse_recent_rulers_payload",
]
