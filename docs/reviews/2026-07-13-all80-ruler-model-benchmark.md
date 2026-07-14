# All-80-Lens Ruler Dossier Model Benchmark — 2026-07-13

## Scope

Two 2020 ruler-year cases were run across all 80 methodology lenses with one
ruler-level researcher session per model. The initial discovery packet was shared
across models; the parent could add one gap-driven search/model continuation.

- Nikol Pashinyan, Armenia (`ruler_year_id=10789`): comparatively well documented.
- Roosevelt Skerrit, Dominica (`ruler_year_id=8425`): deliberately sparse small-state case.
- Models: OpenAI Luna, OpenAI Terra, MiniMax M2.7, MiniMax M3.

Actual subscription/Coding Plan charges are not exposed. Dollar figures below are
official API-equivalent lower/upper ranges from `configs/research-pricing.yaml`.
Long-context application and cache-write volume are not observable, so exact cash
claims would be false. Search cost is included in each row's model-equivalent range.
Shared search IDs must be deduplicated when computing batch totals.

## Results

| Case/model | Publication | Input (cached) | Output | API-equivalent USD | Codex credits | Evidence / mappings | Assessment |
|---|---:|---:|---:|---:|---:|---:|---|
| Pashinyan / Luna | pass | 1,553,302 (1,319,936) | 29,382 | 0.552–1.122 | 13.54 | 14 / 97 | Broadest published dossier; 3 covered, 59 partial, 18 no evidence. |
| Pashinyan / Terra | pass | 1,037,631 (829,952) | 22,478 | 1.074–2.229 | 26.60 | 10 / 61 | Less evidence breadth but 33% fewer input tokens than Luna. |
| Pashinyan / M2.7 | fail | unknown | unknown | unknown | n/a | none | Repeated unsupported connector calls; stopped after no progress. |
| Pashinyan / M3 | format fail | 1,231,164 (963,698) | 29,022 | 0.178–0.391 | n/a | raw alternative artifact | Substantive material, but markdown-wrapped and incompatible structure. |
| Skerrit / Luna | integrity fail | 330,722 (254,976) | 9,935 | 0.166–0.335 | 4.02 | raw 3-item candidate | Cited an unapproved linked State Department PDF; exact-URL provenance gate held. |
| Skerrit / Terra | pass | 877,545 (709,120) | 15,944 | 0.848–1.776 | 20.94 | 6 / 22 | Appropriate sparse degradation: 1 covered, 17 partial, 57 no evidence, 5 not applicable. |
| Skerrit / M2.7 | fail | not exposed | not exposed | unknown | n/a | none | Connector isolation worked, but shell was unavailable and final generation stalled. |
| Skerrit / M3 | format fail | 647,907 (576,272) | 27,565 | 0.094–0.194 | n/a | prose claim of 11 items | Returned a 2.2 KB prose summary instead of the claimed JSON dossier. |

The shared/discovery cash-equivalent total was $0.015 for Pashinyan (one shared
initial plus Luna and Terra continuations) and $0.010 for Skerrit (one shared
initial plus Terra continuation). Do not sum the full initial-search attribution
from every model artifact.

## Quality Findings

1. Terra is the only current candidate that published both cases. It is the safest
   default for the next bounded dossier batch, despite a higher rate card.
2. Luna produced the best Pashinyan breadth and lower credit equivalent than Terra,
   but it needs a retry/formatter path for harmless linked-document URL differences.
   The Skerrit failure was not a political-evidence failure.
3. Sparse-case behavior is sound when publication succeeds. Terra did not invent
   Obama-level coverage for Skerrit and preserved explicit gaps.
4. Pashinyan quality remains smoke-grade: retrospective World Bank evidence is
   overrepresented, ruler attribution is often limited, and Luna improperly marked
   a Wikipedia ceasefire item as final evidence despite the registry's context rule.
5. M3 may be useful as an evidence generator only behind a separate low-cost
   formatter/adapter. It is not currently a direct strict-artifact worker.
6. M2.7 is not ready on the Codex surface. Disabling apps/plugins removed connector
   loops but did not yield reliable repository-tool or final-output behavior.

## Corrections Made During The Benchmark

- Added trusted cached/uncached/reasoning token capture and versioned official pricing.
- Added cache-write and long-context lower/upper ranges; actual billed cash remains unknown.
- Included policy-approved failed/retried model usage and unique billable search rounds.
- Fixed OpenAI strict response schemas to emit `additionalProperties: false`.
- Kept parent-owned pricing fields out of the model-facing response contract.
- Corrected Parallel's five-query/200-character limits by combining all eight chapter
  themes into five deterministic bounded queries.
- Preserved shared initial discovery as round 1, fixing two-round search accounting.
- Disabled unrelated apps/plugins/multi-agent/goals for MiniMax worker profiles.

## Scale Decision

Do not launch the 190-ruler batch yet. The next bounded batch should use Terra as the
publication baseline and Luna as a quality/cost challenger, with:

1. a formatter/adapter experiment for raw M3 output;
2. a provenance-preserving rule for documents directly linked or redirected from an
   approved parent result, without opening arbitrary same-domain URLs;
3. stronger discovery breadth for economics, social policy, integrity, and effectiveness;
4. automated dossier quality summaries and shared-search cost deduplication;
5. reviewed rather than draft chapter guides before score-bearing judge scale tests.
