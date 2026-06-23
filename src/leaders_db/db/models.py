"""SQLAlchemy 2.x ORM models for the 11 prototype tables.

The schema is normative; see ``docs/architecture/database-schema.md`` and the canonical
DDL at ``migrations/0001_initial.sql``. These models are the application-
side mirror — column names, types, nullability, and uniqueness constraints
must stay aligned with the DDL.

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
    "Country",
    "CountryYear",
    "Leader",
    "LeaderAlias",
    "RulerScore",
    "RulerSpell",
    "RulerYear",
    "ScoreCategory",
    "Source",
    "SourceObservation",
    "ValidationResult",
]
