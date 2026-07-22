# Lean-v4 batch-four evidence gate

All five rulers completed on their first launch with no process failures or repeated
research chapters. The hardened review controls behaved as intended.

## Results

| Ruler | Accepted claims | Distinct URLs | Domains | Web calls | Cost | Model time |
|---|---:|---:|---:|---:|---:|---:|
| Jair Bolsonaro | 94 | 92 | 25 | 108 | $1.717 | 57.9 min |
| Narendra Modi | 90 | 86 | 29 | 174 | $2.053 | 80.5 min |
| Ali Khamenei | 92 | 81 | 38 | 197 | $2.226 | 78.6 min |
| Prayut Chan-o-cha | 96 | 77 | 38 | 205 | $2.328 | 78.4 min |
| Recep Tayyip Erdogan | 97 | 80 | 38 | 188 | $2.139 | 75.7 min |

The batch produced 469 accepted claims from 416 distinct URLs. Mean cost was $2.09
per ruler and total cost was $10.46, below both configured ceilings.

## Quality decision

- Bolsonaro passed all eight chapters after the bounded review flow.
- Modi passed six chapters; 6B and 7B remain manual review where the evidence requires
  careful ruler attribution rather than national-outcome inference.
- Khamenei passed six chapters; 5B and 7B retain credible gaps rather than being padded
  with indirect economic or personal-integrity claims.
- Prayut passed seven chapters; 7B remains manual review because direct evidence about
  personal honesty is thinner than institutional and regime evidence.
- Erdogan passed seven chapters; 7B remains manual review for the same ruler-specific
  integrity limitation.

Each ruler used at most the single allowed follow-up. Unresolved gaps were retained as
confidence limitations; no terminal reviewer triggered another research cycle.

Decision: accept the final evidence batch and proceed to the common-meter comparative
judgments for all 20 rulers.
