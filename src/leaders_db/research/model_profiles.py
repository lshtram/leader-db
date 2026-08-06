"""Versioned provider/model profiles for research execution roles."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

ResearchRole = Literal[
    "dossier_researcher",
    "dossier_evidence_reviewer",
    "dossier_formatter",
    "document_reader",
    "chapter_judge",
]


class ResearchModelProfile(BaseModel):
    """One configured provider/model candidate for a research role."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    execution_surface: str = Field(min_length=1)
    roles: tuple[ResearchRole, ...]
    cost_class: str = Field(min_length=1)
    context_window: int | None = Field(default=None, gt=0)
    codex_config_path: str = Field(min_length=1)
    credential_path: str = Field(min_length=1)
    disabled_features: tuple[str, ...] = ()
    notes: str = Field(min_length=1)


class ResearchModelProfiles(BaseModel):
    """Versioned research provider/model profile registry."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    profiles: dict[str, ResearchModelProfile]


def load_research_model_profiles(path: Path) -> ResearchModelProfiles:
    """Load and validate a model profile registry without reading credentials."""

    try:
        payload = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid research model profile YAML: {path}") from exc
    return ResearchModelProfiles.model_validate(payload)


__all__ = [
    "ResearchModelProfile",
    "ResearchModelProfiles",
    "ResearchRole",
    "load_research_model_profiles",
]
