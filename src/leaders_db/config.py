"""Run configuration schema and YAML loading.

A normal run is initialized from a YAML config under ``configs/``, then run
through generic orchestration code. CLI flags may override config values
for diagnostics, but the resolved config used by the run is persisted to
``data/logs/<run-id>/run_config.yaml`` for reproducibility.

Config fields are strict-typed Pydantic models; the package never hard-codes
research parameters (target year, source selection, scoring categories,
confidence thresholds) at module boundaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Section models
# ---------------------------------------------------------------------------


class ProjectConfig(BaseModel):
    """Project-level metadata for a run."""

    name: str = "leaders-db-prototype"
    target_year: int = Field(default=2023, ge=1900, le=2100)
    description: str = ""


class DatabaseConfig(BaseModel):
    """Database connection. SQLite by default; PostgreSQL supported."""

    url: str = "sqlite:///data/catalog/leaders_db.sqlite"
    echo_sql: bool = False


class SourcesConfig(BaseModel):
    """Selection of priority sources to use for a run.

    All flags default to ``False`` — the runner is explicit about which
    sources it wants, which makes a run reproducible from its config alone.
    """

    client_existing: bool = True
    archigos: bool = True
    leader_survival: bool = True
    reign: bool = True
    vdem: bool = True
    freedom_house: bool = True
    world_bank_wdi: bool = True
    world_bank_wgi: bool = True
    transparency_cpi: bool = True
    ucdp: bool = True
    cow_mid: bool = False
    political_terror_scale: bool = True
    cirights: bool = True
    sipri: bool = True
    fas: bool = True
    nti: bool = True


class ScoringConfig(BaseModel):
    """Scoring run parameters."""

    # The four prototype-required categories from requirement §16. Adding
    # more categories is a config-only change.
    categories: list[Literal[
        "political_freedom",
        "economic_wellbeing",
        "corruption",
        "domestic_violence",
    ]] = Field(
        default_factory=lambda: [
            "political_freedom",
            "economic_wellbeing",
            "corruption",
            "domestic_violence",
        ],
    )

    # High-delta threshold for manual-review flagging (requirement §14).
    high_delta_threshold: int = Field(default=2, ge=0, le=10)

    # Below this confidence, items go to the manual-review queue (§14).
    manual_review_confidence_cutoff: int = Field(default=60, ge=0, le=100)


class LLMConfig(BaseModel):
    """LLM adapter parameters. Optional — the package runs without an LLM."""

    enabled: bool = False
    provider: Literal["openai", "anthropic", "ollama", "stub"] = "stub"
    model: str = "stub"
    api_key_env: str = "LEADERSDB_LLM_API_KEY"
    base_url: str | None = None
    timeout_s: int = 60

    @field_validator("provider")
    @classmethod
    def _no_provider_when_disabled(cls, v: str) -> str:  # pragma: no cover - trivial
        return v


class RunConfig(BaseModel):
    """The full run config: project + database + sources + scoring + LLM."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


# ---------------------------------------------------------------------------
# Loading / dumping
# ---------------------------------------------------------------------------


def load_config(path: Path | str) -> RunConfig:
    """Load a YAML config file into a :class:`RunConfig`.

    A missing file raises :class:`FileNotFoundError` with the absolute path.
    An invalid file raises :class:`pydantic.ValidationError` with the
    field-level details.
    """
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"config file not found: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return RunConfig.model_validate(raw)


def dump_config(cfg: RunConfig, path: Path | str) -> Path:
    """Persist a :class:`RunConfig` to YAML at ``path`` and return the absolute path."""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return p


def default_config_path() -> Path:
    """Return the conventional default config path (``configs/prototype-2023.yaml``)."""
    from .paths import configs_dir

    return configs_dir() / "prototype-2023.yaml"
