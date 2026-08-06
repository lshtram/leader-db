from __future__ import annotations

from leaders_db.evidence_funnel.execution import _without_optional_m3_servers


def test_m3_execution_disables_optional_mcp_servers() -> None:
    command = _without_optional_m3_servers(
        ("codex", "exec", "-", "--sandbox", "read-only"),
        "minimax-m3-long-context",
    )

    assert all(
        f"mcp_servers.{name}.enabled=false" in command
        for name in ("minimax", "fetch", "brave", "parallel")
    )


def test_non_m3_execution_command_is_unchanged() -> None:
    command = ("codex", "exec", "-", "--sandbox", "read-only")

    assert _without_optional_m3_servers(
        command, "minimax-m2.7-researcher"
    ) == command
