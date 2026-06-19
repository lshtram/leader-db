"""Stage 2 -- Wikidata heads-of-state-and-government read orchestrator.

This module holds the read orchestrator
(:func:`read_wikidata_heads_of_state_government`) that drives the
SPARQL fetch + parse + concat + pivot-free concat. The frame stays
long-format (one row per SPARQL binding) because the catalog's
``variable_name`` is per-office and the long row already carries the
office; no long-to-wide pivot is needed.

The HTTP + cache layer lives in
:mod:`wikidata_heads_of_state_government_http`. The catalog + paths
+ parquet write live in
:mod:`wikidata_heads_of_state_government_io`. The parser lives in
:mod:`wikidata_heads_of_state_government_parse`. The DB writes live
in :mod:`wikidata_heads_of_state_government_db`. The orchestrator
that ties everything together lives in
:mod:`wikidata_heads_of_state_government`.
"""

from __future__ import annotations

import logging

import pandas as pd

from .wikidata_heads_of_state_government_http import (
    build_cache_key,
    fetch_wikidata_sparql_payload,
)
from .wikidata_heads_of_state_government_io import (
    default_cache_dir,
    load_indicator_catalog,
)
from .wikidata_heads_of_state_government_parse import (
    build_head_of_state_government_query,
    parse_sparql_bindings,
    query_template_hash,
)

_logger = logging.getLogger(__name__)

__all__ = ["read_wikidata_heads_of_state_government"]


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def read_wikidata_heads_of_state_government(
    *,
    year: int | None = None,
    country_qids: list[str] | None = None,
    catalog_path: object = None,
    cache_dir: object = None,
    force_refresh: bool = False,
    request_timeout: float = 60.0,
) -> pd.DataFrame:
    """Read Wikidata heads-of-state for the given year + country set.

    Steps:

    1. Load the catalog (or use the explicit ``office_qids`` override).
    2. Build the canonical SPARQL query for the (year, country_qids)
       parameter combination. If ``office_qids`` is empty, the
       orchestrator raises ``ValueError`` (the catalog's
       ``variable_name`` must have at least one row).
    3. Compute the cache key from the (office_qids, year,
       country_qids, query_template_hash) tuple and look up the
       cached payload at
       ``<cache_dir>/<cache_key>.json``. If the cache file exists
       AND ``force_refresh`` is ``False``, read the cached JSON;
       else HTTP-GET the Wikidata SPARQL endpoint via
       :mod:`wikidata_heads_of_state_government_http`, write the
       verbatim response to the cache, then parse.
    4. Parse the SPARQL JSON response into a long-format DataFrame
       via :func:`parse_sparql_bindings`.
    5. Concat the per-office frames into the final long-format
       DataFrame (no wide pivot -- the Stage 2 frame carries the
       office_qid on every row, so the DB writer can join on
       office_qid -> catalog spec).

    The returned DataFrame carries two extra attributes on
    ``df.attrs`` so the orchestrator can surface them in
    :class:`WikidataHoSGoGIngestResult`:

    - ``df.attrs["indicators_cached"]`` -- count of catalog indicators
      that were read from the JSON cache (no HTTP call).
    - ``df.attrs["indicators_fetched"]`` -- count of catalog indicators
      that were HTTP-fetched in this call.

    Args:
        year: filter to a single calendar year. ``None`` (the default)
            returns all current holders (no end date) for every
            catalog office. When ``year`` is set the SPARQL query
            filters to holders active during that calendar year.
        country_qids: optional list of Wikidata country QIDs to scope
            the query. ``None`` (the default) returns holders for
            every country.
        catalog_path: override the indicator catalog. Default:
            checked-in.
        cache_dir: override the JSON cache root. Default: data-lake
            path
            (``data/raw/wikidata_heads_of_state_government/cache/``).
        force_refresh: re-download even when the cache file exists.
        request_timeout: per-request HTTP timeout in seconds.

    Returns:
        A long-format pandas DataFrame with columns
        ``country_qid``, ``country_label``, ``person_qid``,
        ``person_label``, ``office_qid``, ``office_label``,
        ``start_date``, ``end_date``, ``statement_uri``, ``year``,
        ``requested_year``, ``raw_value``. One row per SPARQL binding.

    Raises:
        ValueError: ``office_qids`` is empty (catalog has no data rows
            or the explicit list is empty).
        FileNotFoundError: no cached file and no network reachability
            (or ``force_refresh=True`` and HTTP fails).
        RuntimeError: the SPARQL endpoint returned a 4xx error
            (malformed query, rate-limit, etc.).
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    office_qids = [spec.raw_column for spec in specs]
    if not office_qids:
        raise ValueError(
            "Wikidata heads-of-state catalog has no data rows; "
            "expected at least one IndicatorSpec with a raw_column "
            "office QID."
        )

    cache_root = cache_dir or default_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    template_hash = query_template_hash(office_qids)

    long_frames: list[pd.DataFrame] = []
    cached_offices: set[str] = set()
    fetched_offices: set[str] = set()

    # One SPARQL query per (year, country_qids) parameter set, with
    # all offices in the catalog scoped via VALUES. The catalog has
    # a small number of offices (2 in the prototype); the Wikidata
    # SPARQL endpoint is highly available. The single-query design
    # keeps the cache count low and avoids hammering the endpoint.
    sparql_query = build_head_of_state_government_query(
        office_qids=office_qids,
        year=year,
        country_qids=country_qids,
    )
    cache_key = build_cache_key(
        office_qid="ALL",
        year=year,
        country_qids=country_qids,
        query_template_hash=template_hash,
    )
    cache_path = cache_root / f"{cache_key}.json"
    payload, came_from_cache = fetch_wikidata_sparql_payload(
        sparql_query,
        cache_path=cache_path,
        force_refresh=force_refresh,
        request_timeout=request_timeout,
    )
    if came_from_cache:
        cached_offices.update(office_qids)
    else:
        fetched_offices.update(office_qids)
    # Parse once for all offices (the SPARQL query already returns
    # the office column per binding, so the parser does not need to
    # be invoked per office).
    parsed = parse_sparql_bindings(
        payload, office_qid=office_qids[0], year=year,
    )
    long_frames.append(parsed)

    if not long_frames:
        df = pd.DataFrame(
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
            ]
        )
        df.attrs["indicators_cached"] = 0
        df.attrs["indicators_fetched"] = 0
        return df

    long_df = pd.concat(long_frames, ignore_index=True)
    # Carry cached/fetched counts through df.attrs so the
    # orchestrator can populate
    # ``WikidataHoSGoGIngestResult.indicators_cached/_fetched``
    # without re-inspecting the cache.
    df = long_df
    df.attrs["indicators_cached"] = len(cached_offices)
    df.attrs["indicators_fetched"] = len(fetched_offices)
    return df
