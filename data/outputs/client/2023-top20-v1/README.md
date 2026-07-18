# Leaders Database — 2023 Population-Top-20 Provisional Results

## Release status

This package is an organized, auditable **provisional research release**. It combines
the frozen original twenty-ruler run with targeted replacement dossiers and chapter
judgments for the United States and Thailand. Original artifacts were not overwritten.

- Original research run: `2023-population-top20-canonical-full-v1`
- Original judge run: `2023-population-top20-canonical-full-judges-v1`
- Repair research run: `2023-top20-usa-tha-repair-v1`
- Repair judge run: `2023-top20-usa-tha-repair-judges-v1`
- Frozen original archive SHA-256:
  `c110716ce38f74922b61efda9eb292a3c7f4d91b17dfd4e5bc9d0c23a0d684cc`
- Code/configuration checkpoint: Git commit `2fc9a58`
- Repair/client-package archive:
  `research/archives/2023-top20-usa-tha-repair-client-package.tar.zst`
- Repair/client-package archive SHA-256:
  `f370c06f3222867579393616964d6b02f1bcdec2d859815736c870fa07a3ae3e`

The client-facing rule is straightforward: use the original results for the other
eighteen rulers and the repaired results below for USA and Thailand. A null is an
explicit insufficient-evidence determination, not a zero and not a midpoint.

## Repaired chapter results

| Chapter | Joe Biden, USA | Confidence | Prayut Chanocha, Thailand | Confidence |
|---|---:|---:|---:|---:|
| 1B | 7.0 | 72 | null | 5 |
| 2B | 5.5 | 70 | 6.0 | 46 |
| 3B | 6.0 | 68 | 4.5 | 72 |
| 4B | 7.0 | 62 | 4.5 | 55 |
| 5B | 6.5 | 78 | 5.0 | 48 |
| 6B | 6.0 | 74 | 5.5 | 52 |
| 7B | 6.5 | 78 | 5.0 | 30 |
| 8B | 6.5 | 72 | 4.5 | 43 |

The 4B judge produced the same substantive null determination three times. Its final
candidate used fractional confidence values (`0.27` and `0.24`) instead of the required
0–100 representation and therefore failed mechanical validation. This package reports
those values as 27 and 24 while preserving the failed candidates unchanged. It does
not convert the nulls into invented scores.

Thailand's 4B and 6B chapters were rejudged from the frozen dossier under the
proportional-attribution rule adopted on 2026-07-18. Formal executive responsibility
now receives appropriate weight without requiring proof of a personal order. The 1B
null remains appropriate for a non-nuclear ruler-period without documented exposure,
and 7B was assigned a low-confidence midpoint from the narrow personal record rather
than from country-level silence.

## Corrected-methodology completion

All remaining non-1B nulls were rejudged under the proportional-attribution rule.
The correction preserves the original artifacts and records its judgments separately
in `corrected-methodology-remaining-judgments.json`. Pakistan 2B evidence was restored
from the original notebook; Vietnam 6B received narrowly targeted cited supplementation.
The resulting public matrix has no non-1B null chapter scores. Chapter 1B nulls remain
where the ruler-period had no documented nuclear or existential-risk exposure.

## Repair effect

| Case | Original evidence | Repaired evidence | Original mappings | Repaired mappings | Original blocked lenses | Repaired blocked lenses |
|---|---:|---:|---:|---:|---:|---:|
| USA | 33 | 58 | 37 | 352 | 71 | 10 |
| Thailand | 36 | 33 | 64 | 308 | 44 | 0 |

The Thailand formatter consolidated multiple source-claim records, so its evidence-item
count fell while its valid many-to-many mappings and usable lens coverage increased.
Evidence count alone is not a quality measure.

## Repair-run usage

Successful recorded model turns, excluding the zero-work connection failures and the
small M3 health probe:

| Role | Calls | Input tokens | Cached input | Output tokens | Total tokens |
|---|---:|---:|---:|---:|---:|
| M3 initial research | 2 | 4,288,359 | 4,025,856 | 37,313 | 4,325,672 |
| M3 continuation | 2 | 23,592,701 | 22,907,520 | 81,972 | 23,674,673 |
| Luna supervisor research | 4 | 6,466,482 | 5,814,528 | 30,172 | 6,496,654 |
| Luna evidence review | 9 | 584,325 | 55,552 | 23,833 | 608,158 |
| Luna formatting | 3 | 282,208 | 9,984 | 67,668 | 349,876 |
| Luna chapter judging | 10 | 381,018 | 50,176 | 35,704 | 416,722 |
| **Total** | **30** | **35,594,093** | **32,863,616** | **276,662** | **35,870,755** |

## Artifact locations

- Frozen original archive:
  `research/archives/2023-population-top20-canonical-complete-original.tar.zst`
- USA replacement dossier:
  `research/runs/2023-top20-usa-tha-repair-v1/jobs/445/attempts/002-fd95c870-17f/dossier.json`
- Thailand replacement dossier:
  `research/runs/2023-top20-usa-tha-repair-v1/jobs/446/attempts/003-f0351d03-931/dossier.json`
- Replacement judge artifacts:
  `research/runs/2023-top20-usa-tha-repair-judges-v1/`
- Machine-readable package manifest: `manifest.json`

## Important limitations

- The original eighteen-ruler judgments and the two-ruler repair judgments were emitted
  in separate judge calls. Chapter guides and score anchors are common, but the repaired
  values should receive a final cross-batch calibration audit before publication as a
  definitive ranking.
- Chapter 7B remains the weakest original chapter across the wider cohort. The repaired
  USA result is usable; Thailand remains null.
- Coverage terms are routing metadata. Judges reason from cited evidence, and missing
  lenses lower confidence rather than automatically lowering scores.
- Client matrix values were not used as evidence and are not included in this package.

## Source attribution block

The evidence dossiers contain item-level publisher, title, URL, date, locator, source
type, confidence, temporal fit, and ruler-attribution fields. Structured sources used
by the pipeline are attributed as follows, using the normative project wording:

- Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009).
- REIGN dataset (Bell 2016), snapshot of August 2021.
- Leader Survival (PLT post-1789) v5, H-DATA (Gerring et al. 2024).
- V-Dem v16 (Coppedge et al. 2026).
- World Bank WDI (World Bank 2024).
- World Bank WGI (World Bank 2023).
- UCDP GED 23.1 (Davies et al. 2023).
- Transparency International CPI 2023.
- SIPRI milex (Stockholm International Peace Research Institute 2026).
- Political Terror Scale (Wood, Gibney, et al.).
- CIRI Human Rights Data Project v3.12.10.24 (Cingranelli, Richards, and Crepaz 2024).
- FAS Nuclear Notebook (Federation of American Scientists).
- Wikidata (CC0 1.0).
- UNDP HDR 2023-24 (United Nations Development Programme 2024).
- BTI 2026 (Bertelsmann Stiftung 2026).
- WHO Global Health Observatory (World Health Organization).
- SIPRI Yearbook 2024 Ch.7 (Stockholm International Peace Research Institute 2024).
- RSF World Press Freedom Index (Reporters Without Borders 2026).

The complete normative attribution and licensing record is
`docs/sources/attributions.md`.

## Interactive comparison viewer

The read-only viewer is at `docs/client-results/2023-top20/index.html`. Rebuild its
payload with:

```bash
.venv/bin/python scripts/build_client_results_viewer.py
```

Serve it from the repository root with:

```bash
.venv/bin/python scripts/serve_design_reviews.py \
  --page docs/client-results/2023-top20/index.html
```

The viewer keeps automated and client scores separate, computes MSE only over
numeric pairs, and links each chapter back to its lens-level evidence and judgment.
