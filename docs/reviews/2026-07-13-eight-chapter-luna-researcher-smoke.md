# Eight independent Luna chapter researchers — 2026-07-13

## Question tested

Can one ruler-period produce materially better chapter evidence coverage when
eight fresh low-cost researchers each receive only one chapter, its ten lenses,
and a simple instruction to retain 5–20 useful items (aiming for about ten),
without making the researcher satisfy the final dossier schema?

The controlled case was Jacinda Ardern, New Zealand, 2020. Eight independent
Luna Codex sessions ran concurrently, one for each chapter `1B`–`8B`. They shared
no model memory. Each received only its chapter guide, ten local priors, and the
matching ten-result discovery packet from the earlier New Zealand benchmark.
The discovery packets were reused deliberately so the experiment measured the
effect of chapter sharding rather than different search results. Because the
child Codex environment currently fails network tool setup with
`bwrap: loopback: Failed RTM_NEWADDR`, the prompts explicitly prohibited tools
and required the complete research handoff in the final response. No formatter
or final JSON-schema pass was used.

## Raw result

All eight sessions completed successfully and every raw handoff reached the
requested minimum:

| Chapter | Raw retained | Defensible distinct source-claim units | Independent quality |
|---|---:|---:|---:|
| 1B | 7 | 3 | 4/10 |
| 2B | 6 | 2 | 2/10 |
| 3B | 9 | 4 | 7/10 |
| 4B | 8 | 4 | 7.5/10 |
| 5B | 8 | 3 | 3/10 |
| 6B | 8 | 4 | 5/10 |
| 7B | 5 | 3 | 6/10 |
| 8B | 10 | 6 | 7/10 |
| **Total** | **61** | **29** | — |

The raw result is therefore not 61 independent pieces of evidence. An
independent no-web audit reduced it to about 29 defensible source-claim units.
The main inflation mechanisms were:

- splitting one URL into several records that represented only one or two
  genuinely distinct claims;
- treating explicit empty local priors as retained evidence;
- retaining tangential chapter mappings or post-period background;
- repeatedly drawing on a small common corpus across chapters.

The audit found good exact-URL provenance: every retained HTTP locator appeared
in that chapter's trusted parent packet. It also found no numeric score or score
recommendation in any handoff. Attribution caveats, contrary evidence, and gap
reports were generally disciplined. Chapters `3B`, `4B`, `7B`, and `8B` benefited
most from specialization; `1B`, `2B`, and `5B` remained genuinely thin despite
meeting the nominal count.

## Usage and cost

Combined trusted event logs for the eight fresh researchers report:

| Metric | Eight chapter researchers |
|---|---:|
| Input tokens | 222,089 |
| Cached input tokens | 71,680 |
| Uncached input tokens | 150,409 |
| Output tokens | 35,760 |
| Reasoning output tokens | 4,283 |
| Total tokens | 257,849 |
| API-equivalent marginal range, reused discovery | $0.372–$0.410 |
| API-equivalent range with eight fresh searches | about $0.412–$0.450 |
| Codex-credit equivalent | 9.303 |

Actual subscription billing is not exposed; these are estimates using the
checked-in dated pricing snapshot. The fresh-search estimate adds eight Parallel
Search calls at $0.005 each.

The earlier single all-chapter Luna research pass used 915,368 tokens and
ultimately supplied 15 published evidence items. The sharded run used 257,849
tokens, about 72% fewer, while producing 29 independently defensible units and 61
raw records. Its nominal cash-equivalent range is comparable rather than 72%
lower because much more of the sharded input/output was uncached and it generated
far more substantive output. The earlier pipeline also paid a separate formatter
cost; this experiment did not.

## Interpretation

The experiment supports chapter specialization, but it does **not** validate raw
minimum-count compliance as a quality measure. The useful result is approximately
29 defensible units with clear chapter gap reports, not 61 independent facts. It
is still a meaningful improvement over the overloaded all-chapter session:
specialized researchers spent less context managing 80 lenses and produced more
focused material with better visibility into weak chapters.

Before using this topology in a larger batch, researcher guidance and parent QA
should define the counted unit more carefully:

1. Count a distinct source-claim unit, not a heading or URL fragment.
2. Never count an empty prior or a `no evidence found` record as evidence.
3. Normally allow at most one or two retained units from the same URL, with an
   explicit justification when a source truly supports more independent claims.
4. Require direct chapter relevance and label post-period material as context,
   not target-period outcome evidence.
5. Report both raw records and deduplicated source-claim units; never use the raw
   total alone for cost/yield comparisons.

The next controlled experiment should keep eight chapter specialists but apply
those counting rules and give each chapter enough discovery breadth to replace
rejected candidates. That will show whether the defensible total can approach
the intended floor of roughly 40 without padding. A later four-researcher,
two-chapters-each test can evaluate whether most of this benefit survives with
half as many sessions.

## Artifacts

The run manifest and each chapter's trusted prompt, event log, and raw handoff
are under `data/outputs/research/chapter-shard-nzl-2020-luna-v1/`. The manifest
records all eight successful return codes and confirms that no formatter or
shared model memory was used.
