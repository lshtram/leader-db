I can’t complete an evidence-based audit from this session because every local shell read failed immediately with:

`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`

That blocked inspection of the requested `dossier-curated.json`, `curation-summary.json`, `execution-profile.json`, reviewer files, judgment attempts, and `judgments-final/*/judgment.json` under the v2 and saturation-v3 paths.

**Decision:** hold.

**Smallest fix required before the next gate:**
1. Restore working local file access for the agent session, or
2. Paste/export the requested directories’ JSON files into the chat or another readable channel.

Once I can read the artifacts, I’ll produce the requested Markdown audit with:
- a metric table,
- Biden/Tshisekedi score-change table,
- findings on duplication, breadth, temporal fit, attribution, and calibration drift,
- and a clear promote/hold recommendation.