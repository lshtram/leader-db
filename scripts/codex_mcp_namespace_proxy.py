#!/usr/bin/env python3
"""Bridge Codex MCP namespace tools to OpenAI-compatible custom providers."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MCP_TOOL_ALIASES = {
    "brave_llm_context": ("mcp__brave", "brave_llm_context"),
    "brave_web_search": ("mcp__brave", "brave_web_search"),
    "minimax_web_search": ("mcp__minimax", "web_search"),
    "parallel_web_fetch": ("mcp__parallel", "web_fetch"),
    "parallel_web_search": ("mcp__parallel", "web_search"),
    "web_fetch": ("mcp__parallel", "web_fetch"),
    "web_search": ("mcp__parallel", "web_search"),
}


def expand_namespace_tools(payload: Any) -> Any:
    """Replace Responses namespace tools with ordinary function definitions."""

    if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
        return payload
    expanded: list[Any] = []
    for item in payload["tools"]:
        if not isinstance(item, dict) or item.get("type") != "namespace":
            expanded.append(item)
            continue
        namespace = str(item.get("name", ""))
        tools = item.get("tools")
        if not namespace or not isinstance(tools, list):
            expanded.append(item)
            continue
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                continue
            parameters = tool.get("parameters", tool.get("input_schema", {}))
            alias = next(
                (
                    name
                    for name, target in MCP_TOOL_ALIASES.items()
                    if target == (namespace, tool["name"])
                ),
                f"{namespace.removeprefix('mcp__').rstrip('_')}_{tool['name']}",
            )
            expanded.append(
                {
                    "type": "function",
                    "name": alias,
                    "description": tool.get("description", ""),
                    "parameters": parameters,
                    "strict": bool(tool.get("strict", False)),
                }
            )
    result = dict(payload)
    result["tools"] = expanded
    return result


def restore_tool_namespaces(payload: Any) -> Any:
    """Convert flat MCP function names back to Codex namespace/name pairs."""

    if isinstance(payload, list):
        return [restore_tool_namespaces(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    result = {key: restore_tool_namespaces(value) for key, value in payload.items()}
    name = result.get("name")
    if isinstance(name, str) and name in MCP_TOOL_ALIASES and "namespace" not in result:
        result = _normalize_research_tool_arguments(result, alias=name)
        result["namespace"], result["name"] = MCP_TOOL_ALIASES[name]
        return result
    if (
        isinstance(name, str)
        and name.startswith("mcp__")
        and "__" in name.removeprefix("mcp__")
        and "namespace" not in result
    ):
        server, tool = name.removeprefix("mcp__").split("__", maxsplit=1)
        if server and tool:
            result["namespace"] = f"mcp__{server}"
            result["name"] = tool
    return result


def _normalize_research_tool_arguments(payload: dict[str, Any], *, alias: str) -> dict[str, Any]:
    """Repair MiniMax's singleton-wrapper encoding for Parallel list arguments."""

    field = {
        "parallel_web_search": "search_queries",
        "web_search": "search_queries",
        "parallel_web_fetch": "urls",
        "web_fetch": "urls",
    }.get(alias)
    if field is None or "arguments" not in payload:
        return payload
    raw_arguments = payload["arguments"]
    encoded = isinstance(raw_arguments, str)
    if encoded:
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return payload
    else:
        arguments = raw_arguments
    if not isinstance(arguments, dict):
        return payload
    wrapped = arguments.get(field)
    if not isinstance(wrapped, dict) or set(wrapped) != {"item"}:
        return payload
    items = wrapped["item"]
    if isinstance(items, str):
        items = [items]
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        return payload
    normalized = dict(arguments)
    normalized[field] = items
    result = dict(payload)
    result["arguments"] = (
        json.dumps(normalized, separators=(",", ":")) if encoded else normalized
    )
    return result


def transform_response_body(body: bytes, content_type: str) -> bytes:
    """Restore namespace metadata in JSON or server-sent-event responses."""

    if "text/event-stream" not in content_type:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return body
        return json.dumps(restore_tool_namespaces(payload), separators=(",", ":")).encode()
    output: list[bytes] = []
    for line in body.splitlines(keepends=True):
        if not line.startswith(b"data:"):
            output.append(line)
            continue
        prefix, raw = line.split(b":", maxsplit=1)
        ending = b"\n" if line.endswith(b"\n") else b""
        raw = raw.strip()
        if raw == b"[DONE]":
            output.append(prefix + b": [DONE]" + ending)
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            output.append(line)
            continue
        transformed = json.dumps(restore_tool_namespaces(payload), separators=(",", ":")).encode()
        output.append(prefix + b": " + transformed + ending)
    return b"".join(output)


class NamespaceProxyHandler(BaseHTTPRequestHandler):
    """Forward Responses requests while translating MCP namespace encoding."""

    server: NamespaceProxyServer

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._respond(200, b'{"status":"ok"}', "application/json")
            return
        self._forward()

    def do_POST(self) -> None:
        self._forward()

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"codex-mcp-proxy: {format % args}\n")

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        if body:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                pass
            else:
                body = json.dumps(expand_namespace_tools(payload), separators=(",", ":")).encode()
        upstream_url = f"{self.server.upstream}{self.path}"
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "accept-encoding"}
        }
        request = urllib.request.Request(
            upstream_url,
            data=body if self.command != "GET" else None,
            headers=headers,
            method=self.command,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.server.timeout) as response:
                response_body = response.read()
                content_type = response.headers.get("Content-Type", "application/json")
                transformed = transform_response_body(response_body, content_type)
                routed_names = sorted(
                    {
                        match.decode()
                        for match in re.findall(rb'"(?:name|namespace)":"mcp__[^" ]+"', transformed)
                    }
                )
                if routed_names:
                    sys.stderr.write("codex-mcp-proxy: routed " + ", ".join(routed_names) + "\n")
                self._respond(response.status, transformed, content_type)
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            content_type = exc.headers.get("Content-Type", "application/json")
            self._respond(exc.code, response_body, content_type)
        except urllib.error.URLError as exc:
            payload = json.dumps({"error": {"message": str(exc.reason)}}).encode()
            self._respond(502, payload, "application/json")

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class NamespaceProxyServer(ThreadingHTTPServer):
    """HTTP server carrying immutable upstream configuration."""

    def __init__(
        self,
        address: tuple[str, int],
        upstream: str,
        timeout: float,
    ) -> None:
        super().__init__(address, NamespaceProxyHandler)
        self.upstream = upstream.rstrip("/")
        self.timeout = timeout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--upstream", default="https://api.minimax.io")
    parser.add_argument("--timeout", type=float, default=7200.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = NamespaceProxyServer(
        (args.host, args.port),
        upstream=args.upstream,
        timeout=args.timeout,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
