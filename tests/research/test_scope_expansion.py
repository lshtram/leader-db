from leaders_db.research.models import DimensionFilter, ResearchQuestion, ScopeFilter
from leaders_db.research.planner import expand_scope_filter, plan_question


def test_multi_country_year_range_expands_to_concrete_row_scopes() -> None:
    scope = ScopeFilter(
        filters=(
            DimensionFilter(key="country", values=("USA", "CHN"), role="entity"),
            DimensionFilter(key="year", start=2020, end=2021, role="time"),
        )
    )

    row_scopes = expand_scope_filter(scope)

    assert len(row_scopes) == 4
    assert [
        (row_scope.value_for("country"), row_scope.value_for("year"))
        for row_scope in row_scopes
    ] == [("USA", 2020), ("USA", 2021), ("CHN", 2020), ("CHN", 2021)]


def test_planner_maps_recognized_scope_filters_to_evidence_query() -> None:
    question = ResearchQuestion(
        question_id="conflict-usa-chn-2020-2021",
        question_key="conflict_fatalities_structured",
        display_text="Get conflict fatalities for selected countries.",
        concepts=("conflict_fatalities",),
        scope_filter=ScopeFilter(
            filters=(
                DimensionFilter(key="country", values=("USA", "CHN"), role="entity"),
                DimensionFilter(key="year", start=2020, end=2021, role="time"),
                DimensionFilter(key="topic", values=("ignored-by-evidence-query",)),
            )
        ),
        analyses=("coverage",),
        preferred_sources=("ucdp",),
    )

    plan = plan_question(question)

    assert plan.evidence_query.indicator_codes == ("conflict_fatalities",)
    assert plan.evidence_query.observation_families == ("conflict",)
    assert [source_id.slug for source_id in plan.evidence_query.source_ids or ()] == ["ucdp"]
    assert plan.evidence_query.countries == ("USA", "CHN")
    assert plan.evidence_query.years == (2020, 2021)
    assert plan.evidence_query.leaders is None


def test_planner_rejects_missing_required_scope_key() -> None:
    question = ResearchQuestion(
        question_id="conflict-without-year",
        question_key="conflict_fatalities_structured",
        display_text="Get conflict fatalities for selected countries.",
        concepts=("conflict_fatalities",),
        scope_filter=ScopeFilter(
            filters=(DimensionFilter(key="country", values=("USA",), role="entity"),)
        ),
        analyses=("coverage",),
    )

    try:
        plan_question(question)
    except ValueError as exc:
        assert "Missing required scope key" in str(exc)
    else:  # pragma: no cover - assertion path
        raise AssertionError("Expected missing scope key rejection")
