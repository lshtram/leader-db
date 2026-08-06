Perform a no-search targeted release review for the 2022 top-20 judgments. Do not
change scores or evidence. Read the affected judgment, its compact chapter projection,
and its source dossier/review artifacts. Review these cases:

- projection integrity: 2B/COD; 3B/DEU; 4B/IDN,IND,NGA,PAK; 5B/PHL;
  6B/THA,TUR; 7B/IDN,IND; 8B/JPN,TUR.
- recoverable null: 2B/NGA.

Judgments 1B-7B are under
`research/conversational-evidence/hybrid-experiment/2022-top20-v2/judgments-v1/`.
The 8B judgment is under
`research/conversational-evidence/hybrid-experiment/2022-top20-v2/judgments-8b-v2/`.
Compact projections are under `judge-compact-v1/` for 2B-7B and
`judge-compact-v2/` for 8B. Source dossiers and original reviews are reachable from
the conversion report and the consolidated `outputs/` directory.

For each projection-integrity case, decide `clear_unchanged` only if the retained
projection independently supports the existing score and rationale after the named
references were dropped. Otherwise decide `rerun_required` and explain why.

For 2B/NGA, decide `clear_null_nonrecoverable` only if the completed broad research,
review, and targeted follow-up reached credible saturation and the remaining null is a
genuine absence of judgeable 2022 international-peace conduct, not an unsearched gap.
Otherwise decide `research_required` and give the exact query direction.

Return JSON only:
{"reviews":[{"iso3":"...","chapter_id":"...","existing_score":0,
"recommended_score":0,"decision":"clear_unchanged|clear_null_nonrecoverable|rerun_required|research_required",
"explanation":"..."}]}
Use null for both score fields in the NGA null case. Include exactly 14 reviews.
