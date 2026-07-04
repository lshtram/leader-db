"""Curated question and concept registries for the research planner."""

# ruff: noqa: E501 - registry text mirrors long methodology questions verbatim.

from __future__ import annotations

from .models import ConceptSpec, QuestionSpec

CONCEPT_SPECS: dict[str, ConceptSpec] = {
    "ucdp_state_based_conflict": ConceptSpec(
        concept_key="ucdp_state_based_conflict",
        expected_scope_keys=("country", "year"),
        evidence_shape="structured_numeric",
        observation_families=("international_peace_country_year",),
        required_output_schema="Question21AnswerRow",
        allowed_source_types=("structured_dataset",),
        acquisition_allowed=False,
    ),
    "conflict_fatalities": ConceptSpec(
        concept_key="conflict_fatalities",
        expected_scope_keys=("country", "year"),
        evidence_shape="structured_numeric",
        observation_families=("conflict",),
        required_output_schema="NormalizedObservation",
        allowed_source_types=("structured_dataset",),
        acquisition_allowed=False,
    ),
    "leader_open_criminal_or_corruption_case": ConceptSpec(
        concept_key="leader_open_criminal_or_corruption_case",
        expected_scope_keys=("country", "leader", "year"),
        evidence_shape="qualitative_cited",
        observation_families=("leader_legal_case",),
        required_output_schema="AcquiredEvidenceRecord",
        allowed_source_types=("official_record", "reputable_news"),
        acquisition_allowed=True,
    ),
    "ruler_effectiveness_qualitative_evidence": ConceptSpec(
        concept_key="ruler_effectiveness_qualitative_evidence",
        expected_scope_keys=("country", "leader", "period"),
        evidence_shape="qualitative_cited",
        observation_families=("ruler_period_effectiveness",),
        required_output_schema="RulerEffectivenessEvidenceRecord",
        allowed_source_types=("official_record", "reputable_news", "scholarly_source"),
        acquisition_allowed=True,
    ),
    "ruler_quality_qualitative_evidence": ConceptSpec(
        concept_key="ruler_quality_qualitative_evidence",
        expected_scope_keys=("country", "leader", "period"),
        evidence_shape="qualitative_cited",
        observation_families=("ruler_period_quality",),
        required_output_schema="AcquiredEvidenceRecord",
        allowed_source_types=("official_record", "reputable_news", "scholarly_source"),
        acquisition_allowed=True,
    ),
}


RULER_QUALITY_CATEGORY_SPECS: dict[str, tuple[str, str, str]] = {
    "1B": ("nuclear_risk", "nuclear_global_risk", "nuclear_global_risk"),
    "2B": ("international_peace", "peace_aggression", "peace_aggression"),
    "3B": ("domestic_safety", "domestic_safety", "domestic_safety"),
    "4B": ("political_freedom", "political_freedom", "political_freedom"),
    "5B": ("economic_wellbeing", "economic_wellbeing", "economic_wellbeing"),
    "6B": ("social_wellbeing", "social_wellbeing", "social_wellbeing"),
    "7B": ("integrity", "integrity", "integrity"),
}

RULER_QUALITY_QUESTION_TEXTS: dict[str, tuple[str, ...]] = {
    "1B": (
        "Did the ruler seek to reduce nuclear or other existential risk, rather than increase prestige, leverage, or personal power through escalation?",
        "Did the ruler use nuclear rhetoric responsibly, avoiding reckless threats, brinkmanship, apocalyptic language, or normalization of nuclear use?",
        "Did the ruler strengthen command-and-control discipline, custody, safety, and accident-prevention safeguards?",
        "Did the ruler support arms-control, inspection, nonproliferation, disarmament, or de-escalation agreements in good faith?",
        "Did the ruler avoid using nuclear capability to shield conventional aggression, territorial coercion, or domestic repression?",
        "Did the ruler resist proliferation by allies, proxies, clients, or domestic factions when proliferation served short-term political interests?",
        "Did the ruler invest in risk-reducing expertise and institutions rather than surrounding nuclear/security decisions with loyalists or ideologues?",
        "In crisis moments, did the ruler de-escalate, communicate clearly, and preserve channels that reduce accidental war?",
        "Did the ruler handle dual-use technology, cyber, biological, AI, or other catastrophic-risk domains with precaution and transparency?",
        "Did the ruler leave the country's existential-risk posture safer or more dangerous than they inherited it?",
    ),
    "2B": (
        "Did the ruler choose diplomacy, compromise, and de-escalation when credible peaceful alternatives existed, rather than treating force as the preferred first option?",
        "Did the ruler initiate, expand, prolong, or justify wars of choice, cross-border coercion, annexation, covert destabilization, or proxy conflict beyond defensive necessity?",
        "Did the ruler distinguish genuine defensive security needs from prestige, revenge, nationalism, manufactured threats, diversionary politics, or regime-survival motives?",
        "Did the ruler respect civilian protection, humanitarian law, prisoner treatment, necessity, and proportionality in military operations?",
        "Did the ruler restrain security forces, militias, allies, proxies, clients, and arms recipients from atrocities or destabilization, and accept responsibility for foreseeable proxy conduct?",
        "Did the ruler truthfully explain security threats to the public, or manipulate intelligence, fear, historical grievance, and misinformation to build support for conflict?",
        "Did the ruler pursue credible ceasefires, peace talks, confidence-building measures, lawful settlements, or post-conflict reconciliation when possible?",
        "Did the ruler use military spending and mobilization to meet real security needs, or to enrich networks, reward security elites, intimidate neighbors, or project personal strength?",
        "Did the ruler accept accountability for military failures, civilian harm, illegal conduct, and later evidence that contradicted the stated justification for conflict?",
        "Did the ruler leave regional/international relations more peaceful, stable, and lawful than they inherited them, accounting for inherited conflicts and external constraints?",
    ),
    "3B": (
        "Did the ruler protect residents from state violence, torture, disappearances, political imprisonment, extrajudicial killing, and arbitrary or exemplary punishment?",
        "Did the ruler prevent, punish, or tolerate abuse by police, military, intelligence services, prisons, militias, party enforcers, informal loyalists, or tolerated vigilantes?",
        "Did the ruler personally incite hatred, revenge, dehumanization, scapegoating, or violence against opponents, minorities, migrants, journalists, civil society, or religious/ethnic/sectarian/caste/racial groups?",
        "Did the ruler build systems for due process, complaint handling, civilian oversight, and independent investigation of abuse, including abuse by politically protected actors?",
        "Did the ruler use emergency powers, security laws, surveillance, anti-terror measures, or administrative controls narrowly and lawfully, or as tools for intimidation, collective punishment, and control?",
        "Did the ruler reduce domestic fear and insecurity without replacing criminal, communal, or insurgent violence with state terror or a broader political fear climate?",
        "Did the ruler protect women, children, minorities, and vulnerable groups from targeted violence, intergroup/religious/ethnic/sectarian/caste/racial violence, displacement, and systematic neglect?",
        "Did the ruler allow peaceful protest, dissent, and community organization without retaliation, chilling surveillance, arbitrary restrictions, or selective punishment?",
        "Did the ruler respond to domestic crises and spontaneous flare-ups with protection, restraint, and suppression of violence rather than incitement, tolerance, collective punishment, censorship, or militarized spectacle?",
        "Did the ruler leave citizens safer from political violence, intergroup violence, deaths/injuries/displacement, and preventable domestic insecurity than they inherited them?",
    ),
    "4B": (
        "Did the ruler genuinely accept that power should be contestable through free, fair, and meaningful elections?",
        "Did the ruler refrain from manipulating electoral rules, courts, media, election commissions, security forces, or public resources to entrench themselves?",
        "Did the ruler tolerate opposition victories, criticism, satire, investigative journalism, protest, and civil-society monitoring?",
        "Did the ruler strengthen independent courts, legislatures, audit bodies, local governments, and oversight institutions even when they constrained the ruler?",
        "Did the ruler avoid personality cults, intimidation, arbitrary loyalty tests, party capture, or politicization of neutral state institutions?",
        "Did the ruler protect independent media and information access instead of spreading propaganda, disinformation, censorship, or pressure on owners/journalists?",
        "Did the ruler protect political equality for minorities, women, excluded groups, opposition regions, and unpopular viewpoints?",
        "Did the ruler respect term limits, succession rules, coalition commitments, and constitutional transfer of power?",
        "Did the ruler use surveillance, digital controls, internet shutdowns, or administrative harassment to limit political freedom?",
        "Did the ruler leave political freedom and democratic resilience stronger or weaker than they inherited it?",
    ),
    "5B": (
        "Did the ruler intend and act to create broad-based, sustainable prosperity rather than extract rents, buy loyalty, or maximize short-term popularity?",
        "Did the ruler appoint competent economic professionals and empower them, rather than loyalists, family members, business partners, or ideological yes-men?",
        "Did the ruler protect macroeconomic stability, fiscal responsibility, monetary credibility, and long-term investment conditions?",
        "Did the ruler create fair rules for entrepreneurship, competition, property rights, trade, investment, and job creation?",
        "Did the ruler resist corruption, favoritism, monopolies, oligarchic capture, and politically connected business privileges?",
        "Did the ruler invest in productivity foundations: infrastructure, education, health, technology, administrative capacity, and predictable regulation?",
        "Did the ruler make economic policy based on evidence and correction of mistakes, or on slogans, denial, patronage, and scapegoating?",
        "Did the ruler distribute economic gains fairly across regions, classes, genders, and groups rather than privileging regime supporters?",
        "Did the ruler manage shocks, inflation, unemployment, debt, sanctions, commodity changes, or crises with competence and honesty?",
        "Did the ruler leave the economy on a stronger trajectory than they inherited, accounting for external constraints?",
    ),
    "6B": (
        "Did the ruler treat human welfare as a core purpose of rule rather than as propaganda, patronage, or secondary concern?",
        "Did the ruler improve access to basic health, education, water, sanitation, housing, food security, and social protection?",
        "Did the ruler prioritize vulnerable groups, poor regions, children, elderly people, women, minorities, disabled people, and marginalized communities?",
        "Did the ruler fund and manage social services with competent professionals rather than patronage networks?",
        "Did the ruler use evidence, measurement, and transparent correction to improve service delivery?",
        "Did the ruler reduce avoidable suffering during crises such as pandemics, disasters, conflict displacement, famine, or economic shocks?",
        "Did the ruler avoid using welfare, permits, jobs, food, housing, or benefits as tools of political loyalty and punishment?",
        "Did the ruler protect dignity and equal opportunity, not only aggregate welfare numbers?",
        "Did the ruler build durable social institutions that would survive beyond their personal rule?",
        "Did the ruler leave ordinary people with better life chances than they inherited, accounting for baseline and constraints?",
    ),
    "7B": (
        "Does the ruler habitually tell the truth to the public, legislature, courts, allies, and international partners, especially on matters where deception would protect power or reputation?",
        "Does the ruler admit errors, correct false claims, and allow truthful reporting, or do they knowingly mislead, double down, blame others, and punish truth-tellers?",
        "Does the ruler separate personal/family/business interests from state decisions, public contracts, licensing, regulation, law enforcement, and foreign policy?",
        "Does the ruler or close family profit from office through assets, contracts, monopolies, gifts, bribes, emoluments, insider access, opaque foundations, or hidden conflicts of interest?",
        "Does the ruler appoint competent professionals, or fill government with family, friends, cronies, donors, business associates, loyalists, and yes-men to protect personal power or self-dealing?",
        "Does the ruler tolerate independent investigation of their conduct, assets, campaign finance, conflicts of interest, associates, and concealed official decisions?",
        "Does the ruler use state power to conceal illegal, destructive, or self-serving activity, protect themselves from accountability, punish investigators, or neutralize courts, prosecutors, auditors, media, and whistleblowers?",
        "Does the ruler keep promises and respect formal commitments, or opportunistically reverse positions, manipulate public information, and conceal tradeoffs for personal advantage?",
        "Does the ruler avoid nepotism, favoritism, clientelism, and transactional politics in appointments, pardons, procurement, enforcement, and access to public information?",
        "Does the ruler model ethical standards that improve public trust, or normalize deliberate lying, impunity, self-dealing, conflicts of interest, and cynicism?",
    ),
}

QUESTION_SPECS: dict[str, QuestionSpec] = {
    "state_based_armed_conflict": QuestionSpec(
        methodology_id="2.1",
        question_code="international_peace/state_based_armed_conflict",
        question_key="state_based_armed_conflict",
        text="Was the country involved in state-based armed conflict in the target/proxy year?",
        category="international_peace",
        answer_level="country_year",
        answer_type="boolean",
        evidence_strategy="structured",
        support_status="structured",
        expected_scope_keys=("country", "year"),
        concept_keys=("ucdp_state_based_conflict",),
        default_analyses=("coverage",),
        acquisition_policy="none",
        output_fields=(
            "answer",
            "state_based_events",
            "state_based_fatalities",
            "evidence_year",
            "coverage_status",
            "source_observation_ids",
            "warning_codes",
        ),
    ),
    "conflict_fatalities_structured": QuestionSpec(
        methodology_id="2.3",
        question_code="conflict/fatalities",
        question_key="conflict_fatalities_structured",
        text="Get structured conflict fatalities for the requested country-year scope.",
        category="conflict",
        answer_level="country_year",
        answer_type="numeric",
        evidence_strategy="structured",
        support_status="structured",
        expected_scope_keys=("country", "year"),
        concept_keys=("conflict_fatalities",),
        default_analyses=("coverage",),
        acquisition_policy="none",
    ),
    "leader_legal_cases_qualitative": QuestionSpec(
        methodology_id="6B.legal_cases",
        question_code="integrity/legal_cases",
        question_key="leader_legal_cases_qualitative",
        text="Identify open criminal or corruption legal cases with cited evidence.",
        category="integrity",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "year"),
        concept_keys=("leader_open_criminal_or_corruption_case",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
    ),
    "ruler_effectiveness_program": QuestionSpec(
        methodology_id="8B.1",
        question_code="effectiveness/program",
        question_key="ruler_effectiveness_program",
        text=(
            "Does the ruler articulate a clear governing ideology, strategic direction, "
            "or program, including explicit or revealed goals for power, policy, or "
            "regime control, that can be evaluated against later action?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_priorities": QuestionSpec(
        methodology_id="8B.2",
        question_code="effectiveness/priorities",
        question_key="ruler_effectiveness_priorities",
        text=(
            "Does the ruler translate that program into concrete priorities, plans, "
            "budgets, appointments, timelines, institutions, and enforcement mechanisms?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_mobilization": QuestionSpec(
        methodology_id="8B.3",
        question_code="effectiveness/mobilization",
        question_key="ruler_effectiveness_mobilization",
        text=(
            "Does the ruler mobilize the state apparatus, party, military, bureaucracy, "
            "coalition, or ruling network effectively toward the chosen program and the "
            "ruler's own goals?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_appointments": QuestionSpec(
        methodology_id="8B.4",
        question_code="effectiveness/appointments",
        question_key="ruler_effectiveness_appointments",
        text=(
            "Does the ruler select and empower people who are capable of executing the "
            "program, whether professionals, loyal operators, technocrats, organizers, "
            "security officials, or coercive administrators?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_coordination": QuestionSpec(
        methodology_id="8B.5",
        question_code="effectiveness/coordination",
        question_key="ruler_effectiveness_coordination",
        text=(
            "Does the ruler maintain internal discipline, coordination, control, and "
            "follow-through across ministries, regions, territory, institutions, "
            "security forces, party structures, and implementing agencies?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_implementation": QuestionSpec(
        methodology_id="8B.6",
        question_code="effectiveness/implementation",
        question_key="ruler_effectiveness_implementation",
        text=(
            "Does the ruler convert declarations into observable implementation and "
            "state reach rather than leaving goals as slogans, speeches, symbolic "
            "gestures, or propaganda only?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_outcomes": QuestionSpec(
        methodology_id="8B.7",
        question_code="effectiveness/outcomes",
        question_key="ruler_effectiveness_outcomes",
        text=(
            "Do outcome indicators move in the direction the ruler claimed or revealed "
            "they sought, after allowing for realistic lags, inherited conditions, and "
            "external constraints?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_adaptation": QuestionSpec(
        methodology_id="8B.8",
        question_code="effectiveness/adaptation",
        question_key="ruler_effectiveness_adaptation",
        text=(
            "When tactics fail, does the ruler adapt methods, replace ineffective "
            "implementers, reallocate resources, or otherwise correct course to keep "
            "advancing the program and maintaining effective control?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_crisis_management": QuestionSpec(
        methodology_id="8B.9",
        question_code="effectiveness/crisis_management",
        question_key="ruler_effectiveness_crisis_management",
        text=(
            "Does the ruler manage crises, opposition, international relationships, "
            "and institutional resistance in a way that preserves or advances the "
            "regime's chosen objectives, durability, and influence, regardless of "
            "whether those objectives are morally good?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
    "ruler_effectiveness_period_end": QuestionSpec(
        methodology_id="8B.10",
        question_code="effectiveness/period_end",
        question_key="ruler_effectiveness_period_end",
        text=(
            "By the end of the relevant period, is the ruler closer to achieving the "
            "stated or revealed ideological, policy, power-consolidation, or "
            "international-influence program than at the start, accounting for "
            "short-term wins, long-term durability, inherited conditions, and external "
            "shocks?"
        ),
        category="effectiveness",
        answer_level="ruler_period",
        answer_type="evidence_bundle",
        evidence_strategy="internet_manual",
        support_status="internet_manual",
        expected_scope_keys=("country", "leader", "period"),
        concept_keys=("ruler_effectiveness_qualitative_evidence",),
        default_analyses=("coverage", "human_review_queue"),
        acquisition_policy="plan_only",
        output_fields=("answer", "confidence", "citations", "warning_codes"),
    ),
}


def _build_ruler_quality_question_specs() -> dict[str, QuestionSpec]:
    specs: dict[str, QuestionSpec] = {}
    for chapter_id, questions in RULER_QUALITY_QUESTION_TEXTS.items():
        category, code_prefix, key_prefix = RULER_QUALITY_CATEGORY_SPECS[chapter_id]
        for index, text in enumerate(questions, start=1):
            methodology_id = f"{chapter_id}.{index}"
            question_key = f"ruler_{key_prefix}_{index}"
            specs[question_key] = QuestionSpec(
                methodology_id=methodology_id,
                question_code=f"{code_prefix}/{index}",
                question_key=question_key,
                text=text,
                category=category,
                answer_level="ruler_period",
                answer_type="evidence_bundle",
                evidence_strategy="internet_manual",
                support_status="internet_manual",
                expected_scope_keys=("country", "leader", "period"),
                concept_keys=("ruler_quality_qualitative_evidence",),
                default_analyses=("coverage", "human_review_queue"),
                acquisition_policy="plan_only",
                output_fields=("answer", "confidence", "citations", "warning_codes"),
            )
    return specs


QUESTION_SPECS.update(_build_ruler_quality_question_specs())


def get_question_spec(question_key: str) -> QuestionSpec | None:
    """Return a registered question spec, if known."""

    return QUESTION_SPECS.get(question_key)


def get_question_spec_by_methodology_id(methodology_id: str) -> QuestionSpec | None:
    """Return a question spec by stable methodology-document question id."""

    for spec in QUESTION_SPECS.values():
        if spec.methodology_id == methodology_id:
            return spec
    return None


def list_question_specs() -> tuple[QuestionSpec, ...]:
    """Return all registered question specs in deterministic order."""

    return tuple(sorted(QUESTION_SPECS.values(), key=lambda spec: spec.methodology_id))


def get_concept_spec(concept_key: str) -> ConceptSpec | None:
    """Return a registered concept spec, if known."""

    return CONCEPT_SPECS.get(concept_key)


__all__ = [
    "CONCEPT_SPECS",
    "QUESTION_SPECS",
    "get_concept_spec",
    "get_question_spec",
    "get_question_spec_by_methodology_id",
    "list_question_specs",
]
