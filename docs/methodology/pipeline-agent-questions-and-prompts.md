# Pipeline Agent Questions and Prompts

Status: review reference for the controlled 2022 evaluation  
Last synchronized: 2026-07-24

This document puts the questions and model instructions used by the cited-evaluation
pipeline in one place. It is intended for human review. The executable prompt builders,
schemas, and chapter guides remain authoritative; links to them are included so a
reviewer can detect drift.

Dynamic run data is shown as `{placeholders}` rather than copying a ruler's evidence
into this document. JSON-only serialization instructions are summarized where the exact
shape is enforced by a Pydantic schema rather than prose.

## 1. Pipeline Map

| Phase | Agent | Web access | Scores | Primary input | Primary output |
|---|---|---:|---:|---|---|
| A | Reconnaissance researcher | Yes | No | Short ruler brief and compact local-evidence summary | Initial notebook and source-claim ledger |
| B | Chapter researcher, repeated for 1B-8B | Yes | No | Recon summary, one compact chapter guide, resource index | Chapter source-claim units |
| C | Evidence reviewer | No | No | Accumulated notebook, ledger, required lenses | Defects, gaps, and continuation request |
| D | Research continuation | Yes | No | Reviewer brief in the same researcher session | Added or corrected evidence |
| E | Supervisor takeover, only after recoverable stalling | Yes | No | Review report and accumulated notebook | Completed permissive research handoff |
| F | Dossier formatter | No | No | Research handoff, ledger, compact local summary, guides | Strict cited dossier |
| G | Comparative chapter judge, one per chapter | No | Yes | All rulers' compact projections for one chapter and its full guide | One calibrated chapter score per ruler |

The producer/receiver rule applies throughout: producers should make outputs as complete
and accurate as possible; receivers should normalize and use imperfect but meaningful
inputs where possible. Missing evidence normally lowers confidence or triggers an
iteration. It causes terminal failure only when the remaining material is genuinely
insufficient to support the requested judgment.

## 2. General Evidence Collection

### 2.1 Reconnaissance researcher

Executable source:
[`dossier_notebook_prompt.py`](../../src/leaders_db/research/dossier_notebook_prompt.py)

The researcher receives:

- immutable ruler identity and period;
- a compact local briefing, not the full local evidence package;
- plain-language descriptions of the eight subject areas;
- the small machine-recovery appendix contract.

The researcher runs without project instructions, shell access, filesystem reads,
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

The prompt ends by requiring:

- a concise overview and evidence-environment assessment;
- compact atomic evidence records;
- separate later-retrospective evidence;
- separate lists for fully extracted evidence, opened corroboration, and uninspected
  leads;
- unresolved questions for deeper research;
- one machine-recoverable `SOURCE_CLAIM_JSON` line for each developed record.

### 2.2 Deep chapter researcher

Executable source:
[`chapter_research_sequence.py`](../../src/leaders_db/research/chapter_research_sequence.py)

This prompt is run once for each chapter. It receives only:

- the immutable ruler-period;
- that chapter's ten lens IDs;
- a bounded reconnaissance summary;
- the chapter guide's `Ten Evidence Lenses` and researcher-facing guidance;
- a compact index of already found resources.

Stable prompt:

> Research Chapter `{chapter_id}` for the same ruler-period. Search directly and do the
> substantive research; do not merely propose searches and do not score.
>
> 1. Read the ten evidence lenses and researcher plan together as one thematic inquiry.
> 2. Inspect the resource index, reuse useful sources, and do not treat it as exhaustive.
> 3. Search broadly across primary, independent, favorable, adverse, contrary, archival,
>    and relevant local-language sources.
> 4. Open promising underlying pages or reports and extract atomic claims with precise
>    locators, period fit, ruler attribution, contrary evidence, and lens mappings.
> 5. Separate inherited conditions, country context, subordinate conduct, ruler choices,
>    implementation, outcomes, allegations, and formal findings.
> 6. Continue until the chapter is reasonably saturated or explain the honest,
>    source-specific reason for a remaining gap.
>
> Preserve reusable sources and assign globally unique provisional IDs scoped to the
> chapter. Update the ledger manifest for every retained, rejected, or changed item.
> Report searches performed, sources opened, source-claim units retained, remaining
> gaps, and why further searching would or would not add value.

The chapter researcher is explicitly told that five to twenty defensible atomic
source-claim units is a normal target, not a quota or validity threshold.

## 3. The Eight Chapter Question Sets

These are overlapping evidence lenses, not eighty scores and not an arithmetic
checklist. The full guides add scope gates, exclusions, attribution rules, rubrics, and
chapter-specific calibration.

### 3.1 Chapter 1B — Nuclear and existential risk

Full guide:
[`1b-nuclear-existential-risk.md`](chapter-guides/1b-nuclear-existential-risk.md)

1. **1B.1:** Did the ruler seek to reduce nuclear or other existential risk, rather than increase prestige, leverage, or personal power through escalation?
2. **1B.2:** Did the ruler use nuclear rhetoric responsibly, avoiding reckless threats, brinkmanship, apocalyptic language, or normalization of nuclear use?
3. **1B.3:** Did the ruler strengthen command-and-control discipline, custody, safety, and accident-prevention safeguards?
4. **1B.4:** Did the ruler support arms-control, inspection, nonproliferation, disarmament, or de-escalation agreements in good faith?
5. **1B.5:** Did the ruler avoid using nuclear capability to shield conventional aggression, territorial coercion, or domestic repression?
6. **1B.6:** Did the ruler resist proliferation by allies, proxies, clients, or domestic factions when proliferation served short-term political interests?
7. **1B.7:** Did the ruler invest in risk-reducing expertise and institutions rather than surrounding nuclear/security decisions with loyalists or ideologues?
8. **1B.8:** In crisis moments, did the ruler de-escalate, communicate clearly, and preserve channels that reduce accidental war?
9. **1B.9:** Did the ruler handle dual-use technology, cyber, biological, AI, or other catastrophic-risk domains with precaution and transparency?
10. **1B.10:** Did the ruler leave the country's existential-risk posture safer or more dangerous than they inherited it?

Research emphasis: exposure and authority; inherited capability; doctrine and arsenal
change; command safety; treaties and inspections; threats and crises; proliferation;
expert appointments; catastrophic dual-use policy; end-of-period posture.

### 3.2 Chapter 2B — International peace

Full guide:
[`2b-international-peace.md`](chapter-guides/2b-international-peace.md)

1. **2B.1:** Did the ruler choose diplomacy, compromise, and de-escalation when credible peaceful alternatives existed, rather than treating force as the preferred first option?
2. **2B.2:** Did the ruler initiate, expand, prolong, or justify wars of choice, cross-border coercion, annexation, covert destabilization, or proxy conflict beyond defensive necessity?
3. **2B.3:** Did the ruler distinguish genuine defensive security needs from prestige, revenge, nationalism, manufactured threats, diversionary politics, or regime-survival motives?
4. **2B.4:** Did the ruler respect civilian protection, humanitarian law, prisoner treatment, necessity, and proportionality in military operations?
5. **2B.5:** Did the ruler restrain security forces, militias, allies, proxies, clients, and arms recipients from atrocities or destabilization, and accept responsibility for foreseeable proxy conduct?
6. **2B.6:** Did the ruler truthfully explain security threats to the public, or manipulate intelligence, fear, historical grievance, and misinformation to build support for conflict?
7. **2B.7:** Did the ruler pursue credible ceasefires, peace talks, confidence-building measures, lawful settlements, or post-conflict reconciliation when possible?
8. **2B.8:** Did the ruler use military spending and mobilization to meet real security needs, or to enrich networks, reward security elites, intimidate neighbors, or project personal strength?
9. **2B.9:** Did the ruler accept accountability for military failures, civilian harm, illegal conduct, and later evidence that contradicted the stated justification for conflict?
10. **2B.10:** Did the ruler leave regional/international relations more peaceful, stable, and lawful than they inherited them, accounting for inherited conflicts and external constraints?

Research emphasis: inherited conflicts and threats; initiation and alternatives;
objectives and justification; civilian conduct; proxies and arms recipients; public
claims; negotiations; military patronage; accountability; end-state change.

### 3.3 Chapter 3B — Domestic safety

Full guide:
[`3b-domestic-safety.md`](chapter-guides/3b-domestic-safety.md)

1. **3B.1:** Did the ruler protect residents from state violence, torture, disappearances, political imprisonment, extrajudicial killing, and arbitrary or exemplary punishment?
2. **3B.2:** Did the ruler prevent, punish, or tolerate abuse by police, military, intelligence services, prisons, militias, party enforcers, informal loyalists, or tolerated vigilantes?
3. **3B.3:** Did the ruler personally incite hatred, revenge, dehumanization, scapegoating, or violence against opponents, minorities, migrants, journalists, civil society, or religious/ethnic/sectarian/caste/racial groups?
4. **3B.4:** Did the ruler build systems for due process, complaint handling, civilian oversight, and independent investigation of abuse, including abuse by politically protected actors?
5. **3B.5:** Did the ruler use emergency powers, security laws, surveillance, anti-terror measures, or administrative controls narrowly and lawfully, or as tools for intimidation, collective punishment, and control?
6. **3B.6:** Did the ruler reduce domestic fear and insecurity without replacing criminal, communal, or insurgent violence with state terror or a broader political fear climate?
7. **3B.7:** Did the ruler protect women, children, minorities, and vulnerable groups from targeted violence, intergroup/religious/ethnic/sectarian/caste/racial violence, displacement, and systematic neglect?
8. **3B.8:** Did the ruler allow peaceful protest, dissent, and community organization without retaliation, chilling surveillance, arbitrary restrictions, or selective punishment?
9. **3B.9:** Did the ruler respond to domestic crises and spontaneous flare-ups with protection, restraint, and suppression of violence rather than incitement, tolerance, collective punishment, censorship, or militarized spectacle?
10. **3B.10:** Did the ruler leave citizens safer from political violence, intergroup violence, deaths/injuries/displacement, and preventable domestic insecurity than they inherited them?

Research emphasis: physical-integrity abuse; aligned actors; ruler rhetoric; oversight
and remedies; emergency and surveillance powers; state versus non-state fear;
vulnerable groups; protest treatment; crisis response; inherited-to-end safety.

### 3.4 Chapter 4B — Political freedom

Full guide:
[`4b-political-freedom.md`](chapter-guides/4b-political-freedom.md)

1. **4B.1** — Did the ruler genuinely accept that power should be contestable through free, fair, and meaningful elections?
2. **4B.2** — Did the ruler refrain from manipulating electoral rules, courts, media, election commissions, security forces, or public resources to entrench themselves?
3. **4B.3** — Did the ruler tolerate opposition victories, criticism, satire, investigative journalism, protest, and civil-society monitoring?
4. **4B.4** — Did the ruler strengthen independent courts, legislatures, audit bodies, local governments, and oversight institutions even when they constrained the ruler?
5. **4B.5** — Did the ruler avoid personality cults, intimidation, arbitrary loyalty tests, party capture, or politicization of neutral state institutions?
6. **4B.6** — Did the ruler protect independent media and information access instead of spreading propaganda, disinformation, censorship, or pressure on owners/journalists?
7. **4B.7** — Did the ruler protect political equality for minorities, women, excluded groups, opposition regions, and unpopular viewpoints?
8. **4B.8** — Did the ruler respect term limits, succession rules, coalition commitments, and constitutional transfer of power?
9. **4B.9** — Did the ruler use surveillance, digital controls, internet shutdowns, or administrative harassment to limit political freedom?
10. **4B.10** — Did the ruler leave political freedom and democratic resilience stronger or weaker than they inherited it?

Research emphasis: election contestability; entrenchment; opposition and civic space;
checks and oversight; institutional capture; media and information; political equality;
succession; digital controls; inherited-to-end trajectory.

### 3.5 Chapter 5B — Economic wellbeing

Full guide:
[`5b-economic-wellbeing.md`](chapter-guides/5b-economic-wellbeing.md)

1. **5B.1** — Did the ruler intend and act to create broad-based, sustainable prosperity rather than extract rents, buy loyalty, or maximize short-term popularity?
2. **5B.2** — Did the ruler appoint competent economic professionals and empower them, rather than loyalists, family members, business partners, or ideological yes-men?
3. **5B.3** — Did the ruler protect macroeconomic stability, fiscal responsibility, monetary credibility, and long-term investment conditions?
4. **5B.4** — Did the ruler create fair rules for entrepreneurship, competition, property rights, trade, investment, and job creation?
5. **5B.5** — Did the ruler resist corruption, favoritism, monopolies, oligarchic capture, and politically connected business privileges?
6. **5B.6** — Did the ruler invest in productivity foundations: infrastructure, education, health, technology, administrative capacity, and predictable regulation?
7. **5B.7** — Did the ruler make economic policy based on evidence and correction of mistakes, or on slogans, denial, patronage, and scapegoating?
8. **5B.8** — Did the ruler distribute economic gains fairly across regions, classes, genders, and groups rather than privileging regime supporters?
9. **5B.9** — Did the ruler manage shocks, inflation, unemployment, debt, sanctions, commodity changes, or crises with competence and honesty?
10. **5B.10** — Did the ruler leave the economy on a stronger trajectory than they inherited, accounting for external constraints?

Research emphasis: goals and appointments; macro stability; market rules; capture;
productivity investment; evidence and correction; distribution; shocks; inherited
trend; ruler-attributable implementation and outcomes.

### 3.6 Chapter 6B — Social wellbeing

Full guide:
[`6b-social-wellbeing.md`](chapter-guides/6b-social-wellbeing.md)

1. **6B.1** — Did the ruler treat human welfare as a core purpose of rule rather than as propaganda, patronage, or secondary concern?
2. **6B.2** — Did the ruler improve access to basic health, education, water, sanitation, housing, food security, and social protection?
3. **6B.3** — Did the ruler prioritize vulnerable groups, poor regions, children, elderly people, women, minorities, disabled people, and marginalized communities?
4. **6B.4** — Did the ruler fund and manage social services with competent professionals rather than patronage networks?
5. **6B.5** — Did the ruler use evidence, measurement, and transparent correction to improve service delivery?
6. **6B.6** — Did the ruler reduce avoidable suffering during crises such as pandemics, disasters, conflict displacement, famine, or economic shocks?
7. **6B.7** — Did the ruler avoid using welfare, permits, jobs, food, housing, or benefits as tools of political loyalty and punishment?
8. **6B.8** — Did the ruler protect dignity and equal opportunity, not only aggregate welfare numbers?
9. **6B.9** — Did the ruler build durable social institutions that would survive beyond their personal rule?
10. **6B.10** — Did the ruler leave ordinary people with better life chances than they inherited, accounting for baseline and constraints?

Research emphasis: welfare goals; access, coverage, quality, outcomes, and inequality;
vulnerable groups; professional delivery; evidence and correction; crises; political
allocation; dignity; durability; inherited-to-end life chances.

### 3.7 Chapter 7B — Personal integrity

Full guide:
[`7b-integrity.md`](chapter-guides/7b-integrity.md)

1. **7B.1** — Does the ruler habitually tell the truth to the public, legislature, courts, allies, and international partners, especially on matters where deception would protect power or reputation?
2. **7B.2** — Does the ruler admit errors, correct false claims, and allow truthful reporting, or do they knowingly mislead, double down, blame others, and punish truth-tellers?
3. **7B.3** — Does the ruler separate personal/family/business interests from state decisions, public contracts, licensing, regulation, law enforcement, and foreign policy?
4. **7B.4** — Does the ruler or close family profit from office through assets, contracts, monopolies, gifts, bribes, emoluments, insider access, opaque foundations, or hidden conflicts of interest?
5. **7B.5** — Does the ruler appoint competent professionals, or fill government with family, friends, cronies, donors, business associates, loyalists, and yes-men to protect personal power or self-dealing?
6. **7B.6** — Does the ruler tolerate independent investigation of their conduct, assets, campaign finance, conflicts of interest, associates, and concealed official decisions?
7. **7B.7** — Does the ruler use state power to conceal illegal, destructive, or self-serving activity, protect themselves from accountability, punish investigators, or neutralize courts, prosecutors, auditors, media, and whistleblowers?
8. **7B.8** — Does the ruler keep promises and respect formal commitments, or opportunistically reverse positions, manipulate public information, and conceal tradeoffs for personal advantage?
9. **7B.9** — Does the ruler avoid nepotism, favoritism, clientelism, and transactional politics in appointments, pardons, procurement, enforcement, and access to public information?
10. **7B.10** — Does the ruler model ethical standards that improve public trust, or normalize deliberate lying, impunity, self-dealing, conflicts of interest, and cynicism?

Research emphasis: Chapter 7B requires a personal ruler nexus. National corruption,
institutional weakness, associate conduct, or silence about scandal is context unless
connected to the ruler's own acts, benefit, knowledge, tolerance, concealment, remedy,
or accountability choices.

### 3.8 Chapter 8B — Effectiveness

Full guide:
[`8b-effectiveness.md`](chapter-guides/8b-effectiveness.md)

1. **8B.1** — Does the ruler articulate a clear governing ideology, strategic direction, or program, including explicit or revealed goals for power, policy, or regime control, that can be evaluated against later action?
2. **8B.2** — Does the ruler translate that program into concrete priorities, plans, budgets, appointments, timelines, institutions, and enforcement mechanisms?
3. **8B.3** — Does the ruler mobilize the state apparatus, party, military, bureaucracy, coalition, or ruling network effectively toward the chosen program and the ruler's own goals?
4. **8B.4** — Does the ruler select and empower people who are capable of executing the program, whether professionals, loyal operators, technocrats, organizers, security officials, or coercive administrators?
5. **8B.5** — Does the ruler maintain internal discipline, coordination, control, and follow-through across ministries, regions, territory, institutions, security forces, party structures, and implementing agencies?
6. **8B.6** — Does the ruler convert declarations into observable implementation and state reach rather than leaving goals as slogans, speeches, symbolic gestures, or propaganda only?
7. **8B.7** — Do outcome indicators move in the direction the ruler claimed or revealed they sought, after allowing for realistic lags, inherited conditions, and external constraints?
8. **8B.8** — When tactics fail, does the ruler adapt methods, replace ineffective implementers, reallocate resources, or otherwise correct course to keep advancing the program and maintaining effective control?
9. **8B.9** — Does the ruler manage crises, opposition, international relationships, and institutional resistance in a way that preserves or advances the regime's chosen objectives, durability, and influence, regardless of whether those objectives are morally good?
10. **8B.10** — By the end of the relevant period, is the ruler closer to achieving the stated or revealed ideological, policy, power-consolidation, or international-influence program than at the start, accounting for short-term wins, long-term durability, inherited conditions, and external shocks?

Research emphasis: freeze a broad portfolio of explicit or reliably revealed goals;
trace program, resources, appointments, mobilization, implementation, outcomes,
adaptation, and durability. The moral worth of the program is scored elsewhere.

## 4. Evidence Environment and Bias Questions

### 4.1 Twelve dossier evidence-environment questions

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

### 4.2 No-search evidence reviewer

Executable source:
[`evidence_review.py`](../../src/leaders_db/research/evidence_review.py)

The reviewer receives the immutable ruler-period, selected chapters and lenses, compact
local-evidence state, accumulated notebook, and ledger. It is instructed:

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
> null. Terminal insufficiency is reserved for identity failure or evidence that remains
> genuinely unusable after reasonable, documented attempts.

### 4.3 Research continuation

Executable source:
[`notebook_continuation.py`](../../src/leaders_db/research/notebook_continuation.py)

Stable prompt:

> Resume the same ruler research session for review round `{round_number}`. Search
> directly and iteratively for every selected chapter. Follow event- and source-specific
> leads; do not rely on one omnibus query or recent-news filters for historical work.
> Expand the candidate pool with broad, archive, source-family, adverse/contrary, and
> local-language queries. Open promising underlying sources and extract precise
> locators. Add traceable source-claim units, preserve contrary evidence and attribution
> limits, and explain when a gap cannot be improved or the chapter is saturated. Work
> only on the immutable ruler-period and do not score.

The complete structured reviewer brief is appended to that prompt.

### 4.4 Supervisor takeover

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

## 5. Dossier Formatter

Executable source:
[`dossier_prompt.py`](../../src/leaders_db/research/dossier_prompt.py)  
Output contract:
[`dossier_models.py`](../../src/leaders_db/research/dossier_models.py)

The formatter is a separate no-search, no-score agent. It receives:

- immutable ruler identity and period;
- applicable guide material;
- compact local evidence and derived-signal summary;
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
13. Does the structured-prior summary match the actual local package?
14. Does the dossier avoid statements that local priors were unavailable when they were supplied?
15. Does the handoff avoid instructions to the judge about what score or null decision to make?

The formatter must produce a dossier even when some fields need cautious normalization.
It should reject the whole handoff only when identity or traceability is genuinely
insufficient, not because exact wording, sequence, or coverage labels differ.

## 6. Comparative Chapter Judges

Executable shared prompt:
[`chapter_judge_prompt.py`](../../src/leaders_db/research/chapter_judge_prompt.py)  
Output contract:
[`chapter_judge_models.py`](../../src/leaders_db/research/chapter_judge_models.py)

There are eight judge jobs, one for each chapter. They do **not** receive eight unrelated
hardcoded prompts. Each receives the shared prompt below plus:

- the complete guide for its own chapter, including its ten questions and rubric;
- every eligible ruler's compact, hash-bound projection for that chapter;
- the unavailable-dossier manifest;
- run-scoped audit corrections, if any;
- a repair note when a previous candidate failed semantic validation.

The judge never receives the client scores and may not browse, search, read local files,
or add remembered facts.

### 6.1 Shared judge prompt

> Judge every dossier in the manifest using one common meter. The ten questions are
> overlapping evidence lenses, not ten scores and not an arithmetic checklist. Read
> each compact projection in full and use only its cited evidence and local-prior
> summaries.
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

### 6.2 Required judge bias assessment

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

### 6.3 Chapter-specific prompt received by each judge

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

### 6.4 Required judge output questions

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

## 7. Prompt Payload Boundaries

To keep model context useful rather than merely large:

- reconnaissance receives a compact local briefing, not the full local package;
- chapter research receives one chapter guide, a bounded recon summary, and a resource
  index, not the complete accumulated dossier;
- the reviewer receives the notebook and ledger because it must audit completeness but
  cannot browse;
- continuation receives only the reviewer brief in the same persistent research
  session;
- the formatter receives the complete research handoff because it must preserve and
  normalize it, but cannot research or score;
- each judge receives only its chapter projections across rulers, not eight full
  dossiers and not other chapters;
- client scores never enter researcher, formatter, or judge prompts.

## 8. Drift Review Checklist

When a prompt or guide changes:

1. update the executable prompt builder or authoritative chapter guide;
2. update its schema tests;
3. update this review reference in the same change;
4. verify all eighty lens IDs and texts against the guides;
5. verify the twelve evidence-environment questions and judge bias fields;
6. render representative prompts and confirm payload boundaries and token profiles;
7. run the affected prompt, schema, reviewer, formatter, and judge tests.
