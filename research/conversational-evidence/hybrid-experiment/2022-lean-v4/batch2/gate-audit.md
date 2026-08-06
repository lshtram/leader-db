# Lean-v4 batch-two evidence gate

All five rulers completed concurrently on their first batch launch. The original
research, reviewer output, follow-up, final review, ledger, dossier, and profiles are
preserved per ruler.

## Results

| Ruler | Accepted claims | Distinct URLs | Domains | Web calls | Cost | Model time |
|---|---:|---:|---:|---:|---:|---:|
| Sheikh Hasina | 104 | 86 | 36 | 208 | $2.297 | 74.1 min |
| Joko Widodo | 86 | 78 | 36 | 199 | $1.942 | 88.2 min |
| Andres Manuel Lopez Obrador | 111 | 97 | 39 | 173 | $2.169 | 83.0 min |
| Muhammadu Buhari | 125 | 93 | 38 | 205 | $2.469 | 82.1 min |
| Shehbaz Sharif | 89 | 80 | 32 | 171 | $2.273 | 74.3 min |

The batch produced 515 accepted claims from 434 distinct URLs. Mean cost was $2.23
per ruler and total cost was $11.15, below both the $5 ruler ceiling and $25 batch
ceiling. Each reviewer used the one allowed targeted follow-up; no ruler was relaunched
and no completed research chapter was repeated.

## Quality decision

- Hasina and Widodo passed seven chapters; 7B remains manual review because direct
  ruler-specific integrity evidence is thinner than institutional or self-reported
  material.
- Lopez Obrador passed five chapters; 3B and 7B remain manual review, while 4B retains
  a credible gap. The reviewer explicitly prevented broad violence, democratic, and
  integrity context from being treated as direct personal attribution.
- Buhari passed six chapters after the recovered follow-up. 1B retains a credible gap
  and 7B remains manual review. The follow-up increased the dossier from 120 to 125
  accepted claims and corrected the evidence-review control defect without repeating
  prior research.
- Sharif passed six chapters; 1B retains a credible gap and 7B remains manual review.
- Across all five dossiers, final review preserves source-family concentration and
  attribution warnings rather than filling quotas with weak claims.

## Process finding

Buhari's initial reviewer requested targeted follow-up in six chapters but supplied an
inconsistent overall disposition. The runner therefore skipped the follow-up. Commit
`41fa972` now derives the overall disposition deterministically from chapter decisions
and revalidates saved reviews on resume. Focused tests and Ruff passed. Buhari was then
resumed from the saved dossier; only the intended follow-up and final review ran.

Decision: pass the evidence flow to batch three. Comparative judgment remains deferred
until all 20 dossiers are assembled so every ruler is scored on the same chapter meter.
