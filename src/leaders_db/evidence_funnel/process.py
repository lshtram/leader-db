"""Subprocess lifecycle controls for isolated model attempts."""

from __future__ import annotations

import os
import signal
import subprocess
import time


def run_isolated_process(
    command: list[str],
    *,
    input_text: str,
    stdout,
    stderr,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run a command and terminate its whole process group on any interruption."""

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        text=True,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )
    try:
        process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        return subprocess.CompletedProcess(command, 124)
    except BaseException:
        _terminate_process_group(process)
        raise
    return subprocess.CompletedProcess(command, process.returncode)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        process.poll()
        if not _process_group_exists(process_group):
            break
        time.sleep(0.05)
    if _process_group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.wait()


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    return True


__all__ = ["run_isolated_process"]
