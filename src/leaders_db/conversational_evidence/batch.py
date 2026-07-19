"""Resumable staged-concurrency runner for conversational evidence batches."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .batch_profile import snapshot


def run(
    manifest_path: Path, batch_dir: Path, interval: int = 20, *, retry_failed: bool = False
) -> None:
    """Run or resume every manifest case, scaling only after completed gates."""

    manifest = _read(manifest_path)
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "logs").mkdir(exist_ok=True)
    manifest_snapshot = batch_dir / "manifest.json"
    if not manifest_snapshot.exists():
        _save(manifest_snapshot, manifest)
    state_path = batch_dir / "batch-state.json"
    state = _state(manifest, state_path)
    if retry_failed:
        for job in state["jobs"].values():
            if job["status"] == "failed":
                job.update(status="queued", failures=0, pid=None, finished_at=None)
    processes: dict[str, tuple[subprocess.Popen[str], Any]] = {}
    while True:
        _reconcile(state, processes, batch_dir)
        completed = sum(job["status"] == "completed" for job in state["jobs"].values())
        if any(job["status"] == "failed" for job in state["jobs"].values()):
            _save(state_path, state)
            snapshot(batch_dir, state["jobs"])
            raise RuntimeError("batch has a job that failed three attempts")
        if completed == len(state["jobs"]):
            _save(state_path, state)
            snapshot(batch_dir, state["jobs"])
            return
        workers = _workers(manifest["stages"], completed)
        running = sum(job["status"] == "running" for job in state["jobs"].values())
        for iso3, job in state["jobs"].items():
            if running >= workers:
                break
            if job["status"] != "queued":
                continue
            process, handle = _launch(manifest, job, batch_dir)
            processes[iso3] = (process, handle)
            job.update(
                status="running",
                pid=process.pid,
                launches=int(job.get("launches", 0)) + 1,
                started_at=datetime.now(UTC).isoformat(),
                finished_at=None,
            )
            running += 1
        _save(state_path, state)
        snapshot(batch_dir, state["jobs"])
        time.sleep(interval)


def _launch(
    manifest: dict[str, Any], job: dict[str, Any], batch_dir: Path
) -> tuple[subprocess.Popen[str], Any]:
    output = batch_dir / "outputs" / job["slug"]
    log = (batch_dir / "logs" / f"{job['slug']}.log").open("a", encoding="utf-8")
    command = [
        ".venv/bin/python",
        "-m",
        "leaders_db.conversational_evidence",
        job["ruler"],
        job["country"],
        str(manifest["year"]),
        str(output),
        "--researcher",
        manifest["researcher"],
    ]
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True), log


def _reconcile(
    state: dict[str, Any], processes: dict[str, tuple[subprocess.Popen[str], Any]], batch_dir: Path
) -> None:
    for iso3, job in state["jobs"].items():
        if job["status"] != "running":
            continue
        managed = processes.get(iso3)
        if managed and managed[0].poll() is None:
            continue
        if managed is None and _alive(job.get("pid")):
            continue
        if managed:
            managed[1].close()
            processes.pop(iso3)
        session = _read(batch_dir / "outputs" / job["slug"] / "session.json")
        if len(session.get("completed", [])) == 81:
            job.update(status="completed", pid=None, finished_at=datetime.now(UTC).isoformat())
        elif int(job.get("failures", 0)) < 2:
            job.update(status="queued", pid=None, failures=int(job.get("failures", 0)) + 1)
        else:
            job.update(status="failed", pid=None, finished_at=datetime.now(UTC).isoformat())


def _state(manifest: dict[str, Any], path: Path) -> dict[str, Any]:
    if path.exists():
        state = _read(path)
        for job in state["jobs"].values():
            job.setdefault("launches", int(job.pop("attempts", 0)))
            job.setdefault("failures", 0)
            if job["status"] == "running" and not _alive(job.get("pid")):
                job["status"] = "queued"
        return state
    jobs = {
        case["iso3"]: {
            **case,
            "slug": f"{case['iso3'].lower()}-{manifest['year']}",
            "status": "queued",
            "launches": 0,
            "failures": 0,
            "pid": None,
        }
        for case in manifest["cases"]
    }
    return {
        "batch_id": manifest["batch_id"],
        "created_at": datetime.now(UTC).isoformat(),
        "jobs": jobs,
    }


def _workers(stages: list[dict[str, int]], completed: int) -> int:
    return max(stage["workers"] for stage in stages if completed >= stage["completed"])


def _alive(pid: object) -> bool:
    if not isinstance(pid, int):
        return False
    return Path(f"/proc/{pid}").exists()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _save(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    run(args.manifest, args.batch_dir, args.interval, retry_failed=args.retry_failed)


if __name__ == "__main__":
    main()
