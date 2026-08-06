from __future__ import annotations

import http.client
import http.server
import threading
from pathlib import Path
from typing import Any

import pytest

from simple_evidence import docker_runner, model_runner
from simple_evidence.docker_runner import (
    DockerRuntime,
    cleanup_runtime,
    docker_command,
)
from simple_evidence.model_runner import ModelProfile
from simple_evidence.provider_relay import RelayHandler


def test_worker_command_uses_internal_network_and_no_real_secret(
    tmp_path: Path, monkeypatch: Any
) -> None:
    codex = tmp_path / "codex"
    codex.write_text("binary", encoding="utf-8")
    monkeypatch.setattr("simple_evidence.docker_runner.which", lambda _: str(codex))
    worker = tmp_path / "worker"
    worker.mkdir()
    runtime = DockerRuntime(
        "isolated-net", "egress-net", "relay-name", "worker-name", "scoped-token"
    )

    command = docker_command(
        profile_name="minimax-m3",
        model="MiniMax-M3",
        image="test-image",
        worker_dir=worker,
        final_path=worker / "final.txt",
        runtime=runtime,
    )

    rendered = " ".join(command)
    assert "--network isolated-net" in rendered
    assert "--name worker-name" in rendered
    assert "--network host" not in rendered
    assert "--env-file" not in rendered
    assert "MINIMAX_API_KEY=scoped-token" in rendered
    assert "api-key" not in rendered
    profile = (worker / ".codex-minimax-m3/minimax-m3.config.toml").read_text()
    assert "http://relay-name:8080/v1" in profile
    assert "MINIMAX_API_KEY=" not in profile


def test_cleanup_removes_worker_relay_and_network(monkeypatch: Any) -> None:
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_: Any) -> None:
        commands.append(command)

    monkeypatch.setattr("simple_evidence.docker_runner.subprocess.run", fake_run)
    runtime = DockerRuntime(
        "isolated-net", "egress-net", "relay-name", "worker-name", "scoped-token"
    )

    cleanup_runtime(runtime)

    assert ("docker", "rm", "-f", "worker-name") in commands
    assert ("docker", "rm", "-f", "relay-name") in commands
    assert ("docker", "network", "rm", "isolated-net") in commands
    assert ("docker", "network", "rm", "egress-net") in commands


def test_cleanup_stops_host_forwarder(monkeypatch: Any) -> None:
    calls: list[str] = []

    class FakeServer:
        def shutdown(self) -> None:
            calls.append("shutdown")

        def server_close(self) -> None:
            calls.append("close")

    class FakeThread:
        def join(self, timeout: int) -> None:
            calls.append(f"join:{timeout}")

    monkeypatch.setattr(
        "simple_evidence.docker_runner.subprocess.run", lambda *_args, **_kwargs: None
    )
    runtime = DockerRuntime(
        "isolated-net", "egress-net", "relay-name", "worker-name", "scoped-token"
    )
    docker_runner._FORWARDERS[runtime.network_name] = (FakeServer(), FakeThread())

    cleanup_runtime(runtime)

    assert calls == ["shutdown", "close", "join:5"]
    assert runtime.network_name not in docker_runner._FORWARDERS


def test_relay_rejects_request_without_scoped_token(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_TOKEN", "scoped-token")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
        connection.request("POST", "/v1/responses", body=b"{}")
        assert connection.getresponse().status == 401
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_relay_readiness_probe_has_per_attempt_timeout(monkeypatch: Any) -> None:
    timeouts: list[int] = []

    def timeout_run(*_args: Any, **kwargs: Any) -> None:
        timeouts.append(kwargs["timeout"])
        raise TimeoutError

    monkeypatch.setattr("simple_evidence.docker_runner.subprocess.run", timeout_run)

    with pytest.raises(TimeoutError):
        docker_runner._wait_for_relay("relay-name")

    assert timeouts == [2]


def test_invoke_timeout_always_cleans_docker_runtime(
    tmp_path: Path, monkeypatch: Any
) -> None:
    runtime = DockerRuntime(
        "isolated-net", "egress-net", "relay-name", "worker-name", "scoped-token"
    )
    cleaned: list[DockerRuntime] = []
    monkeypatch.setattr(model_runner, "start_runtime", lambda **_kwargs: runtime)
    monkeypatch.setattr(model_runner, "docker_command", lambda **_kwargs: ["worker"])
    monkeypatch.setattr(model_runner, "cleanup_runtime", cleaned.append)

    def timeout_run(*_args: Any, **_kwargs: Any) -> None:
        raise model_runner.subprocess.TimeoutExpired(["worker"], 1)

    monkeypatch.setattr(model_runner.subprocess, "run", timeout_run)
    output = tmp_path / "output"
    worker = tmp_path / "worker"
    worker.mkdir()
    profile = ModelProfile("m3", "MiniMax-M3", "docker", "image")

    with pytest.raises(RuntimeError, match="exceeded 1 seconds"):
        model_runner.invoke_model(
            profile=profile,
            prompt="extract",
            role="extractor",
            manifest_path=tmp_path / "manifest.json",
            registry_path=output / "registry.jsonl",
            output_dir=output,
            worker_dir=worker,
            socket_path=worker / "broker.sock",
            capability="capability",
            label="timeout",
            timeout=1,
        )

    assert cleaned == [runtime]
