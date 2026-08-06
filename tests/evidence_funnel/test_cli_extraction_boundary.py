from __future__ import annotations

from pathlib import Path

import pytest

from leaders_db.evidence_funnel.artifacts import ArtifactStore, sha256_file
from leaders_db.evidence_funnel.cli_extraction import (
    _cli_only_command,
    _directory_sha256,
    _reject_blocked_commands,
    _validate_completion,
)
from scripts.experiments.citation_command_guard import _matches


def test_cli_command_uses_guarded_unsandboxed_shell() -> None:
    command = _cli_only_command(
        ("codex", "exec", "-", "--sandbox", "read-only"),
        "minimax-m3-long-context",
    )

    assert command.count("--disable") >= 3
    assert "shell_tool" not in command
    assert "--dangerously-bypass-hook-trust" in command
    assert command[command.index("--sandbox") + 1] == "danger-full-access"
    assert any("mcp_servers.minimax.enabled=false" in item for item in command)


def test_command_guard_rejects_prefix_substitution() -> None:
    allowed = ["/usr/bin/python", "/repo/citation.py", "--ledger", "/run/ledger"]

    assert _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger inspect LAW page",
        allowed,
    )
    assert _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger "
        "record --json '{\"draft_id\":\"D0001\"}'",
        allowed,
    )
    assert _matches(
        r"""/usr/bin/python /repo/citation.py --ledger /run/ledger """
        r"""record --json '{"claim":"aspirant\u0027s policy"}'""",
        allowed,
    )
    assert _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger "
        "revise EF-P123456789abc S00001 S00002",
        allowed,
    )
    assert not _matches("/bin/sh -c 'touch /repo/owned'", allowed)
    assert not _matches(
        "/usr/bin/python /repo/other.py --ledger /run/ledger inspect LAW page",
        allowed,
    )
    assert not _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger "
        "inspect LAW page; touch /repo/owned",
        allowed,
    )
    assert not _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger inspect LAW page && id",
        allowed,
    )
    assert not _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger inspect LAW '$(id)'",
        allowed,
    )
    assert not _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger unknown",
        allowed,
    )
    assert not _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger "
        "record --other '{\"draft_id\":\"D0001\"}'",
        allowed,
    )
    assert not _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger "
        """record --json '{"claim":"'"$HOME"'"}'""",
        allowed,
    )
    assert not _matches(
        "/usr/bin/python /repo/citation.py --ledger /run/ledger "
        """record --json '{"claim":"${HOME}"}'""",
        allowed,
    )


def test_completion_rejects_changed_ledger(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"
    ledger = attempt / "ledger"
    ledger.mkdir(parents=True)
    (attempt / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (attempt / "stderr.txt").write_text("", encoding="utf-8")
    (attempt / ".codex").mkdir()
    (attempt / ".codex/hooks.json").write_text("{}\n", encoding="utf-8")
    (ledger / "record.json").write_text("{}\n", encoding="utf-8")
    ArtifactStore(attempt).write_immutable(
        "completion.json",
        {
            "schema_version": "cli_extraction_completion_v1",
            "events_sha256": sha256_file(attempt / "events.jsonl"),
            "stderr_sha256": sha256_file(attempt / "stderr.txt"),
            "hooks_sha256": sha256_file(attempt / ".codex/hooks.json"),
            "ledger_sha256": _directory_sha256(ledger),
        },
    )
    (ledger / "record.json").write_text('{"changed": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="completion changed"):
        _validate_completion(attempt, ledger)


def test_blocked_citation_command_invalidates_attempt(tmp_path: Path) -> None:
    stderr = tmp_path / "stderr.txt"
    stderr.write_text(
        "ERROR error=Command blocked by PreToolUse hook: "
        "Only the configured evidence citation CLI is permitted.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="citation CLI command was blocked"):
        _reject_blocked_commands(stderr)


def test_clean_stderr_does_not_invalidate_attempt(tmp_path: Path) -> None:
    stderr = tmp_path / "stderr.txt"
    stderr.write_text("ordinary model diagnostic\n", encoding="utf-8")

    _reject_blocked_commands(stderr)
