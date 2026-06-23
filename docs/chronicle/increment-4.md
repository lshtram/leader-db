# Country-Year Chronicle — Increment 4 Plan

Date: 2026-06-21

Sub-project: **Country-Year Chronicle** (`cyc`)

Status: **planned**

## 1. Goal

Increment 4 defines and vets the source path for true
`controlled_area_km2` modeling. Increment 3 deliberately used the
conservative fallback:

```text
controlled_area_km2 = country_area_km2
```

with both `controlled_area_country_only` and
`controlled_area_not_modeled` flags. Increment 4 decides whether we can replace
that fallback for supported metropole-years without inventing colonial or
imperial mappings.

## 2. Working definition to review

Proposed definition:

> `controlled_area_km2` is the sum of the state's own country-area value plus
> the area of external territories for which the state is the documented
> sovereign, colonial administrator, dependency controller, protectorate power,
> mandate authority, or otherwise source-coded controlling state in that year.

This definition intentionally excludes unsourced informal influence, alliance
systems, trade zones, sphere-of-influence claims, and disputed military presence
unless the accepted source explicitly codes them as territorial control.

## 3. Relationship types

Initial included relationship types, if sourced:

- colony / colonial possession;
- dependency / overseas territory;
- protectorate;
- mandate / trust territory;
- formally administered external territory.

Initial excluded relationship types unless separately approved:

- military occupation not coded as territorial administration;
- informal empire / sphere of influence;
- client states;
- alliance blocs;
- disputed claims without administration;
- leased bases and small facilities.

## 4. Source candidates

| Candidate | What it could provide | Current status | Main risk |
|---|---|---|---|
| ICOW Colonial History | Colonial/dependency relationships by state/year | Needs URL recovery. The previously documented `http://www.paulhensel.org/icowcol/Data/colhist.zip` returned 404 on 2026-06-21. | Source availability and exact country-code join to CShapes. |
| COW Colonial/Dependency Contiguity | Colony/dependency relationships from 1816-2016 | Needs download and schema inspection. | May encode contiguity relationships rather than full controller-year ownership. |
| CShapes 2.x dependency attributes | Territory geometry / area for dependencies | Raw CShapes 2.0 is already staged for area. | Need confirm whether the CSV contains controller metadata; current Chronicle loader uses area and GW identity only. |
| From Empire to Nation-State dataset | Territory-year colonial/independence records | Candidate only. | License, availability, and join complexity unknown. |
| Curated empire tables | Direct metropole-year totals | Not accepted by default. | High risk of invented or unsourced mappings; use only if source is authoritative and attribution is clear. |

## 5. Join design to prove

The acceptable implementation path is:

1. Load a dependency-controller table with explicit `(controller, dependency,
   start_date, end_date)` or equivalent source-coded records.
2. Map controller and dependency identities to Chronicle ISO3 / historical-state
   identities with documented mapping tables.
3. For each requested `(controller_iso3, year)`:
   - keep `country_area_km2` from CShapes as-is;
   - find controlled dependencies active in that year;
   - look up each dependency's CShapes area for that year;
   - compute `controlled_area_km2 = country_area_km2 + sum(dependency_area_km2)`;
   - populate `controlled_area_note` with source and dependency count;
   - remove `controlled_area_country_only` only when at least one dependency area
     was actually summed.
4. If any join step fails, keep the Increment 3 country-only fallback and flag the
   row rather than guessing.

## 6. Proof examples

The design should include at least these examples before implementation:

- **GBR 1900 / 1930** — expected to have controlled dependencies if a colonial
  source is accepted.
- **FRA 1900 / 1930** — expected to have controlled dependencies if a colonial
  source is accepted.
- **NLD / PRT / ESP** — useful second-tier checks if the source covers them.
- **USA 2020** — should remain country-only unless territories are explicitly
  included by the accepted definition.
- **SUN / RUS** — must not inherit Russian Empire, Soviet bloc, Warsaw Pact, or
  informal influence as controlled area unless a source codes territorial
  administration.

## 7. Acceptance criteria

Increment 4 is complete when:

1. Controlled-area semantics are review-approved.
2. At least one dependency-controller source is accepted or rejected with evidence.
3. Source URLs, licenses, and attribution requirements are recorded in
   `docs/sources/registry.md` and `docs/sources/attributions.md` if a source is staged.
4. The implementation plan proves no client matrix, LLM, or hand-invented colony
   mappings are needed.
5. Reviewer approves the design before production `controlled_area_km2` behavior
   changes.

## 8. Non-goals

- No broad all-country expansion in this increment.
- No unsourced empire totals.
- No replacement of `country_area_km2`; controlled area is an additional field.
- No removal of missingness/proxy flags unless a source actually fills the field.
