"""Compatibility adapter for the configured MiniMax M3 researcher."""

from pathlib import Path

from .researcher import CodexResearcher


class M3Conversation(CodexResearcher):
    """Preserve the original constructor while using the generic adapter."""

    def __init__(self, project_root: Path, work_dir: Path, thread_id: str | None = None):
        super().__init__(project_root, work_dir, "minimax-m3", thread_id)
