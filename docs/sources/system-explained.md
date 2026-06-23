# Unified Source System — Plain-English Guide

This document explains the planned source system in non-technical language. It is
for future contributors, reviewers, and users who need to understand why the
project is being rebuilt around a unified source interface.

---

## 1. Why we are changing direction

The project has been a prototype. That was useful: it proved we can download or
stage data, parse many real datasets, write database rows, and run tests.

But the prototype grew one source at a time. Many sources work, but each has its
own shape. That makes the next stage harder: future research questions need a
single way to ask, “what evidence do we have for this country, year, leader, and
indicator?”

So we are starting a cleaner source system now, while the project is still early.
The old work is not thrown away. It becomes a reference and fallback. The new
work gets a stronger foundation.

---

## 2. The simple idea

Every source, no matter what kind of file or website it comes from, should behave
like this:

```text
Can I run?          -> check readiness
Read the source     -> read raw files or API cache
Normalize it        -> turn it into common evidence rows
Check it            -> validate fields, locators, warnings
Save it             -> write files and database rows
Explain it          -> write a manifest with provenance and attribution
Use it              -> research/scoring code queries the evidence
```

This means V-Dem, World Bank, PWT, Archigos, Wikidata, PDFs, manually staged
datasets, and future sources all follow the same pattern.

---

## 3. The main pieces

### Source adapter

A source adapter is the source-specific translator.

Examples:

- PWT adapter knows how to read PWT Excel files.
- World Bank adapter knows how to read API/cache JSON.
- Archigos adapter knows how to read leader-tenure rows.
- A PDF adapter would know how to extract rows or snippets from a report.

The adapter does **not** decide final scores. It only turns source material into
evidence.

### Source runner

The runner is the shared machine that calls every adapter in the same order.

It handles common rules:

- validate the output,
- write processed files,
- write database rows,
- make reruns idempotent,
- create manifests,
- enforce no silent stale data.

This keeps source adapters small and prevents each source from inventing its own
workflow.

### Normalized observation

A normalized observation is one evidence row in the common language of the
project.

It says things like:

- source: PWT,
- indicator: population,
- country: USA,
- year: 2019,
- value: 328 million,
- where it came from: sheet `Data`, row X, column `pop`,
- which adapter produced it,
- which warnings or quality flags apply.

Once evidence is normalized, later research code does not care if it came from
Excel, an API, or a PDF.

### Manifest

A manifest is the receipt for a source run.

It records:

- which source version was used,
- which raw files or API responses were read,
- which output files were written,
- how many observations were produced,
- what years/countries were covered,
- warnings,
- attribution and license text,
- hashes that help reproduce the run.

### Evidence repository

The evidence repository is how future scoring and research code asks questions.

Instead of calling 20 different source parsers, code asks:

```text
Give me all observations for Mexico, 2023, related to governance.
```

or:

```text
Show me all sources that support or contradict this ruler-year score.
```

---

## 4. Why the design is this way

### Because sources are very different

Some sources are spreadsheets. Some are APIs. Some are PDFs. Some are manually
downloaded. Some describe countries; some describe leaders; some describe wars;
some describe nuclear arsenals.

If every source exposes a different interface, every later research question
becomes custom code.

### Because auditability is the product

The project is not just trying to produce numbers. It must explain where numbers
came from and why they should or should not be trusted.

That is why every observation needs provenance and every run needs a manifest.

### Because missing data must be honest

If a source ends in 2019 and the user asks for 2023, the system must not quietly
reuse 2019. It should say: “this source has no 2023 data,” produce zero rows for
that year, and record a warning.

### Because the client matrix is not evidence

The client matrix is useful for comparison and validation, but it cannot count as
an independent source. The new system keeps that rule explicit.

---

## 5. Separation from the existing code

The current prototype code lives mainly under:

```text
src/leaders_db/ingest/
```

The new clean source system should live under:

```text
src/leaders_db/sources/
```

The old code is not deleted. It is legacy/reference code. It proves useful
source-specific logic and keeps current capabilities available while the new
system is built.

The rule going forward should be:

```text
New source infrastructure and new source migrations go into leaders_db.sources.
Old ingest code is kept stable and separate.
```

---

## 6. Should we move old code to legacy-src?

Maybe, but not as the first step.

There are two kinds of separation:

1. **Logical separation:** create the new `leaders_db.sources` subsystem and stop
   adding new source logic to old `ingest` modules.
2. **Physical separation:** move old prototype code to `legacy-src/` or
   `src/leaders_db_legacy/`.

Logical separation should happen first. It is safer and lets the new system grow
without breaking existing imports and tests.

Physical separation can happen later as a dedicated cleanup step. If we do it, it
should be one mechanical reviewed commit, not mixed with new architecture work.

Recommended path:

```text
Step 1: Add docs, requirements, and stubs for leaders_db.sources.
Step 2: Add contract tests for the new interface.
Step 3: Rebuild PWT in the new package.
Step 4: Rebuild Maddison and WDI/WGI.
Step 5: Add new CLI commands under `leaders-db sources ...`.
Step 6: Decide whether old code stays frozen or moves to legacy-src.
```

---

## 7. Which sources get the new interface?

All of them.

### Existing prototype sources to migrate

- `pwt`
- `maddison_project`
- `world_bank_wdi`
- `world_bank_wgi`
- `vdem`
- `transparency_cpi`
- `rsf_press_freedom`
- `bti`
- `archigos`
- `reign`
- `ucdp`
- `sipri_milex`
- `sipri_yearbook_ch7`
- `pts`
- `cirights`
- `undp_hdi`
- `who_gho_api`
- `fas`
- `wikidata_heads_of_state_government`
- `wikipedia_search_extract`

### Pending or future sources

- `polity_v`
- `leader_survival`
- `freedom_house`
- `imf_weo`
- `cow_mid`
- `nti`
- `sipri_arms_transfers`
- `iaea_safeguards`
- `iaea_additional_protocol_status`
- `unoda_treaties`
- `ctbto_treaty_status`
- `ctbto_nuclear_tests`
- `csis_missile_threat`
- `cns_nti_missile_launches`
- `world_bank_poverty_inequality_platform`
- `ilo_labor_statistics`
- `world_bank_global_findex`
- `world_inequality_database`
- `ucdp_external_support`
- `non_state_actor_dataset`
- `dangerous_companions_nags`
- `att_monitor`
- `acled`
- `nuclear_weapons_ban_monitor`
- `world_nuclear_association_profiles`
- `nti_country_profiles`
- `government_manifestos`
- `budget_execution_reports`
- `national_statistics_goal_indicators`
- `audit_oversight_reports`

### Aliases, subsets, retired candidates, or excluded candidates

- `acled_ucdp_osv` is currently a UCDP one-sided-violence subset, so the clean
  system should probably represent it as a UCDP observation family rather than a
  separate adapter.
- `chicago_aisd` is mentioned only as an auxiliary/retired violence candidate and
  should stay out of the active registry unless re-vetted.
- `cia_world_leaders` is retired and should stay excluded unless deliberately
  revived as a fallback/validation source.
- `political_terror_scale` is the descriptive source key for PTS. During the
  clean migration we should choose one canonical slug (`pts` or
  `political_terror_scale`) and keep the other as an alias.
- `world_bank_wdi_social` is a WDI subset, not a separate raw source.
- `vdem_governance` is a V-Dem subset, not a separate raw source.
- `world_bank_wgi_corruption` is a WGI subset, not a separate raw source.
- `vdem_corruption` is a V-Dem subset, not a separate raw source.

### Chronicle / curated / area sources

- `soviet_leaders_curated` should become a manual/curated leader-source adapter.
- `cshapes` should become a country-area source adapter, even if its first use is
  Chronicle.
- `icow_colonial` stays blocked until a working dependency-controller source is
  found.

### Special case

- `client_existing` may be represented only as validation-only data. It must not
  count as evidence.

---

## 8. What happens next

The next practical milestone is not to migrate every source immediately. It is to
define the foundation so migrations are consistent:

1. Write the architecture and requirements docs.
2. Add importable stubs for the new package.
3. Write contract tests that define what every source must do.
4. Implement one clean source adapter, likely PWT, without relying on legacy
   dispatch.
5. Migrate the remaining sources in priority order.

This lets the project keep the old achievements while building the real system on
a stronger base.
