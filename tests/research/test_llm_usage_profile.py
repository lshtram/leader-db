import json
from pathlib import Path

from leaders_db.research.llm_usage_profile import write_llm_usage_profile


def test_usage_profile_reports_each_action_and_prompt_size(tmp_path: Path) -> None:
    job_dir = tmp_path / "jobs" / "1"
    attempt_dir = job_dir / "attempts" / "001-token"
    trusted_dir = job_dir / "trusted" / "001-token"
    attempt_dir.mkdir(parents=True)
    trusted_dir.mkdir(parents=True)
    (trusted_dir / "research-chapter-1B.prompt.txt").write_text(
        "short prompt", encoding="utf-8"
    )
    (trusted_dir / "research-chapter-1B.events.jsonl").write_text(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 120,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 10,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    output_path = write_llm_usage_profile(attempt_dir)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert len(payload["actions"]) == 1
    action = payload["actions"][0]
    assert action["action"] == "research-chapter-1B"
    assert action["prompt_characters"] == 12
    assert action["estimated_prompt_tokens"] == 4
    assert action["actual_usage"]["input_tokens"] == 120
    assert action["actual_usage"]["output_tokens"] == 30


def test_usage_profile_does_not_duplicate_initial_or_formatter_actions(
    tmp_path: Path,
) -> None:
    job_dir = tmp_path / "jobs" / "1"
    attempt_dir = job_dir / "attempts" / "001-token"
    trusted_dir = job_dir / "trusted" / "001-token"
    attempt_dir.mkdir(parents=True)
    trusted_dir.mkdir(parents=True)
    event = json.dumps(
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
    )
    for name in ("research-events.jsonl", "codex-events.jsonl"):
        (trusted_dir / name).write_text(event + "\n", encoding="utf-8")
    (trusted_dir / "research-prompt.txt").write_text("recon", encoding="utf-8")
    (attempt_dir / "prompt.txt").write_text("format", encoding="utf-8")

    payload = json.loads(
        write_llm_usage_profile(attempt_dir).read_text(encoding="utf-8")
    )

    assert [item["action"] for item in payload["actions"]] == [
        "dossier_formatter",
        "research_reconnaissance",
    ]
    assert [item["prompt_characters"] for item in payload["actions"]] == [6, 5]
