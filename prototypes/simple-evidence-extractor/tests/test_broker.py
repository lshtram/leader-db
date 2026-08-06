from __future__ import annotations

from pathlib import Path

import pytest

from simple_evidence.broker import (
    MAX_FACTS_PER_WINDOW,
    broker_request,
    registry_broker,
)
from simple_evidence.models import AccessScope
from simple_evidence.registry import Registry
from simple_evidence.source import load_sources


def test_broker_owns_registry_outside_worker_directory(
    manifest_path: Path, tmp_path: Path
) -> None:
    worker = tmp_path / "worker"
    socket_path = worker / "evidence.sock"
    registry_path = tmp_path / "control/registry.jsonl"
    with registry_broker(
        socket_path=socket_path,
        manifest_path=manifest_path,
        registry_path=registry_path,
    ) as broker:
        capability = broker.grant(
            AccessScope(
                role="extractor",
                window_id="window-1",
                source_id="DOC-1",
                start_sentence=1,
                end_sentence=1,
            )
        )
        shown = broker_request(
            socket_path,
            arguments=["show", "DOC-1", "1", "1"],
            capability=capability,
        )
        added = broker_request(
            socket_path,
            arguments=[
                "add",
                "DOC-1",
                "1",
                "--summary",
                "The authority adopted Rule A.",
            ],
            capability=capability,
        )
        confirmed = broker_request(
            socket_path,
            arguments=["confirm", added["fact_id"]],
            capability=capability,
        )

    assert shown["sentences"][0]["sentence_id"] == "S000001"
    assert confirmed["extractor_confirmed"]
    assert not (worker / "registry.jsonl").exists()
    assert Registry(registry_path, load_sources(manifest_path)).states()


def test_capability_confines_role_range_and_fact_access(
    manifest_path: Path, tmp_path: Path
) -> None:
    socket_path = tmp_path / "worker/evidence.sock"
    registry_path = tmp_path / "control/registry.jsonl"
    with registry_broker(
        socket_path=socket_path,
        manifest_path=manifest_path,
        registry_path=registry_path,
    ) as broker:
        token = broker.grant(
            AccessScope(
                role="extractor",
                window_id="window-1",
                source_id="DOC-1",
                start_sentence=1,
                end_sentence=2,
            )
        )
        with pytest.raises(ValueError, match="outside the assigned range"):
            broker_request(
                socket_path,
                arguments=["show", "DOC-1", "1", "3"],
                capability=token,
            )
        added = broker_request(
            socket_path,
            arguments=["add", "DOC-1", "1", "--summary", "A bounded fact."],
            capability=token,
        )
        broker_request(
            socket_path,
            arguments=["confirm", added["fact_id"]],
            capability=token,
        )
        repeated = broker_request(
            socket_path,
            arguments=["confirm", added["fact_id"]],
            capability=token,
        )
        assert repeated["extractor_confirmed"]
        assert not repeated["reviewer_confirmed"]
        with pytest.raises(ValueError, match="outside the assigned allowlist"):
            broker_request(
                socket_path,
                arguments=["show", "F-not-assigned"],
                capability=token,
            )


def test_expired_capability_is_rejected(
    manifest_path: Path, tmp_path: Path
) -> None:
    socket_path = tmp_path / "worker/evidence.sock"
    with registry_broker(
        socket_path=socket_path,
        manifest_path=manifest_path,
        registry_path=tmp_path / "registry.jsonl",
    ) as broker:
        token = broker.grant(
            AccessScope(
                role="extractor",
                window_id="window-1",
                source_id="DOC-1",
                start_sentence=1,
                end_sentence=1,
            )
        )
        broker.revoke(token)
        with pytest.raises(ValueError, match="invalid or expired"):
            broker_request(
                socket_path,
                arguments=["show", "DOC-1", "1", "1"],
                capability=token,
            )


def test_invalid_command_does_not_stop_broker(
    manifest_path: Path, tmp_path: Path
) -> None:
    socket_path = tmp_path / "worker/evidence.sock"
    with registry_broker(
        socket_path=socket_path,
        manifest_path=manifest_path,
        registry_path=tmp_path / "registry.jsonl",
    ) as broker:
        token = broker.grant(
            AccessScope(
                role="extractor",
                window_id="window-1",
                source_id="DOC-1",
                start_sentence=1,
                end_sentence=1,
            )
        )
        with pytest.raises(ValueError, match="use only show"):
            broker_request(
                socket_path,
                arguments=["list"],
                capability=token,
            )
        shown = broker_request(
            socket_path,
            arguments=["show", "DOC-1", "1", "1"],
            capability=token,
        )
        assert shown["source_id"] == "DOC-1"


def test_broker_enforces_window_fact_limit(
    manifest_path: Path, tmp_path: Path
) -> None:
    socket_path = tmp_path / "worker/evidence.sock"
    with registry_broker(
        socket_path=socket_path,
        manifest_path=manifest_path,
        registry_path=tmp_path / "registry.jsonl",
    ) as broker:
        token = broker.grant(
            AccessScope(
                role="extractor",
                window_id="window-1",
                source_id="DOC-1",
                start_sentence=1,
                end_sentence=1,
                fact_ids=frozenset(
                    f"F-{number}" for number in range(MAX_FACTS_PER_WINDOW)
                ),
            )
        )

        with pytest.raises(ValueError, match="window fact limit reached"):
            broker_request(
                socket_path,
                arguments=["add", "DOC-1", "1", "--summary", "One fact too many."],
                capability=token,
            )
