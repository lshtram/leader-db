# Pipeline Agent Questions and Prompts

Status: review reference for the controlled 2022 evaluation  
Last synchronized: 2026-07-24

This document puts the questions and model instructions used by the cited-evaluation
pipeline in one place. It is intended for human review. The executable prompt builders,
schemas, and chapter guides remain authoritative; links to them are included so a
reviewer can detect drift.

The latest validated workflow and measured results are recorded in
[`local-web-separated-2022-ten-case-gate.md`](../reviews/local-web-separated-2022-ten-case-gate.md).
That gate is the authority for the currently accepted separation between structured
local evidence and web research.

Dynamic run data is shown as `{placeholders}` rather than copying a ruler's evidence
into this document. JSON-only serialization instructions are summarized where the exact
shape is enforced by a Pydantic schema rather than prose.

## 1. Pipeline Map

| Phase | Agent | Web access | Scores | Primary input | Primary output |
|---|---|---:|---:|---|---|
| L | Deterministic local evidence builder | No | No | Hash-verified structured observations and chapter mappings | Parent-owned package plus bounded chapter judge packages |
| A | Reconnaissance researcher | Yes | No | Short ruler brief and deliberately small orientation briefing | Initial web notebook and source-claim ledger |
| B | Chapter researcher, once per selected chapter | Yes | No | Bounded recon summary, one compact chapter guide, resource index | Chapter web source-claim units |
| C | Evidence reviewer | No | No | Accumulated notebook, ledger, required lenses | Defects, gaps, and continuation request |
| D | Targeted research continuation | Yes | No | Reviewer gaps and bounded prior-resource index | Added or corrected web evidence |
| E | Supervisor takeover, only after recoverable stalling | Yes | No | Review report and accumulated notebook | Completed permissive research handoff |
| F | Dossier formatter | No | No | Web handoff, ledger, local status/disposition summary | Strict cited web dossier |
| G | Comparative chapter judge, one per chapter | No | Yes | Web projections, direct bounded local packages, and full chapter guide | One calibrated chapter score per ruler |

The producer/receiver rule applies throughout:

- every producer must try to make its output complete, accurate, internally
  reconciled, and maximally useful;
- every receiver must preserve and use meaningful input, tolerate harmless format or
  vocabulary variation, and repair deterministic defects when the intended content is
  unambiguous;
- a tolerant receiver does not excuse a producer defect: every recovery is recorded,
  measured, and routed back into producer improvement;
- missing evidence normally lowers confidence, widens the plausible range, or triggers
  a bounded iteration; it causes terminal failure only when the remaining material is
  genuinely insufficient for the requested judgment.

The ten-case gate demonstrated both sides of this rule. All dossiers remained
judgeable, but eight formatter outputs needed 45 inferred lens mappings and one
manifest-required Scholz fact was restored. Formatter-producer completeness therefore
remains a required repair gate before the full cohort.

## 2. Structured Local Evidence

### 2.1 Local evidence builder

Executable sources:
[`local_prior_package.py`](../../src/leaders_db/research/local_prior_package.py),
[`local_longitudinal.py`](../../src/leaders_db/research/local_longitudinal.py), and
[`chapter_projection.py`](../../src/leaders_db/research/chapter_projection.py)

The local evidence builder is independent of the web researcher. It:

1. starts from the complete hash-verified, client-excluding local artifact;
2. deduplicates repeated question-level facts into stable `LF*` facts;
3. preserves observation IDs, exact concepts, units, uncertainty, warnings, years,
   period roles, and chapter-routing candidates;
4. derives reconstructable `LS*` longitudinal signals without allowing a signal to
   change a score mechanically;
5. builds one bounded package per chapter containing all target-year facts plus
   earliest/latest pre-accession and tenure facts per indicator;
6. retains the complete artifact with the parent and sends the bounded chapter package
   directly to the judge, bypassing web research and dossier formatting.

The builder asks deterministic questions rather than open-ended research questions:

1. Does the package contain all ten methodology IDs for the chapter exactly once?
2. Does every included fact genuinely route to the selected chapter?
3. Are nominal, PPP, constant-price, rate, share, count, and index concepts separate?
4. Are units, scales, uncertainty bounds, proxy years, revisions, breaks, and
   missingness warnings preserved?
5. Do derived signals retain their source observation IDs, formula, transformation
   version, lag, causal distance, and attribution limitation?
6. Is country-level context clearly separated from ruler credit or blame?
7. Are local errors visible rather than silently replaced by web evidence?

Local evidence is contextual unless separately cited ruler evidence establishes
authority, ownership, implementation, tolerance, correction, or another valid
attribution nexus. Missing local evidence is never a zero and never favorable evidence.

## 3. General Web Evidence Collection

### 3.1 Reconnaissance researcher

Executable source:
[`dossier_notebook_prompt.py`](../../src/leaders_db/research/dossier_notebook_prompt.py)

The researcher is treated as a blank slate. It receives:

- immutable ruler identity and period;
- a deliberately small parent-produced orientation briefing, never the full local
  evidence package or raw yearly series;
- plain-language descriptions of the eight subject areas;
- the small machine-recovery appendix contract.

The researcher runs without project instructions, shell access, repository or
filesystem reads,
plugins, apps, subagents, or goals. Web research and the material embedded in the prompt
are its complete working context.

Stable prompt:

> Research `{ruler}`, who governed `{country}`, focusing on `{period}`. We are preparing
> an evidence-based assessment of this ruler. Give the researchers who continue this
> work a reliable, well-organized starting point.
>
> Confirm who held power, the ruler's official position and actual influence, and
> important limits on that influence. Identify the most important events, decisions,
> policies, controversies, successes, and failures across security, peace, domestic
> safety, political freedom, economic and social wellbeing, personal integrity, and
> effectiveness.
>
> Search until additional work mostly repeats facts already found instead of adding
> material information, a stronger underlying source, credible contrary evidence, or an
> important missing perspective. Preserve every credible source that could help later
> research.
>
> Write one evidence record per important underlying fact. Several articles repeating
> the same fact belong in one record; one report with materially different findings may
> support several records. Each record includes the strongest source and stable locator,
> period relevance, connection to the ruler, contrary evidence, source cautions, and
> independent corroboration.

The orientation briefing exists only to prevent needless rediscovery and point out
known data families or obvious context. The researcher remains responsible solely for
web research. It does not build, validate, reinterpret, or re-fetch the structured
local package, and it cannot establish ruler attribution from a national indicator.

The prompt ends by requiring:

- a concise overview and evidence-environment assessment;
- compact atomic evidence records;
- separate later-retrospective evidence;
- separate lists for fully extracted evidence, opened corroboration, and uninspected
  leads;
- unresolved questions for deeper research;
- one machine-recoverable `SOURCE_CLAIM_JSON` line for each developed record.

### 3.2 Deep chapter researcher

Executable source:
[`chapter_research_sequence.py`](../../src/leaders_db/research/chapter_research_sequence.py)

This prompt is run in a fresh compact session once for each selected chapter. It
receives only:

- the immutable ruler-period;
- that chapter's ten lens IDs;
- a bounded reconnaissance summary;
- the chapter guide's ten lenses and researcher-facing guidance;
- a compact index of already found resources.

It explicitly receives neither the structured local package nor the complete
accumulated dossier, prior tool history, other chapter guides, client scores, or
internal project materials.

Stable prompt:

> Research `{chapter subject}` under `{ruler}` in `{country}` during `{period}`.
>
> Prepare a complete, carefully sourced account for researchers who will assess this
> part of the ruler's record. Research the subject without assigning a score. Use the
> questions below as different angles on the same subject. They identify important
> evidence; they are not separate ratings, search quotas, or an arithmetic checklist.
>
> Build the factual record through six observable evidence channels: formal acts and
> law; resources; personnel; implementation and operational conduct; public
> communications and representations; and outcomes. Use the channels that materially
> fit this chapter. They are not quotas or separate scores.
>
> Keep the source type separate from the observed fact. An audit, court record or
> inquiry may verify a formal act, resource, personnel, implementation, communication
> or outcome claim. Authority, baseline, constraints, distribution, exposure,
> causation, durability and source bias are questions for interpreting evidence, not
> additional evidence channels.
>
> The six channels classify facts; they are not a preferred-source list. Books,
> academic research, NGO and international-organization reports, investigative and
> specialist journalism, biographies, histories, expert analysis, and credible local
> reporting remain essential for overview, informal conduct, materiality,
> interpretation, attribution, and scrutiny of official claims.
>
> Research proportionately. Begin with strong overview and synthesis sources that
> identify consequential conduct. Inspect particular laws, budgets, appointments,
> speeches, audits, judgments, and datasets when they establish a material claim,
> resolve disagreement, improve attribution, or test implementation. Do not catalogue
> every act, budget line, appointment, statement, program, or outcome from the period.
>
> Start by forming a working account of the ruler's formal and practical authority, the
> inherited baseline, external shocks and constraints, and the important favorable,
> adverse, disputed, and exculpatory possibilities raised by every selected question.
> Treat the resource list as a starting point. Open an underlying source before using
> it as evidence. Search primary and legal records, independent monitoring,
> scholarship, reputable reporting, archives, relevant local-language material, and
> credible favorable, adverse, and contrary interpretations.
>
> Continue while research produces a materially new fact, a stronger underlying
> source, credible contrary evidence, an important missing perspective, or a necessary
> correction. Conclude when additional searching mostly repeats what is already known.
> There is no document or evidence-record quota.

There is no resource or evidence-record cap. Earlier numeric guidance is diagnostic,
not a collection limit: retain every materially useful, defensible source-claim unit.
A report containing distinct material claims selected for downstream use requires a
separate record and precise locator for each selected claim; this does not require
extracting every row, program, decision, event, finding, or remedy in the report.
Research ends on reasoned saturation or a concrete blocker, not when a target count is
reached.

## 4. The Eight Chapter Question Sets

These are overlapping evidence lenses, not eighty scores and not an arithmetic
checklist. The full guides add scope gates, exclusions, attribution rules, rubrics, and
chapter-specific calibration.

### 4.1 Chapter 1B — Nuclear and existential risk

Full guide:
[`1b-nuclear-existential-risk.md`](chapter-guides/1b-nuclear-existential-risk.md)

1. **1B.1:** Did the ruler use formal authority, strategy, directives, and resource choices to reduce nuclear or other existential risk rather than increase prestige, leverage, or personal power through escalation?
2. **1B.2:** Did the ruler avoid reckless threats, brinkmanship, apocalyptic language, and normalization of nuclear use, and did formal doctrine, orders, and operational posture corroborate rather than contradict responsible rhetoric?
3. **1B.3:** Did the ruler enact, fund, staff, implement, and enforce effective command-and-control, custody, safety, inspection, and accident-prevention safeguards, and correct identified failures?
4. **1B.4:** Did the ruler support, ratify, implement, fund, and comply with arms-control, inspection, nonproliferation, disarmament, and de-escalation agreements, or obstruct and weaken them?
5. **1B.5:** Did the ruler avoid formally or operationally using nuclear capability to authorize, shield, or intensify conventional aggression, territorial coercion, or domestic repression?
6. **1B.6:** Did the ruler establish and enforce proliferation controls against allies, proxies, clients, firms, and domestic factions, and respond when monitoring exposed evasion or assistance?
7. **1B.7:** Did the ruler appoint qualified, independent experts, protect their access and dissent, and resource risk-reducing institutions rather than replace expertise with loyalty or ideology?
8. **1B.8:** In crises, did the ruler issue and implement de-escalatory decisions, preserve communication and decision safeguards, and correct procedures exposed as dangerous?
9. **1B.9:** Did the ruler establish, fund, enforce, and transparently review precautionary legal and institutional safeguards for AI, cyber, biological, and other catastrophic dual-use risks?
10. **1B.10:** Did the ruler leave a demonstrably safer and more durable existential-risk posture than inherited, accounting for authority, implementation, external shocks, and unresolved exposure?

Research emphasis: exposure and authority; inherited capability; doctrine and arsenal
change; command safety; treaties and inspections; threats and crises; proliferation;
expert appointments; catastrophic dual-use policy; end-of-period posture.

### 4.2 Chapter 2B — International peace

Full guide:
[`2b-international-peace.md`](chapter-guides/2b-international-peace.md)

1. **2B.1:** When credible peaceful alternatives existed, did the ruler use formal decisions, diplomatic authority, and available legislative or cabinet processes to pursue them before authorizing or supporting force?
2. **2B.2:** Did the ruler initiate, authorize, fund, expand, prolong, or legally entrench wars of choice, annexation, cross-border coercion, covert destabilization, or proxy conflict beyond defensive necessity?
3. **2B.3:** Did the ruler present decision-makers and the public with accurate, reviewable evidence of defensive need, alternatives, and objectives rather than manufacture threats or exploit prestige, revenge, nationalism, historical grievance, diversionary politics, or regime-survival claims?
4. **2B.4:** Did the ruler adopt, resource, and enforce lawful rules of engagement, civilian protection, and prisoner safeguards, investigate violations, and provide discipline or remedy?
5. **2B.5:** Did the ruler establish and enforce arms-transfer, proxy, and allied-force controls, monitor foreseeable abuse, and suspend support or correct policy when harm emerged?
6. **2B.6:** Did the ruler permit legislative, judicial, media, and independent scrutiny of conflict claims and correct false or misleading official accounts?
7. **2B.7:** Did the ruler negotiate, approve, implement, and comply with credible ceasefires, peace agreements, confidence-building measures, and lawful settlements, and help make them durable?
8. **2B.8:** Did military budgets, mobilization, and procurement address genuine security needs transparently and proportionately rather than enrich networks, entrench security elites, or intimidate neighbors?
9. **2B.9:** Did the ruler cooperate with courts, inquiries, audits, and casualty disclosure; accept responsibility; correct unlawful policy; discipline responsible actors; and provide meaningful remedy?
10. **2B.10:** Did the ruler leave relations more peaceful, stable, and lawful through durable institutions and settlements, accounting for inherited conflicts, actual authority, and external constraints?

Research emphasis: inherited conflicts and threats; initiation and alternatives;
objectives and justification; civilian conduct; proxies and arms recipients; public
claims; negotiations; military patronage; accountability; end-state change.

### 4.3 Chapter 3B — Domestic safety

Full guide:
[`3b-domestic-safety.md`](chapter-guides/3b-domestic-safety.md)

1. **3B.1:** Did the ruler establish and enforce laws, orders, and detention practices that protected residents from torture, disappearance, political imprisonment, extrajudicial killing, and arbitrary punishment, and remedy verified abuse?
2. **3B.2:** Did the ruler appoint, resource, direct, and discipline police, military, intelligence, prison, militia, and aligned actors to prevent abuse rather than tolerate or reward it?
3. **3B.3:** Did the ruler avoid personally or officially inciting hatred, revenge, dehumanization, scapegoating, or violence against opponents, minorities, migrants, journalists, civil society, or other groups, and act when supporters or officials translated such messages into harm?
4. **3B.4:** Did the ruler create, fund, and respect independent courts, complaint systems, civilian oversight, and investigations, comply with findings, and provide victim remedy?
5. **3B.5:** Did the ruler enact, renew, administer, review, and repeal emergency, surveillance, anti-terror, and security powers narrowly and lawfully rather than use them for intimidation, collective punishment, or control?
6. **3B.6:** Did the ruler reduce exposure-adjusted criminal, communal, and insurgent violence through lawful, proportionate policy without replacing it with state terror or a broader fear climate?
7. **3B.7:** Did the ruler enact, fund, and enforce effective protection for women, children, minorities, and vulnerable groups against targeted and intergroup violence, displacement, and systematic neglect, with equitable access across regions and populations?
8. **3B.8:** Did laws, permit systems, policing orders, and actual enforcement protect peaceful protest, dissent, and organization, with accountability and remedy for retaliation or excessive force?
9. **3B.9:** During domestic crises, did the ruler issue and implement protective, restrained measures, allocate resources according to exposure, and correct failures rather than use incitement, collective punishment, censorship, or militarized spectacle?
10. **3B.10:** Did the ruler leave people durably safer from state and non-state violence than inherited, accounting for reporting freedom, population exposure, authority, and external shocks?

Research emphasis: physical-integrity abuse; aligned actors; ruler rhetoric; oversight
and remedies; emergency and surveillance powers; state versus non-state fear;
vulnerable groups; protest treatment; crisis response; inherited-to-end safety.

### 4.4 Chapter 4B — Political freedom

Full guide:
[`4b-political-freedom.md`](chapter-guides/4b-political-freedom.md)

1. **4B.1** — Did the ruler support and implement electoral and constitutional laws, funding, and administration that made power genuinely contestable, and accept verified opposition victories?
2. **4B.2** — Did the ruler refrain from proposing, signing, decreeing, manipulating, or obstructing laws, courts, election administration, security forces, media, or public resources to entrench personal or party power?
3. **4B.3** — Did the ruler protect in law and practice opposition, criticism, satire, investigative journalism, protest, association, and civil-society monitoring, and remedy violations?
4. **4B.4** — Did the ruler protect the jurisdiction, appointment independence, tenure, funding, and decisions of courts, legislatures, election bodies, auditors, and local governments even when they constrained the ruler?
5. **4B.5** — Did appointments, dismissals, civil-service rules, and administrative practice preserve politically neutral institutions rather than impose loyalty tests, party capture, intimidation, or a personality cult?
6. **4B.6** — Did the ruler support and enforce media, information-access, ownership, and licensing rules that enabled independent information rather than censorship, propaganda, disinformation, or pressure?
7. **4B.7** — Did the ruler enact and enforce equal political rights and access for minorities, women, excluded groups, opposition regions, and unpopular viewpoints?
8. **4B.8** — Did the ruler preserve and comply with term limits, succession rules, coalition commitments, and constitutional transfer rather than amend, evade, or obstruct them for continued power?
9. **4B.9** — Did the ruler narrowly authorize, transparently procure, and lawfully oversee surveillance and digital controls, or use law, shutdowns, and administrative harassment to suppress political freedom?
10. **4B.10** — Did the ruler leave political freedom and democratic resilience durably stronger than inherited through enacted, implemented, and independently reviewable institutions, accounting for correction and constraints?

Research emphasis: election contestability; entrenchment; opposition and civic space;
checks and oversight; institutional capture; media and information; political equality;
succession; digital controls; inherited-to-end trajectory.

### 4.5 Chapter 5B — Economic wellbeing

Full guide:
[`5b-economic-wellbeing.md`](chapter-guides/5b-economic-wellbeing.md)

1. **5B.1** — Did the ruler's legislative agenda, formal policies, and executed budgets pursue broad-based sustainable prosperity rather than rents, loyalty purchases, or short-term popularity?
2. **5B.2** — Did the ruler appoint qualified economic professionals through credible processes, empower their operational independence, and retain or replace them based on performance rather than loyalty?
3. **5B.3** — Did the ruler enact, administer, and comply with credible fiscal, tax, debt, monetary, and financial rules that protected macroeconomic stability and long-term investment?
4. **5B.4** — Did the ruler create and consistently enforce fair laws and regulations for competition, entrepreneurship, property, trade, investment, and job creation?
5. **5B.5** — Did the ruler enforce competition, procurement, disclosure, and anti-corruption rules against politically connected actors, cooperate with audits and courts, and remedy proven favoritism or capture?
6. **5B.6** — Did enacted and executed budgets produce timely, high-quality infrastructure, education, health, technology, administrative capacity, and predictable regulation rather than announcements or patronage projects?
7. **5B.7** — Did the ruler publish reliable economic information, permit independent evaluation and audit, and correct laws, programs, or implementers when evidence showed failure rather than rely on slogans, denial, patronage, or scapegoating?
8. **5B.8** — Did tax, labor, wage, benefit, investment, and regional policies distribute gains and burdens fairly in actual incidence across classes, regions, genders, and groups?
9. **5B.9** — During inflation, unemployment, debt, sanctions, commodity, or other shocks, did the ruler use timely, funded, and transparently targeted measures, monitor their effects, and correct mistakes?
10. **5B.10** — Did the ruler leave a stronger and more durable economic trajectory than inherited, accounting for implementation lags, external conditions, institutional constraints, and distribution rather than GDP alone?

Research emphasis: goals and appointments; macro stability; market rules; capture;
productivity investment; evidence and correction; distribution; shocks; inherited
trend; ruler-attributable implementation and outcomes.

### 4.6 Chapter 6B — Social wellbeing

Full guide:
[`6b-social-wellbeing.md`](chapter-guides/6b-social-wellbeing.md)

1. **6B.1** — Did the ruler enact and fund enforceable social commitments that made human welfare a core purpose of government rather than propaganda, patronage, or a secondary concern?
2. **6B.2** — Did laws, eligibility rules, executed budgets, and service administration improve affordable, effective access and uptake across health, education, water, sanitation, housing, food security, and social protection?
3. **6B.3** — Did the ruler enact, target, fund, and enforce protection for poor regions, children, older people, women, minorities, disabled people, and marginalized groups, with evidence of actual incidence and exclusion?
4. **6B.4** — Did the ruler appoint and retain qualified administrators, provide adequate staffing and resources, and use transparent procurement to deliver social services rather than patronage?
5. **6B.5** — Did the ruler publish credible welfare and service data, permit audit and independent evaluation, and correct program design, implementation, or personnel when evidence showed failure?
6. **6B.6** — Did preparedness laws, emergency decisions, funding, and implementation reduce avoidable and unequally distributed suffering during pandemics, disasters, displacement, famine, or economic shocks?
7. **6B.7** — Did formal eligibility rules, administrative practice, and appeal systems prevent welfare, permits, jobs, food, and housing from becoming instruments of political loyalty or punishment?
8. **6B.8** — Did the ruler enact and enforce equal-rights, anti-discrimination, accessibility, and dignity protections, with practical remedy rather than relying on national averages alone?
9. **6B.9** — Did the ruler create durable social institutions with statutory authority, reliable funding, professional staffing, transparent standards, and resilience beyond personal rule?
10. **6B.10** — Did ordinary people, including disadvantaged groups, finish the period with durably better life chances than inherited, accounting for policy lag, baseline, donor or subnational roles, and external shocks?

Research emphasis: welfare goals; access, coverage, quality, outcomes, and inequality;
vulnerable groups; professional delivery; evidence and correction; crises; political
allocation; dignity; durability; inherited-to-end life chances.

### 4.7 Chapter 7B — Personal integrity

Full guide:
[`7b-integrity.md`](chapter-guides/7b-integrity.md)

1. **7B.1** — Does the ruler tell the truth in verifiable public statements, formal records, legislative testimony, courts, and international commitments, especially when deception would protect power, benefit, or reputation?
2. **7B.2** — When reliable records, courts, audits, or investigations expose error or falsehood, does the ruler correct the record, comply, and remedy harm rather than retaliate, conceal, or knowingly repeat the claim?
3. **7B.3** — Does the ruler support and personally comply with conflict-of-interest, disclosure, recusal, divestment, and ethics rules separating personal, family, and business interests from state decisions?
4. **7B.4** — Do asset, tax, gift, ownership, contract, foundation, emolument, bribe, insider-access, and legal records show that the ruler or close family profited from office, and did the ruler permit final findings, recovery, and accountability?
5. **7B.5** — Do the ruler's appointments and removals reflect competence and lawful process, or family, friendship, donations, business ties, and loyalty used to protect personal power or self-dealing?
6. **7B.6** — Did the ruler preserve the law, jurisdiction, appointments, funding, and access needed for independent investigation of their conduct, assets, campaigns, associates, and concealed decisions?
7. **7B.7** — Did the ruler comply with subpoenas, judgments, audits, and disclosure duties, or use vetoes, decrees, pardons, dismissals, secrecy, or retaliation to conceal conduct and obstruct accountability?
8. **7B.8** — Do the ruler's documented legislative positions, formal commitments, and implemented decisions show consistent good-faith promises, or opportunistic reversal and concealed tradeoffs for personal advantage?
9. **7B.9** — Did the ruler personally direct, benefit from, knowingly tolerate, or correct favoritism and clientelism in procurement, licensing, pardons, enforcement, and privileged access?
10. **7B.10** — Did the ruler's personal conduct and support for durable integrity institutions strengthen public trust, or normalize lying, impunity, self-dealing, conflicts, and cynicism?

Research emphasis: Chapter 7B requires a personal ruler nexus. National corruption,
institutional weakness, associate conduct, or silence about scandal is context unless
connected to the ruler's own acts, benefit, knowledge, tolerance, concealment, remedy,
or accountability choices.

### 4.8 Chapter 8B — Effectiveness

Full guide:
[`8b-effectiveness.md`](chapter-guides/8b-effectiveness.md)

1. **8B.1** — Did the ruler state or reliably reveal a sufficiently clear program in dated speeches, manifestos, strategies, directives, or formal acts to freeze and test its policy, ideological, power, and international goals?
2. **8B.2** — Did the ruler translate that program into enacted laws, budgets, appointments, timelines, institutions, regulations, and enforcement mechanisms within actual authority?
3. **8B.3** — Did executed resources and administrative records show effective mobilization of the state, party, military, coalition, or ruling network toward the ruler's chosen program?
4. **8B.4** — Did the ruler appoint, empower, retain, and when necessary replace people capable of executing the program, whether professionals, technocrats, organizers, loyal operators, or coercive administrators?
5. **8B.5** — Did the ruler maintain documented coordination, territorial reach, milestone completion, and compliance across ministries, regions, institutions, security forces, and implementing agencies?
6. **8B.6** — Did legislation, budgets, and directives become observable enforcement, services, projects, and institutional practice rather than remain slogans, plans, or symbolic acts?
7. **8B.7** — Did outcome and distribution indicators move toward the ruler's frozen goals after accounting for baseline, realistic lag, authority, external shocks, and plausible causal alternatives?
8. **8B.8** — Did audits, evaluations, and implementation failures lead the ruler to adapt methods, replace implementers, reallocate resources, and correct course?
9. **8B.9** — Did formal decisions and implemented responses to crises, opposition, international relations, and institutional resistance preserve or advance the ruler's chosen objectives and durable control?
10. **8B.10** — By the end of the period, had the ruler converted more of the frozen program into durable law, institutions, capacity, state practice, and achieved outcomes than at the start, accounting for failures and long-term fragility?

Research emphasis: freeze a broad portfolio of explicit or reliably revealed goals;
trace program, resources, appointments, mobilization, implementation, outcomes,
adaptation, and durability. The moral worth of the program is scored elsewhere.

## 5. Evidence Environment and Bias Questions

### 5.1 Twelve dossier evidence-environment questions

The researcher reports these conditions; the formatter makes them complete and cited.
The collector does not convert them into a score or apply a regime adjustment.

1. Was media and civil-society criticism meaningfully possible?
2. Is there evidence of censorship, surveillance, intimidation, punishment, or self-censorship?
3. Could victims, opposition figures, auditors, courts, journalists, and officials report misconduct safely?
4. Are official statistics credible, incomplete, disputed, manipulated, or unavailable?
5. Which languages and archives were searched?
6. Is evidence concentrated in official, opposition, NGO, academic, or foreign-government sources?
7. Do many records describe one underlying event?
8. Does complaint volume reflect conduct, reporting freedom, or both?
9. What population, geographic, institutional, or exposure denominators matter?
10. What inherited conditions, external shocks, and authority constraints affect interpretation?
11. Which chapter-specific biases are material?
12. Which evidence IDs support these conclusions?

### 5.2 No-search evidence reviewer

Executable source:
[`evidence_review.py`](../../src/leaders_db/research/evidence_review.py)

The reviewer receives the immutable ruler-period, selected chapters and lenses,
accumulated web notebook and ledger, plus compact local status/disposition information.
It does not receive the full local fact payload and it cannot browse. It is instructed:

> Review evidence quality and research completeness, not the ruler and not a future
> score. Do not search. Treat exact coverage vocabulary and harmless formatting
> differences as repairable. Preserve usable evidence and request continuation only for
> concrete, material gaps that research can improve.

For every selected chapter, it asks:

1. Were both favorable and adverse or contrary searches performed?
2. Was closed-regime or censored-system silence mistaken for favorable evidence?
3. Was high complaint volume in an open system mistaken for greater severity?
4. Do repeated articles or reports describe one underlying event or source claim?
5. Are allegations, documented events, official findings, and legal judgments distinguished?
6. Are official claims independently checked where independence matters?
7. Are population, exposure, ruler authority, inherited baseline, and external shocks addressed?
8. Is a source type missing that is needed to resolve the chapter's principal bias risk?
9. Are temporal fit, ruler attribution, contrary evidence, source independence, and precise locators adequate?
10. Is the chapter sufficiently complete to format, or is a targeted continuation likely to materially improve it?

Stable decision prompt:

> Return the selected chapters exactly once with their concrete defects and recoverable
> tasks. Do not prescribe a score or decide whether a judge should return numeric or
> null. Missing evidence is not adverse ruler evidence. Terminal insufficiency is
> reserved for identity failure or evidence that remains genuinely unusable after
> reasonable, documented attempts.

An initial review may request a targeted continuation. A second review may request one
final targeted continuation. The third review is terminal: it preserves all residual
gaps and explicitly records exhausted rounds, but it cannot request endless research
or pretend that exhaustion means completeness.

### 5.3 Research continuation

Executable source:
[`notebook_continuation.py`](../../src/leaders_db/research/notebook_continuation.py)

Stable compact prompt:

> Research the remaining evidence gaps for `{ruler}` governing `{country}` during
> `{period}`. Search the web directly. The independent reviewer identified the
> recoverable gaps and concrete source problems below. Previously found resources are
> listed afterward. Do not repeat them unless you recover a stronger underlying source,
> a missing precise locator, contrary evidence, or a materially distinct fact.
>
> Open the underlying source before accepting it. Keep allegations separate from
> findings and country outcomes separate from ruler attribution. Continue until further
> searches mostly repeat existing material or a concrete access blocker remains. There
> is no evidence-count target. Return one machine record for each new or upgraded
> source-claim.

The continuation receives the reviewer brief and a bounded resource index. It does not
receive the full local evidence package, repository context, all guides, or raw prior
tool history. A persistent researcher session may be resumed when it is reliable;
fresh compact continuation sessions are valid when they preserve stable global IDs and
the cumulative parent ledger.

### 5.4 Supervisor takeover

This fallback is activated only when ordinary iterative research stalls on recoverable
tasks. It receives the latest review report and the complete accumulated notebook.

Stable prompt:

> Take over the incomplete ruler-period evidence run. Work through every selected
> chapter one at a time; search broadly, open underlying sources, and attempt the
> recoverable tasks. Preserve usable evidence. Append defensible source-claim units with
> precise locators, source summaries, period fit, ruler attribution, contrary evidence,
> and lens links. Do not demand proof of a personal order when documented formal
> responsibility is the relevant attribution. Do not score. Return a permissive research
> handoff, not strict JSON, and do not merely describe research that should be done.

## 6. Dossier Formatter

Executable source:
[`dossier_prompt.py`](../../src/leaders_db/research/dossier_prompt.py)  
Output contract:
[`dossier_models.py`](../../src/leaders_db/research/dossier_models.py)

The formatter is a separate no-search, no-score agent. It receives:

- immutable ruler identity and period;
- applicable question IDs and formatting rules;
- compact local methodology statuses and disposition/provenance summaries, without the
  complete local fact or longitudinal-signal payload;
- the completed research notebook and authoritative ledger manifest;
- an existing candidate only during a repair attempt.

Stable prompt:

> Format the supplied completed research notebook. Do not browse, add facts from memory,
> or score. Be accepting of natural-language and harmless serialization variation while
> preserving every meaningful, traceable item. Normalize the research into the strict
> dossier schema.

Its review questions and requirements are:

1. Does every evidence record have one stable evidence ID and traceable source metadata?
2. Are source claim, locator, date, temporal fit, ruler attribution, evidence role, contrary evidence, and lens mappings preserved?
3. Are duplicate reports clustered by underlying event or source claim instead of counted as independent corroboration?
4. Are discovery-only leads excluded from decisive evidence while retained for audit?
5. Are local facts kept as local facts, with their original IDs and provenance, rather than converted to web citations?
6. Are selected sources separated from rejected or merely corroborating candidates?
7. Are incompatible concepts and units kept separate?
8. Are inherited conditions and country context separated from ruler-attributed conduct?
9. Are allegations separated from findings and official claims from independent checks?
10. Is every applicable lens given an evidence-backed disposition or an honest gap?
11. Are all twelve evidence-environment questions answered with supporting E-IDs where available?
12. Are bias risks, source concentration, reporting freedom, complaint volume, denominators, authority, shocks, and missingness warnings retained?
13. Does the structured-prior summary match the supplied compact status/disposition
    summary, with the parent responsible for validation against the actual local
    package?
14. Does the dossier avoid statements that local priors were unavailable when they were supplied?
15. Does the handoff avoid instructions to the judge about what score or null decision to make?
16. Does every manifest-required final fact survive with every exact recorded lens
    mapping?
17. Do coverage rows reference declared evidence through mappings rather than serving
    as an implicit substitute for missing mappings?

The formatter must produce a dossier even when some fields need cautious normalization.
It should reject the whole handoff only when identity or traceability is genuinely
insufficient, not because exact wording, sequence, or coverage labels differ.

The receiver may infer an unambiguous mapping from an explicit coverage reference or
restore a manifest-required fact from the accumulated notebook/recovery catalog. Every
such repair is a normalization warning and a producer-quality failure, not silent
success. The ten-case gate required 45 inferred lens mappings across eight dossiers
and restored one Scholz fact; the formatter prompt and producer must be improved and
the handoff gate repeated before full-cohort evaluation.

## 7. Comparative Chapter Judges

Executable shared prompt:
[`chapter_judge_prompt.py`](../../src/leaders_db/research/chapter_judge_prompt.py)  
Output contract:
[`chapter_judge_models.py`](../../src/leaders_db/research/chapter_judge_models.py)

There are eight judge jobs, one for each chapter. They do **not** receive eight unrelated
hardcoded prompts. Each receives the shared prompt below plus:

- the complete guide for its own chapter, including its ten questions and rubric;
- every eligible ruler's compact, hash-bound web projection for that chapter;
- the independently built bounded chapter-local `LF*` facts and `LS*` longitudinal
  signals, with observation provenance and warnings;
- the unavailable-dossier manifest;
- run-scoped audit corrections, if any;
- a repair note when a previous candidate failed semantic validation.

The judge never receives the client scores and may not browse, search, read local files,
or add remembered facts.

### 7.1 Shared judge prompt

> Judge every dossier in the manifest using one common meter. The ten questions are
> overlapping evidence lenses, not ten scores and not an arithmetic checklist. Read
> each compact projection in full and use only its cited web evidence and supplied
> local evidence package.
>
> First inspect the whole batch and establish low, middle, high, and edge anchors. Then
> score every available dossier exactly once. Missing lenses reduce confidence and widen
> the plausible range; they do not mechanically lower the score. Use a null score only
> when the chapter as a whole is genuinely not defensibly judgeable. Treat mappings and
> coverage states as advisory bookkeeping; independently apply the active guide's scope,
> non-goals, exclusions, and attribution limits.
>
> Use half-point increments. A numeric score must rest on concrete, chapter-relevant,
> ruler-attributed governing conduct, not merely country indicators or evidence volume.
> For Chapters 1B-6B and 8B, documented formal responsibility for national policy,
> programs, appointments, command, implementation, tolerance, or remedy can satisfy
> attribution without proof of a personal order. Chapter 7B requires a personal-integrity
> nexus. Shared authority affects weight and confidence rather than automatically
> erasing evidence.
>
> Treat `LF*` facts and `LS*` signals as structured country context unless cited web
> evidence supports ruler attribution. Never rewrite them as `E*` web citations, never
> let a derived signal change a score mechanically, and never treat absent local data
> as a favorable result.
>
> Before scoring each ruler:
>
> 1. establish the information environment and evidence opportunity;
> 2. identify inherited baseline and external shocks;
> 3. establish formal and practical ruler authority;
> 4. collapse repeated coverage into independent underlying facts;
> 5. compare absolute conditions with change from baseline;
> 6. compare the ruler with adjacent cases;
> 7. then make the holistic judgment.
>
> Do not use discovery-only items decisively. Do not let inherited conditions, generic
> context, intentions, missing implementation evidence, or missing adverse evidence
> determine score direction. A null score carries the full 1-10 range. Reserve manual
> review for a concrete issue that could materially change the result.

The judge must write a self-contained 120-220 word chapter rationale, no more than 300
words, explaining the overall appraisal, main favorable and adverse cases, distinctions
between proven facts and allegations/context/uncertain attribution, and why materially
higher and lower anchors were rejected.

### 7.2 Required judge bias assessment

Every ruler evaluation must answer:

1. Which material biases or evidence distortions were considered?
2. Which same-dossier evidence IDs support each finding?
3. What is the likely direction of distortion?
4. Did the bias change how evidence was interpreted, and how?
5. How did it affect confidence and the plausible score range?
6. What relevant uncertainty remains?
7. Can the judge explicitly confirm that complaint or report volume was not treated as severity?
8. Can the judge explicitly confirm that no blanket democracy/autocracy correction was applied?
9. Was closed-system silence avoided as favorable evidence?
10. Were open-system disclosure and effective remedy avoided as extra misconduct?

### 7.3 Chapter-specific prompt received by each judge

| Judge | Additional guide questions and mandatory calibration focus |
|---|---|
| 1B judge | Questions 1B.1-1B.10 above; exposure class, authority over catastrophic-risk choices, realized use versus near-use versus escalation, inherited arsenal, command safety, and consequential risk reduction |
| 2B judge | Questions 2B.1-2B.10; conflict exposure, initiation and alternatives, defensive necessity, civilian/proxy conduct, peace opportunities, authority, and end-state |
| 3B judge | Questions 3B.1-3B.10; physical-safety nexus, severity, scale, recurrence, state nexus, ruler attribution, remedy, and state versus non-state insecurity |
| 4B judge | Questions 4B.1-4B.10; meaningful contestability, institutional constraints, media/civic space, equality, succession, digital controls, and inherited trajectory |
| 5B judge | Questions 5B.1-5B.10; broad prosperity, policy ownership, implementation, distribution, lag, shocks, inherited trend, and outcomes beyond GDP alone |
| 6B judge | Questions 6B.1-6B.10; spending versus access versus quality versus outcomes, distribution, crisis response, politicized allocation, durability, baseline, and lag |
| 7B judge | Questions 7B.1-7B.10; direct personal nexus, allegation/finding distinction, benefit, knowledge, correction, concealment, obstruction, nepotism, and truthfulness |
| 8B judge | Questions 8B.1-8B.10; frozen program portfolio, program basis and type, operationalization, mobilization, implementation, adaptation, goal progress, durability, causal attribution, and explicit moral separation |

### 7.4 Required judge output questions

For each ruler the output contract requires the judge to resolve:

1. What is the holistic `score_1_to_10`, or why is no responsible score possible?
2. What is the 0-100 confidence and plausible score range?
3. Which cited evidence is decisively favorable and decisively adverse?
4. What inherited baseline, constraints, shocks, and authority matter?
5. Which lenses are supported and which remain weak?
6. What contrary evidence and causal alternatives remain?
7. What is the source mix and structured-local-prior summary?
8. Which adjacent ruler cases calibrate the score?
9. Why is a materially lower anchor rejected?
10. Why is a materially higher anchor rejected?
11. Is manual review required for a concrete score-material issue?
12. What chapter-specific fields required by the active guide apply?

## 8. Prompt Payload Boundaries

To keep model context useful rather than merely large:

- the parent owns the complete hash-verified local artifact throughout;
- reconnaissance receives only a deliberately small orientation briefing, not the
  complete local package or yearly series;
- chapter research receives one chapter guide, a bounded recon summary, and a resource
  index, not local facts, the complete accumulated dossier, or raw tool history;
- the reviewer receives the notebook and ledger because it must audit completeness but
  cannot browse; local input is limited to status/disposition context;
- continuation receives the reviewer brief and bounded prior-resource index, not the
  complete notebook or local package;
- the formatter receives the complete research handoff because it must preserve and
  normalize it, plus compact local dispositions but not local fact payloads;
- each judge receives only its chapter web projections and independently built bounded
  local packages across rulers, not eight full dossiers and not other chapters;
- client scores never enter researcher, formatter, or judge prompts.

## 9. Token and Quality Profiling

Every model call from initial web research through final judging must preserve
provider-reported input, cached-input where exposed, output, and reasoning tokens.
Reports must also retain explicit prompt bytes so prompt size is not confused with
provider-side browsing/tool context.

The validated ten-case gate measured:

| Phase | Calls | Input tokens | Output tokens |
|---|---:|---:|---:|
| Web research | 30 | 19,154,134 | 223,947 |
| No-search evidence review | 30 | 1,658,809 | 70,320 |
| Dossier formatting | 10 | 633,861 | 160,416 |
| Chapter judging | 8 | 614,914 | 29,824 |

The compact continuation prompts were approximately 10–23 KB, yet browser-enabled
research remained the dominant token consumer because search results, opened sources,
and provider tool context enter usage. Therefore:

1. do not diagnose researcher bloat from total input tokens alone;
2. report explicit prompt bytes, cached input, searches, opened sources, accepted
   records, defensible-record estimates, and independent source-family estimates;
3. optimize redundant searching and repeated source opening without imposing an
   evidence cap or discouraging contrary evidence;
4. compare quality and cost on the same frozen cases before promoting a prompt;
5. profile formatter and judge phases separately rather than attributing their input
   to research.

The gate improved the preserved first-pass ledgers from 163 to 344 records, with 318
surviving strict formatting and terminal reviewers estimating 25–37 defensible
source-claims across 10–20 source families per case. These are diagnostics, not quotas
or guarantees that every residual theme was resolved.

## 10. Drift Review Checklist

When a prompt or guide changes:

1. update the executable prompt builder or authoritative chapter guide;
2. update its schema tests;
3. update this review reference in the same change;
4. verify all eighty lens IDs and texts against the guides;
5. verify the twelve evidence-environment questions and judge bias fields;
6. render representative prompts and confirm payload boundaries and token profiles;
7. run the affected prompt, schema, reviewer, formatter, and judge tests;
8. inspect producer normalization warnings and fail promotion when receiver recovery
   hides a repeated producer defect;
9. preserve a curated, checksum-manifested experiment bundle for every promotion gate.
