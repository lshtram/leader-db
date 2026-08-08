"""Command isolation tests for Codex research roles."""

from pathlib import Path

from leaders_db.research.codex_worker_command import build_codex_exec_command
from leaders_db.research.model_profiles import ResearchModelProfile


def _profile() -> ResearchModelProfile:
    return ResearchModelProfile(
        provider="openai",
        model="gpt-5.6-sol",
        execution_surface="codex",
        roles=("dossier_researcher",),
        cost_class="test",
        context_window=1_000_000,
        codex_config_path="~/.codex/config.toml",
        credential_path="~/.codex/auth.json",
        notes="Test profile.",
    )


def test_reconnaissance_command_keeps_web_host_but_disables_file_tools(
    tmp_path: Path,
) -> None:
    command = build_codex_exec_command(
        profile=_profile(),
        project_root=tmp_path,
        schema_path=None,
        final_message_path=tmp_path / "output.md",
        writable_dir=tmp_path,
        isolated_web_research=True,
    )

    assert "--ignore-rules" in command
    disabled = {
        command[index + 1]
        for index, value in enumerate(command[:-1])
        if value == "--disable"
    }
    assert {
        "shell_tool",
        "unified_exec",
        "apps",
        "plugins",
        "multi_agent",
        "goals",
    } <= disabled
    assert "code_mode_host" not in disabled


def test_other_roles_retain_their_configured_tools(tmp_path: Path) -> None:
    command = build_codex_exec_command(
        profile=_profile(),
        project_root=tmp_path,
        schema_path=None,
        final_message_path=tmp_path / "output.md",
        writable_dir=tmp_path,
    )

    assert "--ignore-rules" not in command
    assert "shell_tool" not in command


def test_reasoning_effort_is_explicitly_forwarded(tmp_path: Path) -> None:
    command = build_codex_exec_command(
        profile=_profile(),
        project_root=tmp_path,
        schema_path=None,
        final_message_path=tmp_path / "output.md",
        writable_dir=tmp_path,
        reasoning_effort="high",
    )

    config_index = command.index("--config")
    assert command[config_index + 1] == 'model_reasoning_effort="high"'
