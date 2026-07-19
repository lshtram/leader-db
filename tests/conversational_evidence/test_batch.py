import json
from pathlib import Path

from leaders_db.conversational_evidence.batch import _state, _workers


def test_staged_worker_count() -> None:
    stages = [
        {"completed": 0, "workers": 3},
        {"completed": 3, "workers": 5},
        {"completed": 8, "workers": 10},
    ]

    assert _workers(stages, 0) == 3
    assert _workers(stages, 3) == 5
    assert _workers(stages, 8) == 10


def test_batch_state_is_data_driven_and_resumable(tmp_path: Path) -> None:
    manifest = {
        "batch_id": "example",
        "year": 2025,
        "cases": [{"iso3": "AAA", "country": "Alpha", "ruler": "A Person"}],
    }
    path = tmp_path / "state.json"

    state = _state(manifest, path)
    path.write_text(json.dumps(state))
    resumed = _state(manifest, path)

    assert resumed["jobs"]["AAA"]["slug"] == "aaa-2025"
    assert resumed["jobs"]["AAA"]["status"] == "queued"
    assert resumed["jobs"]["AAA"]["failures"] == 0
