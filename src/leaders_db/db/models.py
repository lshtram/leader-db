"""SQLAlchemy 2.x ORM models for the migration-backed prototype schema.

The schema is normative; see ``docs/architecture/database-schema.md`` and the
canonical ordered DDL under ``migrations/``. These models are the application-side
mirror — column names, types, nullability, and uniqueness constraints must stay
aligned with the migrations.

Conventions:

- Primary keys are surrogate ``Integer`` columns named ``id``.
- Foreign keys are explicit and named ``<table>_id``.
- Enum-like string columns carry their valid values in the docstring; the
  package enforces them at validation boundaries, not at the DB layer
  (SQLite has no native enums and we want the same models on PostgreSQL
  via plain ``VARCHAR`` columns there too).
- Boolean columns use ``Boolean`` and default to ``False`` unless the
  domain clearly defaults to ``True`` (e.g. ``is_actual_ruler`` defaults
  to ``True`` because most ruler spells are actual-ruler spells).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# Reference / dimension tables
# ---------------------------------------------------------------------------


class Country(Base):
    """Master country list. ISO3 is the primary matching key (Stage 3)."""

    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iso3: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)
    country_name: Mapped[str] = mapped_column(String, nullable=False)
    country_name_normalized: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    country_years: Mapped[list[CountryYear]] = relationship(back_populates="country")
    ruler_spells: Mapped[list[RulerSpell]] = relationship(back_populates="country")
    ruler_years: Mapped[list[RulerYear]] = relationship(back_populates="country")
    source_observations: Mapped[list[SourceObservation]] = relationship(
        back_populates="country"
    )


class CountryYear(Base):
    """Per-country-per-year context (population, GDP, inclusion)."""

    __tablename__ = "country_years"
    __table_args__ = (UniqueConstraint("country_id", "year", name="uq_country_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_id: Mapped[int] = mapped_column(
        ForeignKey("countries.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gdp_current_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gdp_per_capita: Mapped[float | None] = mapped_column(Float, nullable=True)
    included_in_project: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    country: Mapped[Country] = relationship(back_populates="country_years")


class Leader(Base):
    """Per-leader identity. Reused across spells and years."""

    __tablename__ = "leaders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    death_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    aliases: Mapped[list[LeaderAlias]] = relationship(back_populates="leader")
    ruler_spells: Mapped[list[RulerSpell]] = relationship(back_populates="leader")
    ruler_years: Mapped[list[RulerYear]] = relationship(back_populates="leader")
    source_observations: Mapped[list[SourceObservation]] = relationship(
        back_populates="leader"
    )


class LeaderAlias(Base):
    """Alternative spellings of a leader, one row per alias-source."""

    __tablename__ = "leader_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("leaders.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)

    leader: Mapped[Leader] = relationship(back_populates="aliases")


class Source(Base):
    """Provenance registry. One row per dataset (or per dataset-version)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    license_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_start_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    coverage_end_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScoreCategory(Base):
    """Canonical scoring categories. Seeded with the ten from §4."""

    __tablename__ = "score_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric_low: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric_mid: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric_high: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Core domain tables
# ---------------------------------------------------------------------------


class RulerSpell(Base):
    """A leader's tenure in a country. Multiple spells per leader are allowed."""

    __tablename__ = "ruler_spells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("leaders.id"), nullable=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    office_title: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_dataset: Mapped[str] = mapped_column(String, nullable=False)
    is_actual_ruler: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_formal_leader: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rule_type: Mapped[str | None] = mapped_column(String, nullable=True)
    shared_rule_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disputed_rule_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    leader: Mapped[Leader] = relationship(back_populates="ruler_spells")
    country: Mapped[Country] = relationship(back_populates="ruler_spells")


class RulerYear(Base):
    """Per-leader-per-country-per-year actual-ruler determination (Stage 4)."""

    __tablename__ = "ruler_years"
    __table_args__ = (
        UniqueConstraint("leader_id", "country_id", "year", name="uq_ruler_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leader_id: Mapped[int] = mapped_column(ForeignKey("leaders.id"), nullable=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ruler_spell_id: Mapped[int | None] = mapped_column(
        ForeignKey("ruler_spells.id"), nullable=True
    )
    actual_ruler_status: Mapped[str | None] = mapped_column(String, nullable=True)
    client_matrix_leader_name: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    system_selected_leader_name: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    match_status: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    leader: Mapped[Leader] = relationship(back_populates="ruler_years")
    country: Mapped[Country] = relationship(back_populates="ruler_years")
    ruler_scores: Mapped[list[RulerScore]] = relationship(back_populates="ruler_year")


class RulerScore(Base):
    """Per-ruler-year per-category score. Carries client + system + final separately."""

    __tablename__ = "ruler_scores"
    __table_args__ = (
        UniqueConstraint("ruler_year_id", "category_id", name="uq_ruler_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ruler_year_id: Mapped[int] = mapped_column(
        ForeignKey("ruler_years.id"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("score_categories.id"), nullable=False
    )
    client_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    system_proposed_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    final_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_delta_vs_client: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source_agreement: Mapped[str | None] = mapped_column(String, nullable=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rationale_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str | None] = mapped_column(String, nullable=True)

    ruler_year: Mapped[RulerYear] = relationship(back_populates="ruler_scores")


class SourceObservation(Base):
    """Raw and normalized observations from each source. The audit backbone."""

    __tablename__ = "source_observations"
    __table_args__ = (
        Index("ix_obs_source_country_year", "source_id", "country_id", "year"),
        Index("ix_obs_variable_year", "variable_name", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    country_id: Mapped[int | None] = mapped_column(
        ForeignKey("countries.id"), nullable=True
    )
    leader_id: Mapped[int | None] = mapped_column(
        ForeignKey("leaders.id"), nullable=True
    )
    year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    variable_name: Mapped[str] = mapped_column(String, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    source_row_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    country: Mapped[Country | None] = relationship(back_populates="source_observations")
    leader: Mapped[Leader | None] = relationship(back_populates="source_observations")


class NormalizedObservationRow(Base):
    """Research-engine normalized evidence row with JSON provenance payloads."""

    __tablename__ = "normalized_observations"
    __table_args__ = (
        UniqueConstraint("source_slug", "observation_id", name="uq_normalized_observation"),
        Index(
            "ix_norm_obs_source_family_indicator",
            "source_slug",
            "observation_family",
            "indicator_code",
        ),
        Index("ix_norm_obs_country_year", "country_code", "year"),
        Index("ix_norm_obs_leader_year", "leader_id", "leader_name", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_slug: Mapped[str] = mapped_column(String, nullable=False)
    observation_id: Mapped[str] = mapped_column(String, nullable=False)
    observation_family: Mapped[str] = mapped_column(String, nullable=False)
    indicator_code: Mapped[str] = mapped_column(String, nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String, nullable=True)
    country_name: Mapped[str | None] = mapped_column(String, nullable=True)
    leader_id: Mapped[str | None] = mapped_column(String, nullable=True)
    leader_name: Mapped[str | None] = mapped_column(String, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    scale: Mapped[str | None] = mapped_column(String, nullable=True)
    source_version: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_locator_json: Mapped[str] = mapped_column(Text, nullable=False)
    transform_locator_json: Mapped[str] = mapped_column(Text, nullable=False)
    quality_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    extension_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    scope_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ResearchQuestion(Base):
    """Persisted question metadata for dashboard/result rows."""

    __tablename__ = "research_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    chapter_id: Mapped[str] = mapped_column(String, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str] = mapped_column(String, nullable=False)
    category_key: Mapped[str | None] = mapped_column(String, nullable=True)
    method_version: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    answers: Mapped[list[ResearchQuestionAnswer]] = relationship(
        back_populates="question"
    )


class ResearchQuestionAnswer(Base):
    """One dashboard-ready answer per question/country/year/method slice."""

    __tablename__ = "research_question_answers"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            "year",
            "iso3",
            "method_version",
            name="uq_research_question_answer_slice",
        ),
        Index("ix_research_answers_question_year", "question_id", "year"),
        Index("ix_research_answers_iso3_year", "iso3", "year"),
        Index("ix_research_answers_ruler_name_year", "ruler_name", "year"),
        Index("ix_research_answers_coverage_year", "coverage_status", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("research_questions.question_id"), nullable=False
    )
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    country_name: Mapped[str] = mapped_column(String, nullable=False)
    ruler_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ruler_name: Mapped[str | None] = mapped_column(String, nullable=True)
    answer_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answer_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    score_1_to_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_status: Mapped[str] = mapped_column(String, nullable=False)
    evidence_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    method_version: Mapped[str] = mapped_column(String, nullable=False)
    warning_codes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    caveats_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    question: Mapped[ResearchQuestion] = relationship(back_populates="answers")
    evidence_links: Mapped[list[ResearchAnswerEvidenceLink]] = relationship(
        back_populates="answer", cascade="all, delete-orphan"
    )


class ResearchAnswerEvidenceLink(Base):
    """Drill-down link from a persisted answer to source evidence."""

    __tablename__ = "research_answer_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "answer_id",
            "source_slug",
            "source_observation_id",
            "evidence_role",
            name="uq_research_answer_evidence_link",
        ),
        Index(
            "ix_research_evidence_source_observation",
            "source_slug",
            "source_observation_id",
        ),
        Index("ix_research_evidence_answer_id", "answer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    answer_id: Mapped[int] = mapped_column(
        ForeignKey("research_question_answers.id", ondelete="CASCADE"), nullable=False
    )
    source_slug: Mapped[str] = mapped_column(String, nullable=False)
    source_observation_id: Mapped[str] = mapped_column(String, nullable=False)
    evidence_role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    answer: Mapped[ResearchQuestionAnswer] = relationship(back_populates="evidence_links")


class ChapterScore(Base):
    """Future aggregate chapter score per ruler-country-year slice."""

    __tablename__ = "chapter_scores"
    __table_args__ = (
        UniqueConstraint(
            "chapter_id",
            "year",
            "iso3",
            "method_version",
            name="uq_chapter_score_slice",
        ),
        Index("ix_chapter_scores_chapter_year", "chapter_id", "year"),
        Index("ix_chapter_scores_iso3_year", "iso3", "year"),
        Index("ix_chapter_scores_ruler_name_year", "ruler_name", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    iso3: Mapped[str] = mapped_column(String(3), nullable=False)
    ruler_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ruler_name: Mapped[str | None] = mapped_column(String, nullable=True)
    score_1_to_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    method_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class ValidationResult(Base):
    """Per-item validation record. Stage 12 output."""

    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_type: Mapped[str] = mapped_column(String, nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_status: Mapped[str | None] = mapped_column(String, nullable=True)
    source_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source_agreement_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source_authority_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    temporal_fit_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    specificity_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    final_confidence_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    validation_note: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = [
    "Base",
    "ChapterScore",
    "Country",
    "CountryYear",
    "Leader",
    "LeaderAlias",
    "NormalizedObservationRow",
    "ResearchAnswerEvidenceLink",
    "ResearchQuestion",
    "ResearchQuestionAnswer",
    "RulerScore",
    "RulerSpell",
    "RulerYear",
    "ScoreCategory",
    "Source",
    "SourceObservation",
    "ValidationResult",
]
