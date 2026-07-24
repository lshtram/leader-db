# Comparative evaluation of paired chapter-research artifacts

This review is based only on the supplied artifacts. I did not search for additional information and did not score any ruler. Overall scores are the unweighted mean of the ten component scores.

## Summary

| Case | Artifact X | Artifact Y | Result | Prompt-change implication |
|---|---:|---:|---|---|
| Joe Biden — 6B | 9.0 | 9.0 | Tie | No wholesale prompt change; combine Y’s domain breadth with X’s cleaner evidence accounting |
| Vladimir Putin — 2B | 8.3 | 9.1 | Y | Yes; Y’s prompt produced materially better baseline, strategic-choice, and end-state coverage |
| Félix Tshisekedi — 3B | 8.7 | 8.9 | Y, narrowly | Supports refinement, not replacement; preserve X’s source diversity and operational ledger discipline |

---

# 1. Joe Biden — Chapter 6B

## Component scores

| Criterion | X | Y |
|---|---:|---:|
| 1. Material coverage of ten questions | 8.4 | 9.3 |
| 2. Source authority, independence, diversity | 9.0 | 9.0 |
| 3. Underlying inspection and stable locators | 8.8 | 9.2 |
| 4. Precision, period fit, retrospective separation | 9.1 | 9.3 |
| 5. Attribution, authority, baseline, shocks | 9.2 | 9.3 |
| 6. Favorable/adverse/contrary/bias balance | 9.0 | 9.4 |
| 7. Facts, repetition, allegations, findings | 9.2 | 9.0 |
| 8. Gaps, rejections, blockers | 9.5 | 9.2 |
| 9. Atomic records and machine appendix | 9.3 | 8.4 |
| 10. Efficiency | 8.6 | 7.6 |
| **Overall** | **9.0** | **9.0** |

## Verdict

**Tie.** Y is the stronger human-readable research dossier; X is the stronger normalized evidence package. Their strengths are complementary, and the small differences do not justify replacing one prompt with the other.

## Artifact X

### Strengths

- Its machine records are consistently structured and genuinely reusable. Each record usually contains a claim, precise locator, period-fit statement, calibrated attribution, contrary evidence, and a deduplication-oriented canonical key.
- It handles prospective and retrospective evidence carefully. The IRA record explicitly distinguishes 2022 enactment from benefits beginning later. The CTC record is labeled inherited context rather than a 2022 outcome.
- It gives unusually good attribution treatment. The CMS enrollment record separates Biden-era subsidies and administration from the inherited ACA, state marketplaces, and household choices. Aggregate mortality, homelessness, and maternal-health outcomes receive appropriately low ruler attribution.
- Its source accounting is transparent: opened, accepted, rejected, blocked, reused, and duplicate records are separately identified.
- The Commonwealth Fund duplicate and the relationship between the two Census records are explicitly controlled.
- Its residual-gap discussion is honest, especially the absence of affirmative evidence for 6B.7 and the distinction between “no verified abuse found” and proof that no abuse occurred.

### Defects

- Coverage is concentrated in health, nutrition, poverty, housing, and pandemic programs. It acknowledges but does not remedy thin treatment of education, water and sanitation, disability services, childcare, and long-term care.
- Several records add relatively little distinct analytical value. The adult and young-child vaccination records deepen distributional detail but partly repeat the established “targeted access with persistent disparities” fact pattern.
- Some locators remain hybrid or weakly normalized, such as “report landing page lines …; report Summary and Tables” or “Fast Facts and What GAO Found.”
- The record set slightly overrepresents federal administrative and audit sources. The Commonwealth Fund is the main clearly independent nongovernmental outcome source.
- The 2025 SNAP publication is valid retrospective evidence about FY2022, but its late publication needs especially careful downstream handling.

## Artifact Y

### Strengths

- It materially broadens the substantive domain coverage. The NAEP learning-loss record addresses education; EPA obligations address water infrastructure; the PACT Act addresses veterans and disability-related protection; the formula-shortage record adds childcare and regulatory preparedness.
- It pairs favorable intervention evidence with adverse realized outcomes particularly well: insurance coverage versus underinsurance, nutrition programs versus rising food insecurity, rental aid versus oversight failures, and mortality recovery versus persistent racial disparities.
- It clearly separates statutory creation, administrative obligation, and realized welfare outcomes. The EPA record does not mistake obligated funds for completed pipe replacement, and the IRA and PACT records do not convert later uptake into 2022 delivery.
- The cross-lens synthesis is decision-useful and identifies precisely which lenses are strong and which remain thin.
- Its rejection rules are sensible: advocacy materials, derivative reporting, generic development priors, and later totals presented as contemporaneous outcomes were excluded.

### Defects

- The artifact is substantially more voluminous, with narrative entries followed by a nearly complete repetition in JSON. This lowers efficiency without adding equivalent research value.
- Some machine records are not atomic:

  - The CMS record joins Marketplace administrative enrollment and a separate ASPE/NHIS uninsured-rate result under one ID.
  - The formula record combines GAO findings, executive emergency measures, legislation, and a later HHS OIG conclusion.
  - The homelessness record combines a point-in-time count with an inferred bed-capacity gap.
- The machine appendix sometimes gives only one URL for a multi-source claim. That impairs stable provenance even where the prose lists both sources.
- Its canonical fact keys are readable slugs but less collision-resistant and less provenance-specific than X’s URL-and-locator keys.
- A few lens mappings are overinclusive. For example, Marketplace enrollment alone is weak direct evidence for professional administration under 6B.4 unless supported by process or audit evidence.
- The later PACT implementation figures are properly labeled, but their inclusion adds complexity to a record whose central target-year fact is statutory eligibility expansion.

## Should the prompt change?

No wholesale change is justified because the aggregate result is effectively tied. A production prompt should combine the best features:

- Require Y’s explicit domain-gap scan across health, education, housing, nutrition, water, disability, childcare, and long-term care.
- Retain X’s append-ready, one-claim-per-record discipline.
- Require every multi-source claim to be split into separate evidence records or to carry a locator and URL for every contributing source.
- Avoid duplicating the full narrative in the machine appendix unless the narrative adds synthesis unavailable in the structured fields.

## Features from each artifact worth preserving

From X:

- deterministic merge payload;
- duplicate accounting;
- explicit inspected/rejected/blocked counts;
- URL-and-locator canonical keys;
- careful context versus final-evidence disposition.

From Y:

- broader domain checklist;
- stronger cross-domain synthesis;
- explicit prospective-versus-realized distinctions;
- dedicated uninspected-lead and rejected-source sections.

---

# 2. Vladimir Putin — Chapter 2B

## Component scores

| Criterion | X | Y |
|---|---:|---:|
| 1. Material coverage of ten questions | 7.8 | 9.5 |
| 2. Source authority, independence, diversity | 8.4 | 9.2 |
| 3. Underlying inspection and stable locators | 8.0 | 9.2 |
| 4. Precision, period fit, retrospective separation | 8.1 | 9.4 |
| 5. Attribution, authority, baseline, shocks | 8.2 | 9.5 |
| 6. Favorable/adverse/contrary/bias balance | 8.0 | 9.4 |
| 7. Facts, repetition, allegations, findings | 8.4 | 9.2 |
| 8. Gaps, rejections, blockers | 9.1 | 9.2 |
| 9. Atomic records and machine appendix | 9.0 | 8.8 |
| 10. Efficiency | 8.8 | 8.0 |
| **Overall** | **8.3** | **9.1** |

## Verdict

**Artifact Y is materially better.** The difference is large enough to justify changing the prompt or adopting the prompt features responsible for Y’s stronger research design.

## Artifact X

### Strengths

- It uses high-authority sources for the central legal and humanitarian record: UN votes, OHCHR investigations, ICRC operational statements, Putin’s own mobilization speech, and SIPRI expenditure estimates.
- Its ICRC records are carefully calibrated. They do not assign exclusive responsibility where the ICRC itself did not do so.
- The Putin mobilization record properly treats the Kremlin speech as primary evidence of orders and rationale, not proof that its threat claims were true.
- It distinguishes state-level attribution from Putin’s personal criminal or operational responsibility.
- Its accounting of inaccessible material is candid and does not promote search snippets or unopened leads into evidence.
- The JSON records are concise and generally atomic.

### Defects

- It lacks a sufficiently developed inherited baseline. Mentioning Minsk and other diplomatic mechanisms does not substitute for evidence about pre-invasion conflict intensity and whether a nationwide emergency existed.
- The central invasion decision is not represented by a dedicated record of Putin’s 24 February address. That is a major omission for ruler attribution, threat narrative, and strategic alternatives.
- It relies on research-accounting references to reused ICJ, OHCHR Commission, grain, and Treasury records that are not actually reproduced in the artifact. A downstream reader cannot fully evaluate or reuse what is merely named in the accounting section.
- It omits several material facts developed by Y:

  - continued operations after the ICJ suspension order;
  - the energy-infrastructure campaign;
  - year-end displacement;
  - NATO-enlargement consequences;
  - later ICC ruler-specific attribution;
  - broader patterns of violations beyond selected northern killings.
- The 2025 Associated Press chronology is a weak choice for 2022 negotiations when contemporaneous analysis, original reporting, draft documents, or institutional records could provide more precise evidence. It is correctly labeled context, but it adds limited value.
- Three separate UN annexation-related records partly repeat the same underlying fact pattern. The General Assembly annexation resolution is material; the Secretary-General statement and Security Council meeting add more institutional reaction than independent underlying fact.
- Russian rationales are recorded, but the artifact does not inspect them as deeply as Y does. “Russia claimed” is not equivalent to reconstructing the inherited threat environment and testing necessity.
- Favorable evidence is relatively thin and mostly appears in contrary-evidence fields rather than developed records.

## Artifact Y

### Strengths

- It constructs the correct causal sequence:

  1. inherited Donbas conflict and available diplomatic channels;
  2. Putin’s direct invasion decision and stated rationale;
  3. international legal and political rejection;
  4. continued war after the ICJ order;
  5. battlefield and detention abuses;
  6. limited diplomacy and humanitarian cooperation;
  7. mobilization and annexation;
  8. humanitarian and regional-security end state.
- The inherited-baseline record is especially valuable. It acknowledges serious ceasefire violations while noting lower civilian harm immediately before the invasion. That directly addresses necessity without pretending the inherited situation was peaceful.
- Ruler attribution is excellent. Strategic choices are attributed directly to Putin, while individual killings, detention-access decisions, and tactical violations receive more cautious institutional attribution.
- It preserves favorable and contrary evidence: the grain agreement, POW exchange, serious negotiations, Russia’s security claims, Ukrainian violations, and the genuine wartime need for manpower and matériel.
- It carefully distinguishes legal stages:

  - General Assembly political determination;
  - binding ICJ provisional measures without final merits resolution;
  - OHCHR or commission findings;
  - ICC reasonable-grounds warrant rather than conviction.
- Retrospective evidence is explicitly labeled. The 2023 Commission report and ICC warrant are not presented as contemporaneous 2022 judgments.
- It rejects strong but unsupported versions of the “completed peace deal blocked by the West” claim.
- The end-state evidence adds analytical value rather than mere volume: displacement and Nordic NATO applications bear directly on humanitarian and strategic consequences.

### Defects

- Several records remain composites rather than atomic units:

  - the negotiation record joins SWP analysis with anonymous-source Reuters reporting;
  - the POW record combines denied access with a separate exchange;
  - the mobilization record combines Putin’s order with SIPRI expenditure;
  - the end-state record combines UNHCR displacement with NATO enlargement.
- The statement that Russia continued operations after the ICJ order is clear, but the machine record’s only URL is the order itself. Continued operations should have its own independently localized evidence or be framed as an undisputed linked fact with a second source.
- The direct Kremlin source for the 24 February address is described but not linked in the main record; the machine record points to the ICJ instead.
- Reuters accessed through a republication is less stable than an original wire-service URL or archived copy.
- The artifact is long and repeats substantial narrative content in JSON.
- NATO is correctly treated as interested, but the causal formulation around strategic “failure” should remain an inference, not a source finding.
- The ICC record is highly valuable, yet it must remain segregated in downstream processing as later ruler-specific legal evidence, not a 2022 adjudicated fact.

## Should the prompt change?

Yes. Y’s improvement is not simply a matter of length. It reflects a better research architecture:

- mandatory inherited-baseline evidence;
- direct ruler-decision evidence;
- explicit reconstruction of peaceful alternatives;
- separate strategic, operational, legal, and end-state records;
- affirmative search for bounded cooperation and contrary facts;
- legal-status labeling for allegations, findings, provisional orders, warrants, and judgments.

The prompt should adopt those requirements while adding a strict atomicity rule to reduce Y’s composite records and duplicated volume.

## Valuable X features to preserve

- More compact appendix records.
- Strong operational caution in the ICRC entries.
- Explicit access-failure accounting.
- Search and rejection counts.
- Clear acknowledgment that aggregate military spending does not prove patronage or personal enrichment.
- Direct Russian-language Kremlin sourcing.

---

# 3. Félix Tshisekedi — Chapter 3B

## Component scores

| Criterion | X | Y |
|---|---:|---:|
| 1. Material coverage of ten questions | 8.5 | 9.3 |
| 2. Source authority, independence, diversity | 8.3 | 8.8 |
| 3. Underlying inspection and stable locators | 8.1 | 9.0 |
| 4. Precision, period fit, retrospective separation | 8.7 | 9.1 |
| 5. Attribution, authority, baseline, shocks | 8.4 | 9.3 |
| 6. Favorable/adverse/contrary/bias balance | 8.7 | 9.0 |
| 7. Facts, repetition, allegations, findings | 8.5 | 8.9 |
| 8. Gaps, rejections, blockers | 9.2 | 9.1 |
| 9. Atomic records and machine appendix | 9.1 | 8.7 |
| 10. Efficiency | 9.0 | 7.8 |
| **Overall** | **8.7** | **8.9** |

## Verdict

**Artifact Y is better, but only narrowly.** It provides deeper ruler-attribution analysis and stronger coverage of torture, detention, prison conditions, security-force alliances, and the enacted reparations law. The difference supports prompt refinement, not wholesale replacement.

## Artifact X

### Strengths

- It is compact, well structured, and economical. Ten records cover all lenses without excessive narrative repetition.
- It offers strong source diversity: UN monitoring, Amnesty, HRW, CPJ, the U.S. State Department, the DRC Presidency, local reporting, and an adverse Rwandan government statement.
- It preserves favorable and adverse facts within the same records:

  - state abuses alongside convictions;
  - protest repression alongside appellate correction;
  - security-force sexual violence alongside training and action plans;
  - proposed reparations alongside implementation uncertainty.
- The presidential anti-discrimination statement is useful direct evidence of Tshisekedi’s personal position and correctly receives only medium source confidence as evidence of implementation.
- The Rwandan statement is responsibly demoted to context and explicitly identified as an interested-party allegation.
- The state-of-siege record avoids a causal overclaim: the worsening death comparison contradicts effectiveness but does not prove that emergency rule caused the deterioration.
- Its residual gaps are unusually concrete, including final judgment status, sentence execution, victim compensation, command responsibility, and authenticated incitement transcripts.
- The manifest fallback is operationally excellent and protects the cumulative ledger.

### Defects

- Several central patterns are fragmented across summary records rather than directly extracted from the strongest underlying source. The torture system, inaccessible intelligence detention, prison deaths, and politically salient detentions are less developed than in Y.
- Two State Department records largely reproduce UN-derived evidence. The artifact acknowledges the dependence, but the accepted-organization count may overstate effective source independence.
- The direct presidential anti-discrimination statement is important but does not materially answer whether officials were disciplined or vulnerable communities were protected.
- The Rwandan allegation contributes little without named speakers or independently verified incidents. It is proper context but weak substantive evidence.
- The proposed victim-protection legislation record stops short of determining that the law was actually promulgated on 26 December; Y supplies the enacted legal text.
- The journalist record is precise but comparatively narrow. It adds a valid incident without establishing a broader national pattern or remedy.
- The Chebeya case concerns an inherited 2010 murder. Its 2022 appellate result is relevant to remedy, but it should not carry much weight as evidence of current-period perpetration.
- The artifact does not sufficiently reconstruct detention conditions, torture prevention, senior-level accountability, or cooperation with abusive armed groups.
- Its attribution framework is sensible but less developed than Y’s distinction among presidential policy, nationally controlled services, military governors, local police, armed groups, and foreign intervention.

## Artifact Y

### Strengths

- It identifies the strongest ruler-specific nexus: Tshisekedi’s continuation of the state of siege, appointment framework, and capacity to narrow or terminate it.
- It distinguishes inherited institutional abuse from target-year conduct. The torture record clearly states that its 2019–April 2022 window is not a 2022-only statistic.
- It develops multiple undercovered physical-safety domains:

  - lethal protest policing;
  - torture and inaccessible intelligence detention;
  - arbitrary and incommunicado detention;
  - prison deaths and extreme overcrowding;
  - child detention and sexual violence;
  - cooperation with abusive armed groups.
- It is careful about external shocks and limited state capacity. M23, Rwandan support, ADF, CODECO, and roughly 120 armed groups are treated as material constraints without erasing government responsibilities.
- The reparations-law record is a strong favorable institutional fact with direct ruler attribution and excellent temporal calibration: promulgation is credited, but no 2022 implementation outcome is inferred.
- It correctly treats conviction totals as meaningful but insufficient. It identifies missing denominators, seniority, finality, sentence execution, and victim remedies.
- The Mumbere Ushindi record distinguishes incitement by local officials from personal presidential incitement.
- It gives monitoring access and reporting bias serious attention, especially for ANR, military-intelligence, Republican Guard, and conflict-area sites.

### Defects

- The dossier is significantly less efficient. The narrative is long and then repeated in the machine appendix.
- It leans heavily on HRW and the U.S. State Department. Some apparent corroboration is dependent because the State Department report itself synthesizes UN and NGO reporting.
- Several claims within a single record could be split:

  - state-of-siege legal design, repression incidents, and security outcomes;
  - arbitrary detention generally, the Beya case, the Kabund case, and the Boende journalists;
  - child detention, child casualties, sexual violence, and preventive action plans;
  - conflict deaths, displacement, UCDP intensity, demobilization failure, and regional diplomacy.
- The inference that lack of an identified investigation supports ruler attribution is useful but should remain explicitly framed as missing remedy evidence, not proof that no investigation occurred.
- The FARDC–Guidon cooperation record rests primarily on an annual HRW synthesis plus a secondary summary of UN Group of Experts findings. Direct inspection of the underlying UN report would strengthen it.
- The legal-text source is Leganet rather than the official gazette. The artifact discloses this, but stable official publication remains preferable.
- The full-year conviction total from Actualité.cd is valuable but was not directly inspected in the machine appendix’s main record; the artifact appropriately flags the underlying annual UNJHRO report as missing.
- Some broad claims—such as impunity being the “dominant pattern”—are well supported qualitatively but lack a national denominator and should remain synthesis rather than machine fact.

## Should the prompt change?

The difference supports a targeted refinement:

- Require an explicit ruler-authority map before evidence collection.
- Require separate treatment of inherited baseline, ruler-maintained institutions, target-year incidents, remedial response, and external armed constraints.
- Require a search for closed or inaccessible detention systems and reporting-selection bias.
- Require direct legal-text inspection for enacted institutional reforms.
- Preserve a strict volume or atomicity constraint so the deeper analysis does not become repetitive.

## Valuable X features to preserve

- Direct presidential rhetoric evidence.
- CPJ’s named journalist incident.
- The Chebeya appellate-accountability record.
- Explicit treatment of adverse foreign-government claims as interested allegations.
- Superior research accounting and deterministic manifest merge instructions.
- More concise, atomic JSON records.
- More varied organizational sources.

---

# Overall recommendation

The results favor the prompt behind Y, but not uniformly:

- In the Putin case, Y is decisively superior because it reconstructs the inherited baseline, direct ruler decision, legal restraint, alternative diplomacy, escalation, and end state.
- In the Tshisekedi case, Y is modestly superior because it finds stronger institutional and ruler-attribution evidence.
- In the Biden case, Y’s wider substantive coverage is offset by X’s cleaner atomic records, duplicate control, and efficiency.

The production prompt should therefore adopt Y’s research architecture while preserving X’s evidence-engineering discipline.

Recommended production requirements:

1. Begin with an explicit authority, inherited-baseline, and external-shock map.
2. Scan every chapter question and every major substantive domain before declaring saturation.
3. Require favorable, adverse, contrary, and reporting-bias evidence as separate search obligations.
4. Distinguish contemporaneous facts from later findings, provisional orders, warrants, audits, and implementation results.
5. Enforce one material underlying fact per machine record.
6. Require one stable URL and locator for every source contributing to a record.
7. Report source dependence, not just publisher counts.
8. Separate inspected evidence, corroboration, unopened leads, rejected materials, and access blockers.
9. Avoid duplicating the full prose dossier in the machine appendix.
10. Preserve deterministic ledger-merge and duplicate-control fields.

## Production promotion

**More cases are needed before production promotion.** Three cases reveal a consistent advantage for Y’s depth but also expose a recurring atomicity and efficiency weakness. The sample is too small and chapter-specific to establish that the prompt generalizes across:

- low-information or closed regimes;
- peaceful cases where absence evidence is central;
- earlier historical periods;
- chapters dominated by economic or institutional evidence rather than conflict or welfare;
- cases with sparse local-language material;
- cases where the ruler has weak practical authority.

A reasonable next gate is **at least six additional paired cases**, distributed across multiple chapters and evidence environments. Promotion should depend on Y-style prompts maintaining their coverage and attribution advantage after imposing X-style atomicity, provenance, and volume constraints.