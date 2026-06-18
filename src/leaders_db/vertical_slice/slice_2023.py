"""2023 vertical slice orchestrator.

The public seam is :func:`run_vertical_slice_2023`. It is named after
the architecture doc (``docs/architecture/vertical-slice-2023.md``)
and intentionally does NOT generalize into the real Stage 3-15
pipeline. The slice:

1. Locates the client xlsx in ``data/raw/client_existing/``.
2. Parses the scoped rows via :func:`load_vertical_slice_client_rows`.
3. Upserts MEX/NGA/USA countries + 2023 ``country_years``.
4. Links ISO3-bearing ``source_observations`` by their
   ``<prefix>:<ISO3>`` pattern.
5. Seeds ``leaders``, ``ruler_spells``, ``ruler_years`` as
   ``client_only`` slice rows.
6. Computes provisional scores for the scoped categories.
7. Writes ``ruler_scores`` and ``validation_results``.
8. Writes ``data/outputs/vertical_slice_2023/*.csv|*.md``.

The orchestrator is idempotent: re-running it keeps countries,
country_years, leaders, score_categories, and Stage 2
``source_observations`` untouched and re-inserts only slice-owned rows.

DB row writers live in :mod:`persistence`; this module owns the
orchestration flow only.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import RunConfig
from ..db.models import Country
from ..db.session import default_sqlite_url, session_scope
from ..ingest import undp_hdi, wgi
from ..paths import project_root, raw_dir
from .constants import (
    DEFAULT_CATEGORIES,
    DEFAULT_COUNTRIES,
    SLICE_PREFERRED_NAME_BY_ISO3,
)
from .countries_seeding import (
    link_iso3_observations,
    seed_countries,
    seed_country_years,
)
from .outputs import (
    ComparisonRow,
    ScoreRow,
    write_comparison_csv,
    write_scores_csv,
    write_summary_md,
)
from .parser import ClientSliceRow, load_vertical_slice_client_rows
from .persistence import (
    SKIP_NO_OBSERVATION,
    delete_slice_owned_rows,
    insert_ruler_spell,
    insert_ruler_year,
    requires_human_review,
    source_key_for_category,
    upsert_leader,
    upsert_score_categories,
    validation_status_for,
    write_ruler_score,
    write_validation_row,
)
from .scoring import ScoreResult, gather_inputs, score_one

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class VerticalSliceResult(BaseModel):
    """Summary of one ``run_vertical_slice_2023`` invocation.

    All fields are populated by the orchestrator; tests use them to
    assert row counts and output paths.
    """

    target_year: int = Field(..., ge=1900, le=2100)
    countries: tuple[str, ...]
    categories: tuple[str, ...]
    client_rows_parsed: int = Field(..., ge=0)
    countries_seeded: int = Field(..., ge=0)
    observations_linked: int = Field(..., ge=0)
    ruler_years_written: int = Field(..., ge=0)
    score_rows_written: int = Field(..., ge=0)
    validation_rows_written: int = Field(..., ge=0)
    score_csv_path: Path
    comparison_csv_path: Path
    summary_md_path: Path
    skipped: tuple[tuple[str, str, str], ...] = Field(default_factory=tuple)
    sources_used: tuple[str, ...] = Field(default_factory=tuple)
    client_xlsx_path: Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_vertical_slice_2023(
    config: RunConfig,
    *,
    countries: Sequence[str] | None = None,
    categories: Sequence[str] | None = None,
    run_adapters: bool = True,
    database_url: str | None = None,
    client_xlsx: Path | None = None,
) -> VerticalSliceResult:
    """Run the 2023 vertical slice end-to-end.

    Args:
        config: a :class:`RunConfig` (used for the target year and DB URL
            resolution; the slice's defaults override ``countries`` and
            ``categories`` if those kwargs are not provided).
        countries: ISO3 scope. Defaults to ``("MEX", "NGA", "USA")``.
        categories: categories to score. Defaults to
            ``("social_wellbeing", "integrity")``.
        run_adapters: when ``True``, the orchestrator will try to call
            the UNDP HDI Stage 2 adapter (and WGI if the xlsx is
            locally available). When ``False``, only the already-staged
            ``source_observations`` rows are consumed.
        database_url: override the SQLite URL. Defaults to the
            ``RunConfig`` URL or the :func:`default_sqlite_url` from
            :mod:`leaders_db.db.session`.
        client_xlsx: override the client xlsx path. Defaults to the
            first xlsx found under ``data/raw/client_existing/``.

    Returns:
        A :class:`VerticalSliceResult` with row counts and output paths.
    """
    iso3_scope = tuple(c.upper() for c in (countries or DEFAULT_COUNTRIES))
    category_scope = tuple(categories or DEFAULT_CATEGORIES)
    target_year = config.project.target_year
    # Prefer the explicit ``database_url``; otherwise honor the env-var
    # override (``LEADERSDB_PROJECT_ROOT``) via :func:`default_sqlite_url`
    # so the test fixture can redirect to a temp DB. ``config.database.url``
    # is the production path (relative to CWD), which only matches when
    # the user is CWD'd at the project root.
    if database_url:
        db_url = database_url
    else:
        db_url = default_sqlite_url()

    # Adapter DB targeting is not wired for this slice. The Stage 2
    # adapters (UNDP HDI, WGI) resolve the DB through :func:`session_scope`
    # using ``LEADERSDB_PROJECT_ROOT`` / the default URL, so they cannot
    # be told to write into an explicit ``database_url``. Reject the
    # combination rather than silently writing adapters and slice into
    # different SQLite files (reviewer blocker 3).
    if run_adapters and database_url:
        raise ValueError(
            "run_vertical_slice_2023 does not support run_adapters=True with "
            "an explicit database_url: the Stage 2 adapters resolve the DB "
            "through the default SQLite URL, while the slice would persist "
            "into the explicit database_url. Either drop --run-adapters (the "
            "slice can read already-staged source_observations rows) or drop "
            "--database-url (let both resolve through LEADERSDB_PROJECT_ROOT)."
        )

    resolved_xlsx = client_xlsx or _locate_client_xlsx()
    client_rows = load_vertical_slice_client_rows(
        path=resolved_xlsx,
        sheet="Main",
        year=target_year,
        iso3_scope=iso3_scope,
    )

    if run_adapters:
        _maybe_run_adapters(target_year=target_year, db_url=db_url)

    with session_scope(db_url) as session:
        # Idempotency sweep: delete slice-owned rows for the scoped
        # countries/year so a rerun produces deterministic counts.
        delete_slice_owned_rows(
            session, iso3_scope=iso3_scope, target_year=target_year
        )

        country_ids = seed_countries(
            session,
            iso3s=iso3_scope,
            preferred_names=_preferred_names_for(iso3_scope),
        )
        population_by_iso3 = {
            row.iso3: row.population_raw for row in client_rows
        }
        seed_country_years(
            session,
            country_ids=country_ids,
            target_year=target_year,
            population_by_iso3=population_by_iso3,
        )
        observations_linked = link_iso3_observations(
            session, country_ids=country_ids
        )

        category_ids = upsert_score_categories(session, category_scope)

        ruler_year_ids: dict[str, int] = {}
        leader_ids: dict[str, int] = {}
        for client_row in client_rows:
            leader_id = upsert_leader(session, client_row)
            spell_id = insert_ruler_spell(
                session,
                leader_id=leader_id,
                country_id=country_ids[client_row.iso3],
                client_row=client_row,
                target_year=target_year,
            )
            ruler_year_id = insert_ruler_year(
                session,
                leader_id=leader_id,
                country_id=country_ids[client_row.iso3],
                spell_id=spell_id,
                client_row=client_row,
                target_year=target_year,
            )
            ruler_year_ids[client_row.iso3] = ruler_year_id
            leader_ids[client_row.iso3] = leader_id

        (
            score_rows, comparison_rows, skipped,
            direct_year_count, proxy_year_count, sources_used,
        ) = _compute_scores(
            session,
            client_rows=client_rows,
            country_ids=country_ids,
            ruler_year_ids=ruler_year_ids,
            category_ids=category_ids,
            category_scope=category_scope,
            target_year=target_year,
        )

    output_root = _project_root()
    scores_path = write_scores_csv(score_rows, root=output_root)
    comparison_path = write_comparison_csv(comparison_rows, root=output_root)
    summary_path = write_summary_md(
        score_rows=score_rows,
        comparison_rows=comparison_rows,
        countries=iso3_scope,
        categories=category_scope,
        target_year=target_year,
        sources_used=tuple(sorted(sources_used)),
        direct_year_count=direct_year_count,
        proxy_year_count=proxy_year_count,
        skipped=skipped,
        root=output_root,
    )

    return VerticalSliceResult(
        target_year=target_year,
        countries=iso3_scope,
        categories=category_scope,
        client_rows_parsed=len(client_rows),
        countries_seeded=len({row.iso3 for row in client_rows}),
        observations_linked=observations_linked,
        ruler_years_written=len(ruler_year_ids),
        score_rows_written=len(score_rows),
        validation_rows_written=len(score_rows),
        score_csv_path=scores_path,
        comparison_csv_path=comparison_path,
        summary_md_path=summary_path,
        skipped=tuple(skipped),
        sources_used=tuple(sorted(sources_used)),
        client_xlsx_path=resolved_xlsx,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _preferred_names_for(iso3_scope: Sequence[str]) -> dict[str, str]:
    return {iso3: SLICE_PREFERRED_NAME_BY_ISO3.get(iso3, iso3) for iso3 in iso3_scope}


def _project_root() -> Path:
    return project_root()


def _compute_scores(
    session: Session,
    *,
    client_rows: list[ClientSliceRow],
    country_ids: dict[str, int],
    ruler_year_ids: dict[str, int],
    category_ids: dict[str, int],
    category_scope: Sequence[str],
    target_year: int,
) -> tuple[
    list[ScoreRow],
    list[ComparisonRow],
    list[tuple[str, str, str]],
    int,
    int,
    set[str],
]:
    """Compute and persist scores + validation rows; return output rows.

    The returned tuple holds:

    - ``score_rows`` — one :class:`ScoreRow` per written ``ruler_scores``.
    - ``comparison_rows`` — one :class:`ComparisonRow` per (country, category).
      Includes ``skip_reason`` rows that did NOT persist a ``ruler_scores``
      row (architecture §8 + §9: missing sources emit a comparison row
      and a skipped note only).
    - ``skipped`` — list of ``(iso3, category, reason)`` for missing inputs.
    - ``direct_year_count`` / ``proxy_year_count`` — used in the summary.
    - ``sources_used`` — set of source keys with at least one observation.
    """
    score_rows: list[ScoreRow] = []
    comparison_rows: list[ComparisonRow] = []
    skipped: list[tuple[str, str, str]] = []
    direct_year_count = 0
    proxy_year_count = 0
    sources_used: set[str] = set()

    for client_row in client_rows:
        iso3 = client_row.iso3
        country = session.execute(
            select(Country).where(Country.id == country_ids[iso3])
        ).scalar_one()
        country_label = country.country_name

        for category_key in category_scope:
            client_score = client_row.client_scores.get(category_key)
            inputs = gather_inputs(
                session,
                country_id=country_ids[iso3],
                category_key=category_key,
                target_year=target_year,
            )
            if inputs is None:
                continue  # category not in slice scope

            score = score_one(inputs)

            if score.skip_reason is not None:
                # Missing source: emit a comparison row + skipped note ONLY.
                # Per architecture §8 ("skip integrity rows rather than
                # inventing a score") and reviewer blocker 1, do NOT write
                # RulerScore / ValidationResult / ScoreRow in this branch.
                comparison_rows.append(_make_comparison_row(
                    client_row=client_row,
                    category_key=category_key,
                    country_label=country_label,
                    target_year=target_year,
                    client_score=client_score,
                    rs=None,
                    score=score,
                ))
                skipped.append((iso3, category_key, score.skip_reason))
                continue

            direct_year_count, proxy_year_count, sources_used = _bump_counters(
                score=score,
                direct_year_count=direct_year_count,
                proxy_year_count=proxy_year_count,
                sources_used=sources_used,
            )

            rs = write_ruler_score(
                session,
                ruler_year_id=ruler_year_ids[iso3],
                category_id=category_ids[category_key],
                client_score=client_score,
                score=score,
            )
            write_validation_row(
                session,
                ruler_score_id=rs.id,
                score=score,
                client_score=client_score,
                source_year=score.source_year,
                target_year=target_year,
            )

            score_rows.append(_make_score_row(
                client_row=client_row,
                category_key=category_key,
                country_label=country_label,
                target_year=target_year,
                client_score=client_score,
                rs=rs,
                score=score,
                inputs=inputs,
            ))
            comparison_rows.append(_make_comparison_row(
                client_row=client_row,
                category_key=category_key,
                country_label=country_label,
                target_year=target_year,
                client_score=client_score,
                rs=rs,
                score=score,
            ))

    return (
        score_rows,
        comparison_rows,
        skipped,
        direct_year_count,
        proxy_year_count,
        sources_used,
    )


def _bump_counters(
    *,
    score: ScoreResult,
    direct_year_count: int,
    proxy_year_count: int,
    sources_used: set[str],
) -> tuple[int, int, set[str]]:
    """Increment the direct/proxy counters and ``sources_used`` set."""
    if score.is_proxy and score.source_year is not None:
        proxy_year_count += 1
    elif score.source_year is not None:
        direct_year_count += 1
    if score.skip_reason is None:
        sources_used.add(source_key_for_category(score.category_key))
    return direct_year_count, proxy_year_count, sources_used


def _make_score_row(
    *,
    client_row: ClientSliceRow,
    category_key: str,
    country_label: str,
    target_year: int,
    client_score: int | None,
    rs,
    score: ScoreResult,
    inputs,
) -> ScoreRow:
    delta = (
        rs.system_proposed_score - rs.client_score
        if rs.system_proposed_score is not None and rs.client_score is not None
        else None
    )
    return ScoreRow(
        iso3=client_row.iso3,
        country=country_label,
        leader=client_row.leader_name,
        year=target_year,
        category_key=category_key,
        client_score=client_score,
        system_proposed_score=rs.system_proposed_score,
        final_score=rs.final_score,
        score_delta_vs_client=delta,
        confidence_score=rs.confidence_score,
        source_variable=inputs.variable_name,
        source_year=score.source_year,
        source_raw_value=score.raw_value_str,
        review_status=rs.review_status or "",
        rationale_short=rs.rationale_short or "",
    )


def _make_comparison_row(
    *,
    client_row: ClientSliceRow,
    category_key: str,
    country_label: str,
    target_year: int,
    client_score: int | None,
    rs,  # may be None when the row was skipped (no source observation)
    score: ScoreResult,
) -> ComparisonRow:
    system_score = rs.system_proposed_score if rs is not None else None
    confidence = rs.confidence_score if rs is not None else None
    rationale = rs.rationale_short if rs is not None else ""
    delta = (
        system_score - client_score
        if system_score is not None and client_score is not None
        else None
    )
    return ComparisonRow(
        iso3=client_row.iso3,
        country=country_label,
        year=target_year,
        category_key=category_key,
        client_score=client_score,
        system_proposed_score=system_score,
        score_delta_vs_client=delta,
        confidence_score=confidence,
        validation_status=validation_status_for(
            client_score=client_score,
            system_score=system_score,
            confidence=confidence,
        ),
        missing_reason=score.skip_reason or "",
        manual_review_required=requires_human_review(
            client_score=client_score,
            system_score=system_score,
            confidence=confidence,
            is_proxy=score.is_proxy,
        ),
        rationale_short=rationale,
    )


def _locate_client_xlsx() -> Path:
    """Return the first xlsx file under ``data/raw/client_existing/``.

    The slice does not depend on the exact filename documented in the
    architecture brief; it accepts any xlsx in the conventional folder
    so tests can stage their own fixture.
    """
    folder = raw_dir("client_existing")
    if not folder.exists():
        raise FileNotFoundError(
            f"client xlsx folder not found: {folder}. "
            "Run `leaders-db init-data-lake` and place the client xlsx there."
        )
    candidates = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".xlsx"
    )
    if not candidates:
        raise FileNotFoundError(
            f"no xlsx files found under {folder}. The slice requires the "
            "client matrix xlsx at this conventional location."
        )
    return candidates[0]


def _maybe_run_adapters(*, target_year: int, db_url: str) -> None:
    """Optionally run UNDP HDI Stage 2 (and WGI if available).

    WGI is only run when its xlsx is locally available; otherwise the
    slice gracefully marks integrity rows as missing (architecture §8
    "If WGI Control of Corruption is not present, skip integrity rows
    rather than inventing a score").
    """
    try:
        undp_hdi.ingest_undp_hdi(year=target_year)
    except FileNotFoundError as exc:
        _logger.info(
            "[vertical_slice_2023] UNDP HDI adapter skipped: %s", exc,
        )
    except Exception:
        _logger.exception(
            "[vertical_slice_2023] UNDP HDI adapter raised; slice continues."
        )

    wgi_raw = raw_dir("world_bank_wgi")
    wgi_xlsx = wgi_raw / "wgidataset.xlsx"
    if wgi_xlsx.is_file():
        try:
            wgi.ingest_wgi(year=target_year)
        except Exception:
            _logger.exception(
                "[vertical_slice_2023] WGI adapter raised; slice continues."
            )
    else:
        _logger.info(
            "[vertical_slice_2023] WGI xlsx not present locally (%s); "
            "integrity rows will be marked missing if no observation exists.",
            wgi_xlsx,
        )


# Re-export for downstream callers that want the Sentinel value.
__all__ = [
    "SKIP_NO_OBSERVATION",
    "ClientSliceRow",
    "VerticalSliceResult",
    "load_vertical_slice_client_rows",
    "run_vertical_slice_2023",
]
