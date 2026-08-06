import json
from hashlib import sha256
from pathlib import Path

from leaders_db.research.model_profiles import load_research_model_profiles
from leaders_db.research.research_checkpoint_recovery import (
    load_previous_research_checkpoint,
)


def test_final_reviewed_checkpoint_recovers_without_initial_marker(
    tmp_path: Path,
) -> None:
    trusted_root = tmp_path / "trusted"
    prior = trusted_root / "001-prior"
    current = trusted_root / "002-current"
    prior.mkdir(parents=True)
    current.mkdir()
    notebook = prior / "research-notebook-round-03.md"
    events = prior / "research-supervisor-takeover-round-03.events.jsonl"
    notebook.write_text("Reviewed research ledger.", encoding="utf-8")
    events.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    (prior / "research-notebook-checkpoint.json").write_text(
        json.dumps(
            {
                "job_key": "dossier:test",
                "provider_profile": "researcher",
                "provider": "openai",
                "model": "gpt-5.4-mini",
                "notebook_path": str(notebook),
                "notebook_sha256": sha256(notebook.read_bytes()).hexdigest(),
                "events_path": str(events),
                "events_sha256": sha256(events.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    profile = load_research_model_profiles(
        Path("configs/research-models.yaml")
    ).profiles["openai-gpt54-mini-researcher"]

    recovered = load_previous_research_checkpoint(
        current,
        job={"job_key": "dossier:test", "provider_profile": "researcher"},
        profile=profile,
    )

    assert recovered is not None
    assert recovered[2] == notebook


def test_more_complete_checkpoint_wins_over_newer_partial_attempt(
    tmp_path: Path,
) -> None:
    trusted_root = tmp_path / "trusted"
    current = trusted_root / "003-current"
    current.mkdir(parents=True)
    profile = load_research_model_profiles(
        Path("configs/research-models.yaml")
    ).profiles["openai-gpt54-mini-researcher"]
    complete = _checkpoint(
        trusted_root / "001-complete",
        "\n".join(
            f"--- CHAPTER RESEARCH {number}B ---" for number in range(1, 9)
        ),
    )
    _checkpoint(trusted_root / "002-newer-partial", "--- CHAPTER RESEARCH 1B ---")

    recovered = load_previous_research_checkpoint(
        current,
        job={"job_key": "dossier:test", "provider_profile": "researcher"},
        profile=profile,
    )

    assert recovered is not None
    assert recovered[2] == complete


def _checkpoint(directory: Path, notebook_text: str) -> Path:
    directory.mkdir()
    notebook = directory / "notebook.md"
    events = directory / "events.jsonl"
    notebook.write_text(notebook_text, encoding="utf-8")
    events.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
    (directory / "research-notebook-checkpoint.json").write_text(
        json.dumps(
            {
                "job_key": "dossier:test",
                "provider_profile": "researcher",
                "provider": "openai",
                "model": "gpt-5.4-mini",
                "notebook_path": str(notebook),
                "notebook_sha256": sha256(notebook.read_bytes()).hexdigest(),
                "events_path": str(events),
                "events_sha256": sha256(events.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return notebook
