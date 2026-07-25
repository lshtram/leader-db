"""Preflight and run resumable, budget-reserved hybrid research batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from leaders_db.conversational_evidence.data import questions

from .artifacts import write_json
from .batch_models import BatchManifest
from .runner import prepare_inputs


def preflight(manifest_path: Path, batch_dir: Path, project_root: Path) -> dict[str, object]:
    """Validate identities and build all client-excluding local-prior packages."""

    manifest = _manifest(manifest_path)
    batch_dir.mkdir(parents=True, exist_ok=True)
    _snapshot_manifest(manifest_path, batch_dir)
    cases = []
    for case in manifest.cases:
        output = batch_dir / "outputs" / f"{case.iso3.lower()}-{manifest.year}"
        prepare_inputs(
            project_root,
            output,
            case.ruler,
            case.country,
            case.iso3,
            manifest.year,
            "",
        )
        priors = json.loads(
            (output / "inputs" / "local-priors.json").read_text(encoding="utf-8")
        )
        if not isinstance(priors, list):
            raise ValueError("local-priors.json must contain a JSON array")
        statuses = _counts(str(item.get("status", "error")) for item in priors)
        cases.append(
            {
                "iso3": case.iso3,
                "ruler": case.ruler,
                "prior_rows": len(priors),
                "statuses": statuses,
                "ready": len(priors) == len(questions()) and not statuses.get("error"),
            }
        )
    report = {
        "schema_version": "hybrid_experiment_preflight_v1",
        "batch_id": manifest.batch_id,
        "year": manifest.year,
        "manifest_sha256": _sha256(manifest_path),
        "cases": cases,
        "ready": all(bool(item["ready"]) for item in cases),
    }
    write_json(batch_dir / "preflight.json", report)
    return report


def run(manifest_path: Path, batch_dir: Path, project_root: Path, interval: int = 20) -> None:
    """Run or resume every preflighted case with bounded concurrency and cost reserve."""

    manifest = _manifest(manifest_path)
    preflight_report = _read(batch_dir / "preflight.json")
    if not preflight_report.get("ready"):
        raise ValueError("batch preflight is not ready")
    if preflight_report.get("manifest_sha256") != _sha256(manifest_path):
        raise ValueError("manifest changed after preflight")
    state_path = batch_dir / "batch-state.json"
    state = _state(manifest, state_path, batch_dir)
    logs = batch_dir / "logs"
    logs.mkdir(exist_ok=True)
    processes: dict[str, tuple[subprocess.Popen[str], Any]] = {}
    while True:
        _reconcile(manifest, state, processes, batch_dir)
        completed = sum(job["status"] == "completed" for job in state["jobs"].values())
        if completed == len(state["jobs"]):
            _save_state(state_path, state, batch_dir, manifest)
            return
        if any(job["status"] == "failed" for job in state["jobs"].values()):
            _save_state(state_path, state, batch_dir, manifest)
            raise RuntimeError("batch contains a terminal failed case")
        workers = _workers(manifest, completed)
        running = sum(job["status"] == "running" for job in state["jobs"].values())
        for job in state["jobs"].values():
            if running >= workers or job["status"] != "queued":
                continue
            if not _can_reserve(manifest, state, batch_dir):
                _save_state(state_path, state, batch_dir, manifest)
                raise RuntimeError("batch cost ceiling cannot reserve another ruler")
            process, handle = _launch(manifest, job, batch_dir, project_root)
            processes[job["iso3"]] = (process, handle)
            job.update(
                status="running",
                pid=process.pid,
                launches=int(job["launches"]) + 1,
                launch_progress=_progress_marker(batch_dir / "outputs" / job["slug"]),
                started_at=datetime.now(UTC).isoformat(),
            )
            running += 1
        _save_state(state_path, state, batch_dir, manifest)
        time.sleep(interval)


def _launch(
    manifest: BatchManifest,
    job: dict[str, Any],
    batch_dir: Path,
    project_root: Path,
) -> tuple[subprocess.Popen[str], Any]:
    slug = str(job["slug"])
    output = batch_dir / "outputs" / slug
    log = (batch_dir / "logs" / f"{slug}.log").open("a", encoding="utf-8")
    command = [
        str(project_root / ".venv/bin/python"),
        "-m",
        "leaders_db.conversational_evidence.hybrid_experiment.cli",
        "--ruler",
        str(job["ruler"]),
        "--country",
        str(job["country"]),
        "--iso3",
        str(job["iso3"]),
        "--year",
        str(manifest.year),
        "--output-dir",
        str(output),
        "--researcher",
        manifest.researcher,
        "--cost-ceiling-usd",
        str(manifest.per_ruler_cost_ceiling_usd),
    ]
    if manifest.research_mode == "saturation_v3":
        command.append("--saturation-v3")
    process = subprocess.Popen(
        command,
        cwd=project_root,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, log


def _reconcile(
    manifest: BatchManifest,
    state: dict[str, Any],
    processes: dict[str, tuple[subprocess.Popen[str], Any]],
    batch_dir: Path,
) -> None:
    for iso3, job in state["jobs"].items():
        if job["status"] != "running":
            continue
        managed = processes.get(iso3)
        if managed and managed[0].poll() is None:
            continue
        if managed is None and _alive(job.get("pid")):
            continue
        return_code = managed[0].returncode if managed else None
        if managed:
            managed[1].close()
            processes.pop(iso3)
        output = batch_dir / "outputs" / job["slug"]
        session = _read_optional(output / "session.json")
        if session.get("last_completed") == "complete" and (output / "dossier.json").is_file():
            job.update(status="completed", pid=None, finished_at=_now(), return_code=return_code)
        elif _progress_marker(output) != tuple(job.get("launch_progress") or ()):
            job.update(status="queued", pid=None, failures=0, return_code=return_code)
        elif int(job["failures"]) < manifest.maximum_failures_per_case:
            job.update(
                status="queued",
                pid=None,
                failures=int(job["failures"]) + 1,
                return_code=return_code,
            )
        else:
            job.update(status="failed", pid=None, finished_at=_now(), return_code=return_code)


def _state(
    manifest: BatchManifest, path: Path, batch_dir: Path
) -> dict[str, Any]:
    if path.exists():
        value = _read(path)
        for job in value["jobs"].values():
            if job["status"] == "running" and not _alive(job.get("pid")):
                job["status"] = "queued"
            if (
                job["status"] == "failed"
                and _progress_marker(batch_dir / "outputs" / job["slug"])
                != tuple(job.get("launch_progress") or ())
            ):
                job.update(status="queued", failures=0, pid=None)
        return value
    return {
        "schema_version": "hybrid_experiment_batch_state_v1",
        "batch_id": manifest.batch_id,
        "created_at": _now(),
        "jobs": {
            case.iso3: {
                **case.model_dump(mode="json"),
                "slug": f"{case.iso3.lower()}-{manifest.year}",
                "status": "queued",
                "launches": 0,
                "failures": 0,
                "pid": None,
            }
            for case in manifest.cases
        },
    }


def _progress_marker(output: Path) -> tuple[str, ...]:
    """Return durable stage artifacts used to detect progress across retries."""

    candidates = [
        output / "reconnaissance.md",
        *(output / "chapters" / f"{number}B.md" for number in range(1, 9)),
        output / "review.json",
        output / "follow-up.md",
        output / "review-final.json",
        output / "dossier.json",
    ]
    return tuple(path.name for path in candidates if path.is_file())


def _save_state(
    path: Path, state: dict[str, Any], batch_dir: Path, manifest: BatchManifest
) -> None:
    write_json(path, state)
    profiles = [
        _read_optional(batch_dir / "outputs" / job["slug"] / "profile.json")
        for job in state["jobs"].values()
    ]
    write_json(
        batch_dir / "batch-profile.json",
        {
            "batch_id": manifest.batch_id,
            "status_counts": _counts(job["status"] for job in state["jobs"].values()),
            "completed_estimated_cost_usd": round(
                sum(float(item.get("estimated_cost_usd") or 0) for item in profiles), 6
            ),
            "completed_duration_seconds": round(
                sum(float(item.get("duration_seconds") or 0) for item in profiles), 3
            ),
        },
    )


def _can_reserve(manifest: BatchManifest, state: dict[str, Any], batch_dir: Path) -> bool:
    spent = sum(
        float(
            _read_optional(batch_dir / "outputs" / job["slug"] / "profile.json").get(
                "estimated_cost_usd"
            )
            or 0
        )
        for job in state["jobs"].values()
        if job["status"] == "completed"
    )
    running = sum(job["status"] == "running" for job in state["jobs"].values())
    reserved = (running + 1) * manifest.per_ruler_cost_ceiling_usd
    return spent + reserved <= manifest.batch_cost_ceiling_usd


def _workers(manifest: BatchManifest, completed: int) -> int:
    return max(stage.workers for stage in manifest.stages if completed >= stage.completed)


def _snapshot_manifest(path: Path, batch_dir: Path) -> None:
    target = batch_dir / "manifest.json"
    value = _read(path)
    if target.exists() and _read(target) != value:
        raise ValueError("batch directory contains a different manifest")
    if not target.exists():
        write_json(target, value)


def _manifest(path: Path) -> BatchManifest:
    return BatchManifest.model_validate(_read(path))


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_optional(path: Path) -> dict[str, Any]:
    return _read(path) if path.exists() else {}


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[str(value)] = result.get(str(value), 0) + 1
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _alive(pid: object) -> bool:
    return isinstance(pid, int) and Path(f"/proc/{pid}").exists()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "run"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--interval", type=int, default=20)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    if args.action == "preflight":
        result = preflight(args.manifest, args.batch_dir, root)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    else:
        run(args.manifest, args.batch_dir, root, args.interval)


if __name__ == "__main__":
    main()
