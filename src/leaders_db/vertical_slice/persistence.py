"""DB row writers and helpers for the 2023 vertical slice.

Implements architecture doc §7 (client-only leader / ruler spell /
ruler-year seeding) and §8 (ruler_scores + validation_results
persistence). Extracted from :mod:`slice_2023` so the orchestrator
stays focused on control flow and stays under the documented line cap.

Every helper here is internal to the vertical-slice package. The
public surface lives in :mod:`slice_2023`.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db.models import (
    Country,
    Leader,
    RulerScore,
    RulerSpell,
    RulerYear,
    ScoreCategory,
    ValidationResult,
)
from ..normalize.leader_names import normalize_leader_name
from ..score.confidence import ConfidenceInputs, compute_confidence
from .constants import (
    SLICE_NOTE_PREFIX,
    SLICE_RULER_SPELLS_DATASET,
    SLICE_SEED_CONFIDENCE,
    placeholder_date_for,
)
from .parser import ClientSliceRow
from .scoring import ScoreResult

# Sentinel used when a slice-owned row has no observation to score
# (the slice never invents scores, per architecture §8).
SKIP_NO_OBSERVATION: str = "skipped_no_observation"


def delete_slice_owned_rows(
    session: Session,
    *,
    iso3_scope: Sequence[str],
    target_year: int,
) -> None:
    """Delete only slice-owned rows for the scoped countries/year.

    Selection is constrained by the slice marker in addition to the
    country/year/match-status triple so a non-slice ``client_only`` row
    (e.g. one produced by an earlier real Stage 4 run for the same
    ISO3/year) is preserved. Preserves reusable ``countries``,
    ``country_years``, ``leaders``, ``score_categories``, and Stage 2
    ``source_observations`` rows.
    """
    country_id_subq = select(Country.id).where(Country.iso3.in_(iso3_scope))
    slice_ruler_year_ids = list(
        session.execute(
            select(RulerYear.id).where(
                RulerYear.country_id.in_(country_id_subq),
                RulerYear.year == target_year,
                RulerYear.match_status == "client_only",
                RulerYear.review_note.like(f"{SLICE_NOTE_PREFIX}%"),
            )
        ).scalars()
    )

    if slice_ruler_year_ids:
        # Delete validation_results -> ruler_scores -> ruler_years -> ruler_spells.
        ruler_score_ids = list(
            session.execute(
                select(RulerScore.id).where(
                    RulerScore.ruler_year_id.in_(slice_ruler_year_ids)
                )
            ).scalars()
        )
        if ruler_score_ids:
            session.execute(
                delete(ValidationResult).where(
                    ValidationResult.item_type == "ruler_score",
                    ValidationResult.item_id.in_(ruler_score_ids),
                )
            )
        session.execute(
            delete(RulerScore).where(
                RulerScore.ruler_year_id.in_(slice_ruler_year_ids)
            )
        )
        spell_ids = list(
            session.execute(
                select(RulerSpell.id).where(
                    RulerSpell.country_id.in_(country_id_subq),
                    RulerSpell.source_dataset == SLICE_RULER_SPELLS_DATASET,
                )
            ).scalars()
        )
        session.execute(
            delete(RulerYear).where(RulerYear.id.in_(slice_ruler_year_ids))
        )
        if spell_ids:
            session.execute(
                delete(RulerSpell).where(RulerSpell.id.in_(spell_ids))
            )
    else:
        # No ruler_years yet, but slice-owned spells from a prior partial
        # run may still exist.
        spell_ids = list(
            session.execute(
                select(RulerSpell.id).where(
                    RulerSpell.country_id.in_(country_id_subq),
                    RulerSpell.source_dataset == SLICE_RULER_SPELLS_DATASET,
                )
            ).scalars()
        )
        if spell_ids:
            session.execute(delete(RulerSpell).where(RulerSpell.id.in_(spell_ids)))


def upsert_score_categories(
    session: Session, category_keys: Sequence[str]
) -> dict[str, int]:
    """Return ``{category_key: score_categories.id}`` for every scoped key."""
    out: dict[str, int] = {}
    for key in category_keys:
        existing = session.execute(
            select(ScoreCategory).where(ScoreCategory.category_key == key)
        ).scalar_one_or_none()
        if existing is not None:
            out[key] = existing.id
            continue
        row = ScoreCategory(
            category_key=key, category_name=key.replace("_", " ").title()
        )
        session.add(row)
        session.flush()
        out[key] = row.id
    return out


def upsert_leader(session: Session, client_row: ClientSliceRow) -> int:
    """Return the ``leaders.id`` for the normalized client leader name."""
    normalized = normalize_leader_name(client_row.leader_name)
    existing = session.execute(
        select(Leader).where(Leader.normalized_name == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    row = Leader(
        full_name=client_row.leader_name,
        normalized_name=normalized,
        notes=f"{SLICE_NOTE_PREFIX}seeded_from_client_matrix",
    )
    session.add(row)
    session.flush()
    return row.id


def insert_ruler_spell(
    session: Session,
    *,
    leader_id: int,
    country_id: int,
    client_row: ClientSliceRow,
    target_year: int,
) -> int:
    """Insert a slice-owned :class:`RulerSpell` row for the leader/country."""
    start_date = placeholder_date_for(client_row.year_started_raw, target_year)
    note_parts = [f"{SLICE_NOTE_PREFIX}client_only_seeded"]
    if client_row.year_started_raw is None:
        note_parts.append("year_started_missing_in_client_matrix")
    row = RulerSpell(
        leader_id=leader_id,
        country_id=country_id,
        start_date=start_date,
        end_date=None,
        source_dataset=SLICE_RULER_SPELLS_DATASET,
        # Architecture §7: is_formal_leader=True only when office information
        # is available. The slice has no office source, so we set the
        # conservative/default value (False) and surface the seeding note
        # in ``notes`` for audit.
        is_actual_ruler=True,
        is_formal_leader=False,
        confidence_score=SLICE_SEED_CONFIDENCE,
        notes="; ".join(note_parts),
    )
    session.add(row)
    session.flush()
    return row.id


def insert_ruler_year(
    session: Session,
    *,
    leader_id: int,
    country_id: int,
    spell_id: int,
    client_row: ClientSliceRow,
    target_year: int,
) -> int:
    """Insert a slice-owned :class:`RulerYear` row for the (leader, country, year)."""
    review_note = (
        f"{SLICE_NOTE_PREFIX}real Stage 4 leader resolver not invoked; "
        "this row is seeded from the client matrix only."
    )
    row = RulerYear(
        leader_id=leader_id,
        country_id=country_id,
        year=target_year,
        ruler_spell_id=spell_id,
        actual_ruler_status="actual_ruler",
        client_matrix_leader_name=client_row.leader_name,
        system_selected_leader_name=client_row.leader_name,
        match_status="client_only",
        confidence_score=SLICE_SEED_CONFIDENCE,
        review_status="manual_review_required",
        review_note=review_note,
    )
    session.add(row)
    session.flush()
    return row.id


def write_ruler_score(
    session: Session,
    *,
    ruler_year_id: int,
    category_id: int,
    client_score: int | None,
    score: ScoreResult,
) -> RulerScore:
    """Insert the :class:`RulerScore` row and return the persisted object."""
    confidence = _confidence_or_none(score)
    review_required = _requires_human_review(
        client_score=client_score,
        system_score=score.system_proposed_score,
        confidence=confidence,
        is_proxy=score.is_proxy,
    )
    rationale = _score_rationale(score)

    row = RulerScore(
        ruler_year_id=ruler_year_id,
        category_id=category_id,
        client_score=client_score,
        system_proposed_score=score.system_proposed_score,
        final_score=None,
        score_delta_vs_client=_score_delta(client_score, score.system_proposed_score),
        confidence_score=confidence,
        source_agreement="medium" if score.skip_reason is None else None,
        human_review_required=review_required,
        rationale_short=rationale,
        review_status=(
            "manual_review_required" if review_required else "auto_accepted_slice"
        ),
    )
    session.add(row)
    session.flush()
    return row


def write_validation_row(
    session: Session,
    *,
    ruler_score_id: int,
    score: ScoreResult,
    client_score: int | None,
    source_year: int | None,
    target_year: int,
) -> ValidationResult:
    """Persist a :class:`ValidationResult` row for one ``ruler_scores`` row."""
    confidence = _confidence_or_zero(score)
    validation_status = _validation_status_for(
        client_score=client_score,
        system_score=score.system_proposed_score,
        confidence=confidence,
    )
    note = _validation_note(score, source_year, target_year)

    row = ValidationResult(
        item_type="ruler_score",
        item_id=ruler_score_id,
        validation_status=validation_status,
        source_count=1 if score.skip_reason is None else 0,
        source_agreement_score=score.confidence_agreement,
        source_authority_score=score.confidence_authority,
        temporal_fit_score=score.confidence_temporal_fit,
        specificity_score=score.confidence_specificity,
        final_confidence_score=confidence,
        validation_note=note,
    )
    session.add(row)
    session.flush()
    return row


def validation_status_for(
    *,
    client_score: int | None,
    system_score: int | None,
    confidence: int | None,
) -> str:
    """Map (client_score, system_score, confidence) to a validation status."""
    if client_score is None or system_score is None:
        return SKIP_NO_OBSERVATION
    delta = abs(system_score - client_score)
    if delta <= 1:
        return "match"
    if delta > 2:
        return "high_delta"
    return "conflict"


def requires_human_review(
    *,
    client_score: int | None,
    system_score: int | None,
    confidence: int | None,
    is_proxy: bool,
) -> bool:
    """Return ``True`` when the slice marks the row for manual review."""
    if system_score is None or client_score is None:
        return True
    if abs(system_score - client_score) > 2:
        return True
    if confidence is not None and confidence < 60:
        return True
    return is_proxy


def source_key_for_category(category_key: str) -> str:
    """Return the source key (data lake folder / CLI flag) for a category."""
    if category_key == "social_wellbeing":
        return "undp_hdi"
    if category_key == "integrity":
        return "world_bank_wgi"
    return category_key


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _confidence_or_none(score: ScoreResult) -> int | None:
    if score.skip_reason is not None:
        return None
    return compute_confidence(
        ConfidenceInputs(
            agreement=score.confidence_agreement,
            authority=score.confidence_authority,
            specificity=score.confidence_specificity,
            temporal_fit=score.confidence_temporal_fit,
        )
    )


def _confidence_or_zero(score: ScoreResult) -> int:
    if score.skip_reason is not None:
        return 0
    return compute_confidence(
        ConfidenceInputs(
            agreement=score.confidence_agreement,
            authority=score.confidence_authority,
            specificity=score.confidence_specificity,
            temporal_fit=score.confidence_temporal_fit,
        )
    )


def _score_delta(
    client_score: int | None, system_score: int | None
) -> int | None:
    if client_score is None or system_score is None:
        return None
    return system_score - client_score


def _score_rationale(score: ScoreResult) -> str:
    parts = [f"{SLICE_NOTE_PREFIX}category={score.category_key}"]
    if score.source_year is not None:
        suffix = "(proxy)" if score.is_proxy else ""
        parts.append(f"source_year={score.source_year}{suffix}")
    if score.skip_reason is not None:
        parts.append(f"skip_reason={score.skip_reason}")
    return "; ".join(parts)


def _validation_note(
    score: ScoreResult, source_year: int | None, target_year: int
) -> str:
    parts = [f"{SLICE_NOTE_PREFIX}category={score.category_key}"]
    if source_year is not None and source_year != target_year:
        parts.append(f"proxy_year={source_year}")
    if score.skip_reason is not None:
        parts.append(f"skip_reason={score.skip_reason}")
    return "; ".join(parts)


def _validation_status_for(
    *,
    client_score: int | None,
    system_score: int | None,
    confidence: int | None,
) -> str:
    return validation_status_for(
        client_score=client_score,
        system_score=system_score,
        confidence=confidence,
    )


def _requires_human_review(
    *,
    client_score: int | None,
    system_score: int | None,
    confidence: int | None,
    is_proxy: bool,
) -> bool:
    return requires_human_review(
        client_score=client_score,
        system_score=system_score,
        confidence=confidence,
        is_proxy=is_proxy,
    )


__all__ = [
    "SKIP_NO_OBSERVATION",
    "delete_slice_owned_rows",
    "insert_ruler_spell",
    "insert_ruler_year",
    "requires_human_review",
    "source_key_for_category",
    "upsert_leader",
    "upsert_score_categories",
    "validation_status_for",
    "write_ruler_score",
    "write_validation_row",
]
