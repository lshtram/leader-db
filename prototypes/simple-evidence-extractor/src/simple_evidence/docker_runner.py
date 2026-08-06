"""Externally sandboxed Docker command and lifecycle helpers."""

from __future__ import annotations

import os
import re
import selectors
import socket
import socketserver
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex, token_urlsafe
from shutil import which


@dataclass(frozen=True)
class DockerRuntime:
    network_name: str
    egress_network_name: str
    relay_name: str
    worker_name: str
    relay_token: str


_FORWARDERS: dict[str, tuple[socketserver.ThreadingTCPServer, threading.Thread]] = {}


def start_runtime(*, image: str, label: str) -> DockerRuntime:
    suffix = token_hex(5)
    stem = re.sub(r"[^a-z0-9_.-]", "-", label.casefold())[:35]
    runtime = DockerRuntime(
        network_name=f"simple-evidence-{stem}-{suffix}",
        egress_network_name=f"simple-evidence-egress-{suffix}",
        relay_name=f"simple-evidence-relay-{suffix}",
        worker_name=f"simple-evidence-worker-{suffix}",
        relay_token=token_urlsafe(32),
    )
    relay_script = Path(__file__).with_name("provider_relay.py")
    auth_env = Path.home() / ".config" / "minimax" / "api-key"
    try:
        _run(("docker", "network", "create", "--internal", runtime.network_name))
        _run(("docker", "network", "create", runtime.egress_network_name))
        forward_host, forward_port = _start_forwarder(
            runtime.network_name, runtime.egress_network_name
        )
        _run(
            (
                "docker",
                "run",
                "-d",
                "--name",
                runtime.relay_name,
                "--network",
                runtime.egress_network_name,
                "--add-host",
                f"host.docker.internal:{forward_host}",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "64",
                "--memory",
                "256m",
                "--env-file",
                str(auth_env),
                "-e",
                f"RELAY_TOKEN={runtime.relay_token}",
                "-e",
                "UPSTREAM_HOST=host.docker.internal",
                "-e",
                f"UPSTREAM_PORT={forward_port}",
                "-v",
                f"{relay_script}:/relay.py:ro",
                "--entrypoint",
                "/usr/local/bin/python",
                image,
                "/relay.py",
            )
        )
        _run(
            (
                "docker",
                "network",
                "connect",
                runtime.network_name,
                runtime.relay_name,
            )
        )
        _wait_for_relay(runtime.relay_name)
    except Exception:
        cleanup_runtime(runtime)
        raise
    return runtime


def cleanup_runtime(runtime: DockerRuntime) -> None:
    for container in (runtime.worker_name, runtime.relay_name):
        subprocess.run(
            ("docker", "rm", "-f", container),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    for network in (runtime.network_name, runtime.egress_network_name):
        subprocess.run(
            ("docker", "network", "rm", network),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    forwarder = _FORWARDERS.pop(runtime.network_name, None)
    if forwarder is not None:
        server, thread = forwarder
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def docker_command(
    *,
    profile_name: str,
    model: str,
    image: str,
    worker_dir: Path,
    final_path: Path,
    runtime: DockerRuntime,
) -> list[str]:
    if model != "MiniMax-M3":
        raise ValueError("secure Docker backend currently supports MiniMax-M3 only")
    codex_binary = Path(which("codex") or "").resolve()
    if not codex_binary.is_file():
        raise ValueError("codex executable was not found")
    package_src = Path(__file__).resolve().parents[1]
    site_packages = next(path for path in sys.path if path.endswith("site-packages"))
    python_binary = Path(sys.executable).resolve()
    python_home = python_binary.parents[1]
    codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    catalog = codex_root / "model-catalogs" / "minimax-m3.json"
    docker_home = worker_dir / f".codex-{profile_name}"
    docker_home.mkdir(exist_ok=True)
    _write_profile(docker_home, profile_name, model, catalog, runtime.relay_name)
    mounts = (
        (codex_binary, Path("/usr/local/bin/codex"), "ro"),
        (worker_dir, worker_dir, "rw"),
        (package_src, package_src, "ro"),
        (Path(site_packages), Path(site_packages), "ro"),
        (python_home, python_home, "ro"),
        (catalog, catalog, "ro"),
    )
    command = [
        "docker",
        "run",
        "-i",
        "--rm",
        "--name",
        runtime.worker_name,
        "--network",
        runtime.network_name,
        "--read-only",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "1g",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-e",
        f"CODEX_HOME={docker_home}",
        "-e",
        f"MINIMAX_API_KEY={runtime.relay_token}",
        "-e",
        f"PYTHONHOME={python_home}",
        "-e",
        f"PYTHONPATH={package_src}:{site_packages}",
        "-e",
        f"SIMPLE_EVIDENCE_PYTHON={python_binary}",
        "-e",
        "EVIDENCE_SOCKET",
        "-e",
        "EVIDENCE_CAPABILITY",
    ]
    for source, target, mode in mounts:
        command.extend(("-v", f"{source}:{target}:{mode}"))
    command.extend(
        (
            "--entrypoint",
            "/usr/local/bin/codex",
            image,
            "exec",
            "--ephemeral",
            "--disable",
            "apps",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "--disable",
            "goals",
            "-",
            "--json",
            "--color",
            "never",
            "--cd",
            str(worker_dir),
            "--output-last-message",
            str(final_path),
            "--profile",
            profile_name,
            "--model",
            model,
            "--dangerously-bypass-approvals-and-sandbox",
        )
    )
    return command


def _write_profile(
    docker_home: Path,
    profile_name: str,
    model: str,
    catalog: Path,
    relay_name: str,
) -> None:
    content = (
        f'model = "{model}"\n'
        'model_provider = "minimax"\n'
        f'model_catalog_json = "{catalog}"\n'
        'model_reasoning_effort = "none"\n\n'
        "[model_providers.minimax]\n"
        'name = "MiniMax relay"\n'
        f'base_url = "http://{relay_name}:8080/v1"\n'
        'wire_api = "responses"\n'
        'env_key = "MINIMAX_API_KEY"\n\n'
        "[shell_environment_policy]\n"
        'inherit = "all"\n'
        'exclude = ["MINIMAX_API_KEY"]\n'
    )
    (docker_home / f"{profile_name}.config.toml").write_text(
        content, encoding="utf-8"
    )


def _run(command: tuple[str, ...]) -> None:
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


class _ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        with socket.create_connection(("127.0.0.1", 18765), timeout=30) as upstream:
            upstream.settimeout(None)
            selector = selectors.DefaultSelector()
            selector.register(self.request, selectors.EVENT_READ, upstream)
            selector.register(upstream, selectors.EVENT_READ, self.request)
            while True:
                events = selector.select(timeout=900)
                if not events:
                    return
                for key, _ in events:
                    data = key.fileobj.recv(65536)
                    if not data:
                        return
                    key.data.sendall(data)


def _start_forwarder(runtime_key: str, egress_network_name: str) -> tuple[str, int]:
    gateway = subprocess.check_output(
        (
            "docker",
            "network",
            "inspect",
            egress_network_name,
            "--format",
            "{{(index .IPAM.Config 0).Gateway}}",
        ),
        text=True,
    ).strip()
    server = socketserver.ThreadingTCPServer((gateway, 0), _ForwardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _FORWARDERS[runtime_key] = (server, thread)
    return gateway, int(server.server_address[1])


def _wait_for_relay(container_name: str) -> None:
    probe = (
        "docker",
        "exec",
        container_name,
        "/usr/local/bin/python",
        "-c",
        "import socket; socket.create_connection(('127.0.0.1', 8080), 1).close()",
    )
    for _ in range(50):
        result = subprocess.run(
            probe,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        if result.returncode == 0:
            return
        time.sleep(0.1)
    raise RuntimeError("provider relay did not become ready")


__all__ = [
    "DockerRuntime",
    "cleanup_runtime",
    "docker_command",
    "start_runtime",
]
