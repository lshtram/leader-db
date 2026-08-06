# Comparative evaluation

Scores assess the research artifacts only. Overall scores are the arithmetic mean of the ten components; they are not ruler or chapter scores.

## Joe Biden — Chapter 6B

| Component | Artifact X | Artifact Y |
|---|---:|---:|
| 1. Ten-question coverage | 9.2 | 8.6 |
| 2. Source authority, independence, diversity | 9.0 | 8.7 |
| 3. Underlying inspection and locators | 9.0 | 8.6 |
| 4. Precision, period fit, retrospective separation | 9.2 | 8.8 |
| 5. Attribution, authority, baseline, shocks | 9.3 | 8.8 |
| 6. Evidentiary and reporting-bias balance | 9.1 | 8.8 |
| 7. Fact, repetition, allegation, finding distinctions | 9.1 | 8.7 |
| 8. Gaps, rejections, and blockers | 9.2 | 9.1 |
| 9. Atomic-record and appendix reusability | 9.1 | 9.2 |
| 10. Efficiency | 7.8 | 8.3 |
| **Overall** | **8.9** | **8.8** |

**Better artifact: X, narrowly.**

### Why X is better

X provides the more complete substantive map of the chapter. It reaches important domains that Y leaves thin or absent:

- Education through the 2022 NAEP learning-loss record.
- Water infrastructure through EPA obligations and initial state grants.
- Veterans’ welfare through the PACT Act.
- Regulatory crisis performance through the infant-formula episode.
- Shelter capacity, not merely the homelessness count.
- Concrete institutional durability across the IRA, PACT Act, water appropriations, rental aid, and formula legislation.

Its attribution discipline is particularly strong. It repeatedly distinguishes presidential action from congressional authority, inherited ACA or ERA structures, state administration, private-sector failures, inflation, viral evolution, and Federal Reserve policy. The NAEP record is correctly treated as important welfare evidence but weak presidential-attribution evidence. The IRA is correctly classified as a 2022 institutional act whose principal household effects began later.

X also makes unusually good use of contrary evidence inside individual records. For example, the vaccine-equity record preserves both targeted federal design and continuing underrepresentation; rental assistance preserves both likely eviction prevention and serious Treasury oversight weaknesses.

### Defects in X

- It is somewhat overproduced. Fourteen full narrative records followed by fourteen largely duplicative JSON records impose substantial reading and processing cost.
- Some records are broader welfare context rather than strong evidence of Biden’s conduct. Homelessness, maternal mortality, and aggregate mortality are useful baselines but have low ruler attribution.
- A few claims combine multiple sources or facts under one atomic record. The formula-shortage record combines GAO, later HHS OIG findings, emergency measures, and legislation; the CMS record combines administrative enrollment with an ASPE uninsured-rate estimate.
- The HUD shelter “gap” comparison risks implying direct commensurability between the PIT population and different bed-inventory categories. X notes limitations, but this derived comparison is less secure than the underlying count.
- Lens 6B.7 remains essentially uncovered. X is honest about that, but its very high overall coverage should not obscure the gap.

### Valuable features from Y to preserve

Y is more operationally transparent:

- It gives explicit discovery, opening, acceptance, reuse, rejection, duplication, and access-blocker accounting.
- It clearly identifies records as `final_evidence` or `context`.
- It includes a compact lens-by-lens coverage table.
- Its duplicate-control note is useful and concrete.
- It adds material SNAP evidence, including the Thrifty Food Plan audit and the vulnerable-household profile.
- It adds unemployment-assistance delivery disparities and two targeted vaccination-uptake records.
- Its canonical keys include source and locator information, which helps deterministic reconciliation even if semantic fact keys would be better for cross-source deduplication.

Y’s main substantive weakness is allocation. It spends three records on vaccination and several on nutrition while leaving education, drinking water, veterans, disability, long-term care, and childcare relatively thin. The 2021 CTC record and earlier PUA experience are correctly labeled context, but they consume capacity that could have filled direct 2022 domain gaps.

### Prompt-change judgment

The difference alone is **not large enough to justify a wholesale prompt replacement**. X is substantively superior, while Y is slightly more efficient and marginally stronger as a documented merge payload.

The best change would be incremental: retain the prompt behavior that produced X’s domain breadth, attribution analysis, and integrated synthesis, while requiring Y’s explicit research accounting, `context`/`final_evidence` distinction, and duplicate ledger.

---

## Vladimir Putin — Chapter 2B

| Component | Artifact X | Artifact Y |
|---|---:|---:|
| 1. Ten-question coverage | 9.6 | 8.3 |
| 2. Source authority, independence, diversity | 9.3 | 8.4 |
| 3. Underlying inspection and locators | 9.2 | 7.9 |
| 4. Precision, period fit, retrospective separation | 9.2 | 8.2 |
| 5. Attribution, authority, baseline, shocks | 9.5 | 8.4 |
| 6. Evidentiary and reporting-bias balance | 9.2 | 8.5 |
| 7. Fact, repetition, allegation, finding distinctions | 9.3 | 8.4 |
| 8. Gaps, rejections, and blockers | 9.3 | 8.8 |
| 9. Atomic-record and appendix reusability | 9.1 | 8.5 |
| 10. Efficiency | 8.0 | 8.4 |
| **Overall** | **9.2** | **8.4** |

**Better artifact: X, clearly.**

### Why X is better

X reconstructs the chapter’s necessary causal and chronological structure:

1. An active but lower-intensity inherited Donbas conflict.
2. Putin’s direct initiation and stated justification of the invasion.
3. International institutional rejection.
4. Continued operations after the ICJ order.
5. Civilian killings and broader war-crime findings.
6. The energy-infrastructure campaign.
7. Humanitarian access and POW treatment.
8. Negotiations and bounded cooperation.
9. Mobilization and spending escalation.
10. Attempted annexation.
11. Humanitarian and regional-security deterioration.
12. Later ruler-specific ICC action.

That sequence allows evaluation of alternatives, escalation, restraint, civilian protection, diplomacy, accountability, and end-state consequences without confusing them.

The artifact is also exemplary on evidentiary status:

- Putin’s speech is evidence of his decision and claims, not proof that those claims were true.
- UN General Assembly resolutions are political institutional determinations, not criminal judgments.
- The ICJ order is binding provisional relief, not a final decision on every merits issue.
- The ICC warrant is a reasonable-grounds determination, not a conviction.
- UN findings about Russian forces are not automatically converted into proof that Putin ordered every incident.
- Anonymous Reuters reporting about the Kozak proposal is retained but carefully qualified.
- Later investigations are explicitly labeled retrospective.

X also preserves meaningful favorable evidence: the grain initiative, the prisoner exchange, serious negotiations, Russian security claims, Ukrainian violations documented by the UN, and genuine wartime resource needs. Those facts are not allowed to erase the much stronger contrary record.

### Defects in X

- It is long and partly duplicative: the prose records and machine appendix repeat almost all content.
- Some records aggregate more than one independent fact. Displacement and Nordic NATO enlargement should ideally be separate atomic units.
- The POW record combines an ICRC access failure with a separate UN-reported exchange.
- The energy record mixes contemporaneous casualties with a later legal characterization.
- NATO is appropriately caveated as interested, but Finland’s own official record would have been more independent for the policy-change rationale.
- X could have stated more explicitly which accepted records were newly opened versus reused from the supplied evidence environment.

### Defects in Y

Y’s largest problem is not merely having fewer records; it lacks several components necessary for a defensible chapter reconstruction:

- No developed pre-invasion baseline comparable to X’s OHCHR Donbas record.
- No full atomic record for Putin’s 24 February invasion order and its stated purposes.
- No developed record of the ICJ order, although it appears in the reuse accounting.
- No broad UN Commission record distinguishing patterns, individual incidents, and some Ukrainian violations.
- No energy-infrastructure campaign record.
- No displacement or regional-security end-state record.
- No later ruler-specific ICC record.
- Limited treatment of whether negotiations produced a completed or merely provisional settlement framework.

Its 2025 Associated Press chronology is a weak substitute for contemporaneous negotiation documents or a dedicated document-level analysis. Y labels it context, which is honest, but the locator “lines 1776–1779” is fragile and the source is temporally remote.

The accounting also says five supplied records were reopened and reused, but those records are not reproduced as normalized appendices here. Consequently, the visible artifact is not fully self-contained.

### Valuable features from Y to preserve

- The Mariupol humanitarian-access record adds a material fact absent from X.
- The separate Olenivka record is more atomic than X’s combined POW record.
- The Security Council veto record adds institutional-accountability detail and preserves Brazil’s and China’s procedural or diplomatic reservations.
- Y carefully distinguishes allegations made by Rwanda, Russia, or other interested governments from established findings.
- Its access-blocker accounting is unusually specific and correctly states that search-indexed content was not accepted where the underlying source could not be localized.
- It is somewhat more concise and avoids reproducing every corroborative lead in narrative form.

### Prompt-change judgment

This difference **does justify changing the prompt or preferring the prompt that produced X** before production use. X is not simply longer; it captures indispensable strategic decisions, baseline conditions, legal restraint, civilian consequences, diplomacy, attribution levels, and end-state effects that Y omits.

The change should preserve Y’s atomization of humanitarian incidents and its explicit opening/access audit.

---

## Félix Tshisekedi — Chapter 3B

| Component | Artifact X | Artifact Y |
|---|---:|---:|
| 1. Ten-question coverage | 9.2 | 8.7 |
| 2. Source authority, independence, diversity | 8.8 | 8.7 |
| 3. Underlying inspection and locators | 8.8 | 8.7 |
| 4. Precision, period fit, retrospective separation | 9.1 | 8.7 |
| 5. Attribution, authority, baseline, shocks | 9.3 | 8.8 |
| 6. Evidentiary and reporting-bias balance | 9.1 | 9.0 |
| 7. Fact, repetition, allegation, finding distinctions | 8.9 | 8.8 |
| 8. Gaps, rejections, and blockers | 9.2 | 8.9 |
| 9. Atomic-record and appendix reusability | 9.0 | 8.8 |
| 10. Efficiency | 8.0 | 8.5 |
| **Overall** | **8.9** | **8.8** |

**Better artifact: X, narrowly.**

### Why X is better

X presents the stronger institutional account. Its central organizing fact—the state of siege—is connected carefully to:

- Tshisekedi’s decree and appointment authority.
- Military and police replacement of civilian government.
- Military jurisdiction over civilians.
- Repeated extensions without a clear termination test.
- Repression of critics.
- Judicial backlog and prolonged detention.
- Failure to deliver the promised improvement in protection.

That produces a more useful ruler-level record than a collection of isolated abuses.

X also covers several material areas more deeply than Y:

- The multi-year OHCHR–MONUSCO torture investigation, with exact perpetrator and victim counts and explicit period warnings.
- Incommunicado intelligence detention and inaccessible facilities.
- Prison deaths, overcrowding, food and medical deprivation, and monitoring restrictions.
- Child detention and state-force violations.
- FARDC cooperation with an abusive armed-group leader.
- The enacted December 2022 reparations law, distinguished from later implementation.

Its attribution analysis is consistently calibrated. It assigns high attribution to the emergency framework and appointments, moderate attribution to nationally controlled institutions and failures of remedy, and lower attribution to individual battlefield or police abuses without presidential-order evidence. It also treats M23, Rwanda, ADF, CODECO, inherited institutional weakness, and limited state reach as genuine external or inherited constraints.

### Defects in X

- Several records are dense bundles rather than strictly atomic claims. The state-of-siege record combines legal structure, repression, court dysfunction, extensions, and comparative casualty outcomes.
- The State Department report supplies three separate records, but much of its information derives from UN or NGO reporting. X recognizes this, yet the appendix could encode underlying-source dependence more explicitly.
- The torture and children records cover mixed multi-year periods. They are labeled correctly, but they remain less probative of calendar-year change than direct 2022 records.
- The full-year conviction totals rely on an Actualité.cd summary of UNJHRO findings rather than the underlying annual report.
- Leganet is not the official gazette. The law’s existence is well supported, but the locator and provenance are less ideal than an authenticated official text.
- Like the Biden artifact, X duplicates extensive narrative analysis in its machine appendix.

### Valuable features from Y to preserve

Y contributes several facts that improve balance and attribution:

- Tshisekedi’s direct public statement opposing ethnic discrimination and profiling is valuable ruler-specific favorable evidence.
- The CPJ journalist case adds a precise incident and a prompt corrective release.
- The Chebeya–Bazana appellate convictions show accountability for a serious inherited case while preserving the unresolved senior-command allegation.
- The LUCHA appellate reversal is stronger corrective-mechanism evidence than raw conviction totals.
- The March–April MONUSCO report gives a compact contemporaneous comparison of armed-group abuses, state killings, and convictions.
- The adverse Rwandan statement is properly retained only as a low-to-medium-confidence allegation from an interested conflict party.
- Y’s explicit distinction between newly accepted and reused records is useful for ledger integrity.

Y’s main defects are that it treats late-2022 reparations measures as still proposed when X supplies the enacted law, and it gives less sustained treatment to torture, prisons, inaccessible intelligence detention, child detention, and abusive auxiliary cooperation. Its coverage is broad but somewhat flatter: the records do not synthesize the state-of-siege command structure and presidential responsibility as effectively as X.

### Prompt-change judgment

The small aggregate difference does **not justify replacing the prompt wholesale**. It does justify a targeted revision.

The preferred prompt should preserve X’s institutional synthesis and authority analysis while explicitly asking for Y’s ruler-specific favorable conduct, functioning corrective cases, and adverse-party allegations with source-interest labels.

---

# Overall recommendation

| Case | Better artifact | Margin | Prompt implication |
|---|---|---:|---|
| Biden 6B | X | Very small | Incremental revision only |
| Putin 2B | X | Material | Prefer or adopt the X-producing prompt |
| Tshisekedi 3B | X | Small | Incremental revision only |

Artifact X is the stronger research design across all three cases. Its advantage is not record count or prose length. It more reliably produces:

- A coherent inherited baseline.
- A ruler-authority model.
- Separation of direct decisions from institutional and incident-level attribution.
- Integration of favorable and adverse evidence.
- Careful separation of contemporaneous outcomes from later findings.
- Domain coverage guided by the chapter rather than by whichever source family was easiest to search.
- A defensible saturation assessment.

Artifact Y should not be discarded. Its strongest production features should be added to the X-producing prompt:

- Explicit counts for discovered, opened, blocked, accepted, reused, and rejected materials.
- A visible distinction between `final_evidence`, `context`, and unresolved leads.
- Identification of repeated underlying sources and prior ledger IDs.
- Smaller atomic records when two facts have different sources, dates, or attribution levels.
- Direct ruler statements and concrete corrective cases, not only adverse structural evidence.
- A deterministic append-only merge payload.
- Specific disclosure when a supposedly reused record is not reproduced in the visible artifact.

## Production promotion

**Do not promote after only these three cases.** The evidence favors the X-producing prompt, especially because of the decisive Putin result, but two of the three comparisons are close and the chapters differ substantially in source environment.

Run **at least three additional paired cases** before promotion:

- One low-information or highly access-blocked ruler-period.
- One non-conflict chapter where administrative outcomes dominate.
- One case with fragmented local-language evidence and weak institutional documentation.

Promotion should require the X advantage to persist without systematically increasing duplicate records or volume. If those cases confirm the pattern, promote the X-producing prompt with Y’s accounting, atomization, and ledger-integrity requirements incorporated.