"""Aggregate durable batch progress, resource use, and model usage."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_CPU_SAMPLE: tuple[int, int] | None = None


def snapshot(batch_dir: Path, jobs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build and persist one recoverable whole-batch snapshot."""

    profiles = [_read(path / "profile.json") for path in _output_dirs(batch_dir)]
    profiles = [item for item in profiles if item]
    pids = [int(job["pid"]) for job in jobs.values() if job.get("status") == "running"]
    result = {
        "captured_at": datetime.now(UTC).isoformat(),
        "machine": _machine(pids),
        "jobs": {
            "total": len(jobs),
            "running": sum(job.get("status") == "running" for job in jobs.values()),
            "completed": sum(job.get("status") == "completed" for job in jobs.values()),
            "queued": sum(job.get("status") == "queued" for job in jobs.values()),
            "failed": sum(job.get("status") == "failed" for job in jobs.values()),
        },
        "progress": {
            "completed_steps": sum(
                int(item.get("progress", {}).get("completed_steps", 0)) for item in profiles
            ),
            "total_steps": len(jobs) * 81,
        },
        "researcher_usage": _usage(profiles, "research"),
        "formatter_usage": _usage(profiles, "formatter"),
        "estimated_researcher_cost_usd": round(
            sum(float(item.get("estimated_researcher_cost_usd") or 0) for item in profiles), 6
        ),
        "evidence": {
            "records": sum(int(item.get("evidence", {}).get("records", 0)) for item in profiles),
            "unique_urls_per_dossier_sum": sum(
                int(item.get("evidence", {}).get("unique_urls", 0)) for item in profiles
            ),
            "empty_mappings": sum(
                len(item.get("evidence", {}).get("empty_mappings", [])) for item in profiles
            ),
        },
    }
    _atomic_json(batch_dir / "batch-profile.json", result)
    with (batch_dir / "batch-profile-history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, separators=(",", ":")) + "\n")
    return result


def _usage(profiles: list[dict[str, Any]], section: str) -> dict[str, int]:
    keys = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    return {
        key: sum(int(item.get(section, {}).get("usage", {}).get(key, 0)) for item in profiles)
        for key in keys
    }


def _machine(root_pids: list[int]) -> dict[str, float | int]:
    rows = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,pcpu=,rss="], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    processes = [tuple(float(value) for value in row.split()) for row in rows]
    descendants = set(root_pids)
    changed = True
    while changed:
        before = len(descendants)
        descendants.update(int(pid) for pid, ppid, _, _ in processes if int(ppid) in descendants)
        changed = len(descendants) != before
    cpu = sum(pcpu for pid, _, pcpu, _ in processes if int(pid) in descendants)
    rss = sum(rss for pid, _, _, rss in processes if int(pid) in descendants)
    memory = _meminfo()
    load = os.getloadavg()
    logical_cpus = os.cpu_count() or 1
    return {
        "logical_cpus": logical_cpus,
        "load_1m": round(load[0], 2),
        "load_5m": round(load[1], 2),
        "load_15m": round(load[2], 2),
        "batch_cpu_percent": round(cpu, 1),
        "batch_cpu_capacity_percent": round(cpu / logical_cpus, 1),
        "machine_cpu_percent": _system_cpu_percent(),
        "batch_rss_mib": round(rss / 1024, 1),
        "memory_available_mib": round(memory.get("MemAvailable", 0) / 1024, 1),
        "swap_free_mib": round(memory.get("SwapFree", 0) / 1024, 1),
    }


def _system_cpu_percent() -> float | None:
    global _CPU_SAMPLE
    values = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    total = sum(values)
    idle = values[3] + values[4]
    previous = _CPU_SAMPLE
    _CPU_SAMPLE = (total, idle)
    if previous is None or total == previous[0]:
        return None
    busy_delta = (total - previous[0]) - (idle - previous[1])
    return round(100 * busy_delta / (total - previous[0]), 1)


def _meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        result[key] = int(value.strip().split()[0])
    return result


def _output_dirs(batch_dir: Path) -> list[Path]:
    output = batch_dir / "outputs"
    return [path for path in output.iterdir() if path.is_dir()] if output.exists() else []


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
