# Research Answer Persistence Testing Guide

## 8B cited evaluations

Persist already-cited 8B effectiveness evaluations with:

```bash
leaders-db research persist-8b-evaluations --input tmp/8b-evaluations.json
```

The input file can be a JSON array or an object with an `evaluations` array:

```json
{
  "evaluations": [
    {
      "methodology_id": "8B.3",
      "year": 1967,
      "iso3": "TZA",
      "country_name": "Tanzania",
      "leader_name": "Julius Nyerere",
      "leader_resolution": "Julius Nyerere / TANU government",
      "program_source": "Arusha Declaration",
      "implementation_or_outcome_window": "1967-1975",
      "verdict": "partially_supported",
      "evidence_quality": "medium",
      "confidence": "medium",
      "manual_review_reason": "Outcome side effects require review.",
      "score_1_to_10": 6,
      "confidence_score": 70,
      "goal_coverage": [{"goal": "ujamaa villages", "score_1_10": 5}],
      "candidate_structured_observation": {"support_status": "partially_supported"},
      "citations": [{"url": "https://example.test/program", "title": "Program source"}],
      "caveats": ["Broad mobilization question."]
    }
  ]
}
```

This command writes `research_questions`, `research_question_answers`, and
`research_answer_evidence_links`. It does not run web research, create citations,
or invent evidence; it only persists already-cited evaluator output.
