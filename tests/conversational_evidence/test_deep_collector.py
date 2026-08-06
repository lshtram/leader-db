import json
from pathlib import Path

import pytest

from leaders_db.conversational_evidence.deep_artifacts import accepted_ledger
from leaders_db.conversational_evidence.deep_collector import canonical_url, collect_deep


class FakeResearcher:
    def __init__(self, work_dir: Path, *, oversized_final: bool = False):
        self.work_dir = work_dir
        self.thread_id = "fake-thread"
        self.turn = 1
        self.prompts: list[str] = []
        self.oversized_final = oversized_final

    def ask(self, prompt: str) -> str:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        number = self.turn
        self.turn += 1
        self.prompts.append(prompt)
        if "candidate discovery only" in prompt:
            answer = "\n".join(
                f"2B-C{index:03d} | Document {index} | https://example.org/doc-{index}"
                for index in range(1, 21)
            )
        elif "Inspect only" in prompt:
            answer = "\n".join(
                f"2B-C{index:03d}: opened_accepted as 2B-S{index:03d}"
                for index in range(1, 21)
            )
        elif "Correct the oversized" in prompt:
            answer = _ledger(20)
        elif "Finalize Chapter" in prompt:
            answer = _ledger(21 if self.oversized_final else 20)
        else:
            answer = "Reconnaissance complete."
        (self.work_dir / f"turn-{number:03d}.md").write_text(answer, encoding="utf-8")
        return answer


def _ledger(count: int) -> str:
    return "\n".join(
        f"| `2B-S{index:03d}` | Document {index} | https://source.test/{index} |"
        for index in range(1, count + 1)
    )


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps(
            {
                "schema_version": "deep-chapter-workflow-v1",
                "candidate_target": 20,
                "accepted_minimum": 10,
                "accepted_maximum": 20,
                "discovery_max_rounds": 1,
                "inspection_wave_size": 20,
                "turn_timeout_seconds": 1200,
                "chapters": ["2B"],
            }
        ),
        encoding="utf-8",
    )
    priors = tmp_path / "priors.json"
    priors.write_text(
        json.dumps(
            [
                {
                    "methodology_id": "2B.1",
                    "leader": {"name": "Vladimir Putin"},
                    "country": {"iso3": "RUS"},
                    "period": {"start_year": 2023},
                    "client_matrix_policy": "excluded_as_evidence",
                    "status": "ready",
                    "local_facts": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    return workflow, priors


def test_canonical_url_removes_tracking_and_fragment() -> None:
    assert canonical_url("HTTPS://Example.COM/a//b/?utm_source=x&z=2#part") == (
        "https://example.com/a/b?z=2"
    )


def test_accepted_ledger_parses_bullet_records(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "- `4B-S053` [Country report](https://example.org/report) | Publisher | 2023\n",
        encoding="utf-8",
    )
    assert accepted_ledger(ledger, "4B") == {
        "4B-S053": "https://example.org/report"
    }


def test_collect_deep_runs_and_resumes_without_more_calls(tmp_path: Path) -> None:
    workflow, priors = _write_inputs(tmp_path)
    output = tmp_path / "run"
    researcher = FakeResearcher(output / ".researcher")

    profile = collect_deep(
        "Vladimir Putin",
        "Russia",
        "RUS",
        2023,
        output,
        priors,
        workflow_path=workflow,
        project_root=Path.cwd(),
        conversation=researcher,
    )

    result = json.loads(profile.read_text(encoding="utf-8"))
    assert len(researcher.prompts) == 4
    assert result["chapters"]["2B"]["verified_candidate_urls"] == 20
    assert result["chapters"]["2B"]["finalized"] is True
    assert (output / "chapters/2B/final.md").is_file()

    collect_deep(
        "Vladimir Putin",
        "Russia",
        "RUS",
        2023,
        output,
        priors,
        workflow_path=workflow,
        project_root=Path.cwd(),
        conversation=researcher,
    )
    assert len(researcher.prompts) == 4


def test_collect_deep_rejects_mismatched_local_priors(tmp_path: Path) -> None:
    workflow, priors = _write_inputs(tmp_path)
    value = json.loads(priors.read_text(encoding="utf-8"))
    value[0]["leader"]["name"] = "Someone Else"
    priors.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="different ruler"):
        collect_deep(
            "Vladimir Putin",
            "Russia",
            "RUS",
            2023,
            tmp_path / "run",
            priors,
            workflow_path=workflow,
            project_root=Path.cwd(),
            conversation=FakeResearcher(tmp_path / "run/.researcher"),
        )


def test_collect_deep_corrects_an_oversized_final_ledger(tmp_path: Path) -> None:
    workflow, priors = _write_inputs(tmp_path)
    output = tmp_path / "run"
    researcher = FakeResearcher(output / ".researcher", oversized_final=True)

    collect_deep(
        "Vladimir Putin",
        "Russia",
        "RUS",
        2023,
        output,
        priors,
        workflow_path=workflow,
        project_root=Path.cwd(),
        conversation=researcher,
    )

    session = json.loads((output / "session.json").read_text(encoding="utf-8"))
    assert len(researcher.prompts) == 5
    assert session["chapters"]["2B"]["final_artifact"] == "chapters/2B/final-selected.md"
