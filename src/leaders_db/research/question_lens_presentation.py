"""Layered, versioned presentation of ruler-quality research lenses."""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from leaders_db.conversational_evidence.data import load, questions


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LensPresentation(_StrictModel):
    """Compact orientation layered over one stable detailed question."""

    id: str
    title: str
    simple_question: str
    priority_categories: tuple[str, ...]

    @field_validator("priority_categories")
    @classmethod
    def require_distinct_categories(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("priority_categories must be non-empty and distinct")
        return value


class EvidenceCategory(_StrictModel):
    """Configured evidence category and non-exclusive source orientation."""

    name: str
    description: str
    typical_sources: tuple[str, ...]


class QuestionLensPresentation(_StrictModel):
    """Validated presentation catalogue loaded from the versioned JSON artifact."""

    version: str
    max_priority_categories: int
    evidence_categories: dict[str, EvidenceCategory]
    lenses: tuple[LensPresentation, ...]

    @model_validator(mode="after")
    def validate_catalogue(self) -> QuestionLensPresentation:
        if len(self.lenses) != len({item.id for item in self.lenses}):
            raise ValueError("lens presentation IDs must be unique")
        if self.max_priority_categories < 1:
            raise ValueError("max_priority_categories must be positive")
        if any(
            len(item.priority_categories) > self.max_priority_categories
            for item in self.lenses
        ):
            raise ValueError("lens priority category count exceeds configured maximum")
        unknown_categories = {
            category
            for lens in self.lenses
            for category in lens.priority_categories
            if category not in self.evidence_categories
        }
        if unknown_categories:
            raise ValueError(
                f"unknown priority evidence categories: {sorted(unknown_categories)}"
            )
        return self


@lru_cache(maxsize=1)
def load_question_lens_presentation() -> QuestionLensPresentation:
    """Load and cross-validate the layered lens catalogue."""

    presentation = QuestionLensPresentation.model_validate(
        load("question_lens_presentation.json")
    )
    expected_ids = {item["id"] for item in questions()}
    lens_ids = {item.id for item in presentation.lenses}
    if lens_ids != expected_ids:
        raise ValueError("lens presentation IDs must match the detailed question catalogue")
    return presentation


def render_lens_table(methodology_ids: list[str]) -> str:
    """Render selected lenses from simple orientation to detailed wording."""

    presentation = load_question_lens_presentation()
    lens_by_id = {item.id: item for item in presentation.lenses}
    detailed_by_id = {item["id"]: item["text"] for item in questions()}
    rows = [
        "| Lens | Simple question | Detailed research question | Priority evidence |",
        "|---|---|---|---|",
    ]
    for methodology_id in methodology_ids:
        lens = lens_by_id[methodology_id]
        category_names = [
            presentation.evidence_categories[key].name
            for key in lens.priority_categories
        ]
        rows.append(
            "| "
            f"**{methodology_id} — {_escape_cell(lens.title)}** | "
            f"{_escape_cell(lens.simple_question)} | "
            f"{_escape_cell(detailed_by_id[methodology_id])} | "
            f"{'; '.join(f'**{_escape_cell(name)}**' for name in category_names)} |"
        )
    return "\n".join(rows)


def render_evidence_category_key() -> str:
    """Render the compact global category key used ahead of lens tables."""

    categories = load_question_lens_presentation().evidence_categories
    return "\n".join(
        f"- **{category.name}:** {category.description} "
        f"Typical sources: {', '.join(category.typical_sources)}."
        for category in categories.values()
    )


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
