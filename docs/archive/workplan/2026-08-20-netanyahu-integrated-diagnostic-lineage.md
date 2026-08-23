# Netanyahu 2023 integrated diagnostic lineage through v16

This closes the historical run narrative that occupied the active workplan before consolidation.
The byte-complete narrative remains recoverable from `docs/workplan.md` at commit `ac033fdd`;
immutable outputs remain under `research/runs/`.

| Release or experiment | Terminal result | Lasting consequence |
|---|---|---|
| Terra/Sol v2 | Review rejected 6B.1 | Preserve claim citations and allocation-versus-execution distinctions. |
| Terra v3 | Grouped-citation parser stop | Validate individual and semicolon-grouped IDs. |
| Terra v4 | Missing inline citation | Keep strict inline claim-level completeness. |
| All-Sol v5 | Review defects and quota overage | Add run-wide usage control; reject all-Sol writing under the old quota. |
| Luna/Sol v6-v8 | Structural disposition failures | Enforce exact response keys and prospective fail-stop behavior. |
| Luna/Sol v9 | Writing passed; 3B.2 review failed | Keep material coverage as an independent-review gate. |
| Luna/Sol v10 | Explicit return used; later review failed | Freeze lineage; its 72 writer reopen requests became evidence-completion input. |
| Focused verifier v1/v2 | Diagnostic only | Not promoted as another production quality stage. |
| Luna/Sol v11 | Owner disappeared | Require detached ownership; never resume an incomplete run. |
| Luna/Sol v12 | Invented evidence ID | Replace free-form citations with allowlisted structured sections. |
| v13 | Superseded zero-call preflight | The proposed repair did not address the actual failure. |
| v14 | One-call 6B.6 proof passed | Validate strict citation transport on the known failure. |
| v15 | Ten-call boundary batch passed | Validate excluded predecessors and the largest request. |
| v16 | 80 writes passed; 29 second-round requests | Close discovery after one completion; do not promote those requests. |

## Controls retained in v17

- One production action followed by one independent quality action.
- No automatic retry, repair, re-review, or supervisor takeover.
- One evidence-completion decision per lineage, distinct from the one explicit post-review
  material-defect return.
- Closed writer packets have no compact index or reopen-response field.
- Strict citation enums, deterministic rendering, run-wide reservations, shared fail-stop, and
  detached ownership.
- Failed and superseded runs remain immutable and cannot be resumed or relabeled.

Next task: P1-T1, zero-call preflight of v17 blind independent review.
