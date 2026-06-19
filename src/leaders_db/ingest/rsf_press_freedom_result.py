"""Stage 2 -- RSF World Press Freedom Index ingest result model."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .rsf_press_freedom_io import RSF_PRESS_FREEDOM_ATTRIBUTION


class RsfPressFreedomIngestResult(BaseModel):
    """Summary of a single ``ingest_rsf_press_freedom`` run.

    Pydantic ``BaseModel`` (not a dataclass) because the result
    crosses a CLI boundary: :func:`leaders_db.cli.ingest_source`
    reads the core fields to print the end-of-run summary, and the
    manifest writer in :mod:`rsf_press_freedom_db` consumes the
    same fields. Same shape as V-Dem's
    :class:`vdem.IngestResult`, WGI's :class:`wgi.WGIIngestResult`,
    UCDP's :class:`ucdp.UCDPIngestResult`, SIPRI milex's
    :class:`sipri_milex.SipriMilexIngestResult`, SIPRI Yearbook
    Ch.7's :class:`sipri_yearbook_ch7.SipriYearbookCh7IngestResult`,
    PTS's :class:`pts.PtsIngestResult`, and UNDP HDI's
    :class:`undp_hdi.UndpHdiIngestResult`.

    Fields (10 total):

    - ``source_id``, ``parquet_path``, ``observation_rows``,
      ``countries``, ``years``, ``indicators``, ``year_window`` --
      shared with the V-Dem / WGI / UCDP / SIPRI milex / SIPRI
      Yearbook Ch.7 / PTS / UNDP HDI shape.
    - ``pre_2022_country_count`` and ``post_2022_country_count`` --
      RSF-specific: the per-schema split of country rows. The
      2022 schema break separates the 2002-2021 files (16-col
      wide format, score + rank only) from the 2022+ files (22-26
      col wide format with 5 component-context columns). The two
      counts help the audit trail confirm that the pre/post-2022
      coverage is what the metadata.json expects.
    """

    source_id: int = Field(
        ..., ge=1,
        description="The ``sources.id`` row created/updated.",
    )
    parquet_path: Path = Field(
        ..., description="Path to the narrow RSF parquet.",
    )
    observation_rows: int = Field(
        ...,
        ge=0,
        description=(
            "Number of ``source_observations`` rows written by this run."
        ),
    )
    countries: int = Field(
        ...,
        ge=0,
        description=(
            "Distinct ``iso3``s in the narrow frame."
        ),
    )
    years: tuple[int, ...] = Field(
        ..., description="Years included in the run, sorted.",
    )
    indicators: int = Field(
        ..., ge=0,
        description="Number of catalog indicators used.",
    )
    pre_2022_country_count: int = Field(
        ...,
        ge=0,
        description=(
            "Number of distinct ISO3s read from pre-2022 files "
            "(2002-2021). Pre-2022 files do not carry the 5 "
            "component-context columns."
        ),
    )
    post_2022_country_count: int = Field(
        ...,
        ge=0,
        description=(
            "Number of distinct ISO3s read from post-2022 files "
            "(2022+). Post-2022 files carry the 5 component-context "
            "columns."
        ),
    )
    year_window: tuple[int, int] = Field(
        ...,
        description=(
            "(start_year, end_year) tuple representing the min/max "
            "year in the narrow frame."
        ),
    )

    @field_validator("years")
    @classmethod
    def _years_are_sorted_unique_ints(
        cls, value: tuple[int, ...],
    ) -> tuple[int, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError(
                "years must be a sorted tuple of unique ints"
            )
        for one_year in value:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got "
                    f"{type(one_year).__name__}"
                )
        return value

    @field_validator("year_window")
    @classmethod
    def _year_window_is_ordered_pair(
        cls, value: tuple[int, int],
    ) -> tuple[int, int]:
        if len(value) != 2:
            raise ValueError("year_window must be a 2-tuple")
        if value[0] > value[1]:
            raise ValueError(
                "year_window must have start <= end"
            )
        return value

    @property
    def attribution(self) -> str:
        """The RSF attribution text (Always-On Rule #15)."""
        return RSF_PRESS_FREEDOM_ATTRIBUTION


__all__ = ["RsfPressFreedomIngestResult"]
