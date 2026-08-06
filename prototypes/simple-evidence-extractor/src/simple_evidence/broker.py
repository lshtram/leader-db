"""Runner-owned Unix-socket broker for authoritative registry mutation."""

from __future__ import annotations

import json
import socket
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe
from typing import Any

from .cli import execute_arguments
from .models import AccessScope, BrokerRequest, BrokerResponse
from .registry import Registry
from .source import load_sources

MAX_FACTS_PER_WINDOW = 15


class _BrokerServer(socketserver.UnixStreamServer):
    registry: Registry
    scopes: dict[str, AccessScope]


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            request = BrokerRequest.model_validate_json(self.rfile.readline())
            scope = self.server.scopes.get(request.capability)  # type: ignore[attr-defined]
            if scope is None:
                raise ValueError("invalid or expired capability")
            if (
                request.arguments
                and request.arguments[0] == "add"
                and scope.role == "extractor"
                and len(scope.fact_ids) >= MAX_FACTS_PER_WINDOW
            ):
                raise ValueError(
                    f"window fact limit reached ({MAX_FACTS_PER_WINDOW}); "
                    "review and confirm existing facts"
                )
            result = execute_arguments(
                request.arguments,
                role=scope.role,
                registry=self.server.registry,  # type: ignore[attr-defined]
                window_id=scope.window_id,
                scope=scope,
            )
            if request.arguments and request.arguments[0] == "add":
                fact_id = str(result["fact_id"])
                self.server.scopes[request.capability] = scope.model_copy(  # type: ignore[attr-defined]
                    update={"fact_ids": scope.fact_ids | {fact_id}}
                )
            response = BrokerResponse(ok=True, entity=result)
        except SystemExit:
            response = BrokerResponse(
                ok=False,
                error="invalid command; use only show, add, correct, or confirm",
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            response = BrokerResponse(ok=False, error=str(exc))
        self.wfile.write(
            (response.model_dump_json() + "\n").encode("utf-8")
        )


@dataclass(frozen=True)
class Broker:
    server: _BrokerServer
    socket_path: Path

    def grant(self, scope: AccessScope) -> str:
        capability = token_urlsafe(32)
        self.server.scopes[capability] = scope
        return capability

    def revoke(self, capability: str) -> None:
        self.server.scopes.pop(capability, None)


@contextmanager
def registry_broker(
    *,
    socket_path: Path,
    manifest_path: Path,
    registry_path: Path,
) -> Iterator[Broker]:
    """Serve serialized CLI requests while the model worker runs."""

    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    server = _BrokerServer(str(socket_path), _Handler)
    server.registry = Registry(registry_path, load_sources(manifest_path))
    server.scopes = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Broker(server=server, socket_path=socket_path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        socket_path.unlink(missing_ok=True)


def broker_request(
    socket_path: Path,
    *,
    arguments: list[str],
    capability: str,
) -> dict[str, Any]:
    payload = BrokerRequest(arguments=arguments, capability=capability)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall((payload.model_dump_json() + "\n").encode("utf-8"))
        response = b""
        while not response.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            response += chunk
    value = BrokerResponse.model_validate_json(response)
    if not value.ok:
        raise ValueError(value.error or "broker request failed")
    return dict(value.entity or {})


__all__ = ["broker_request", "registry_broker"]
