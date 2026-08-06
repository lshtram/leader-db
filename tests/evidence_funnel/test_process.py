from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from leaders_db.evidence_funnel import process as process_module


class InterruptingProcess:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self._process = process
        self.pid = process.pid

    def communicate(self, **_: object) -> None:
        time.sleep(0.15)
        raise KeyboardInterrupt

    def poll(self):
        return self._process.poll()

    def wait(self, timeout: float | None = None):
        return self._process.wait(timeout=timeout)

    @property
    def returncode(self):
        return self._process.returncode


def test_keyboard_interrupt_terminates_descendant_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat = tmp_path / "heartbeat.txt"
    real_popen = subprocess.Popen

    def spawn(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        return InterruptingProcess(process)

    monkeypatch.setattr(process_module.subprocess, "Popen", spawn)
    command = [
        "bash",
        "-c",
        f"(while true; do printf x >> '{heartbeat}'; sleep 0.02; done) & wait",
    ]

    with pytest.raises(KeyboardInterrupt):
        process_module.run_isolated_process(
            command,
            input_text="",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )

    size_after_interrupt = heartbeat.stat().st_size
    time.sleep(0.15)
    assert heartbeat.stat().st_size == size_after_interrupt


def test_timeout_terminates_process_group_and_returns_failure(
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "timeout-heartbeat.txt"
    command = [
        "bash",
        "-c",
        f"(while true; do printf x >> '{heartbeat}'; sleep 0.02; done) & wait",
    ]

    result = process_module.run_isolated_process(
        command,
        input_text="",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=0.1,
    )

    assert result.returncode == 124
    size_after_timeout = heartbeat.stat().st_size
    time.sleep(0.15)
    assert heartbeat.stat().st_size == size_after_timeout


def test_interrupt_kills_term_ignoring_child_after_leader_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat = tmp_path / "orphan-heartbeat.txt"
    real_popen = subprocess.Popen

    def spawn(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        return InterruptingProcess(process)

    monkeypatch.setattr(process_module.subprocess, "Popen", spawn)
    command = [
        "bash",
        "-c",
        f"(trap '' TERM; while true; do printf x >> '{heartbeat}'; "
        "sleep 0.02; done) & exit 0",
    ]

    with pytest.raises(KeyboardInterrupt):
        process_module.run_isolated_process(
            command,
            input_text="",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )

    size_after_interrupt = heartbeat.stat().st_size
    time.sleep(0.15)
    assert heartbeat.stat().st_size == size_after_interrupt
