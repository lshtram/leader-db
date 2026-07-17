#!/usr/bin/env python3
"""Serve repository design reviews through a read-only localhost server."""

from __future__ import annotations

import argparse
import functools
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import IO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAGE = "docs/design-reviews/ruler-analysis-flow.html"
VIEWABLE_ROOTS = frozenset(
    {".agents", "configs", "docs", "research", "scripts", "src", "tests"}
)
VIEWABLE_ROOT_FILES = frozenset({"AGENTS.md", "README.md", "pyproject.toml"})


class ReadOnlyRepositoryHandler(SimpleHTTPRequestHandler):
    """Serve files from the repository and reject mutation methods explicitly."""

    def do_POST(self) -> None:
        self.send_error(405, "read-only server")

    def do_PUT(self) -> None:
        self.send_error(405, "read-only server")

    def do_DELETE(self) -> None:
        self.send_error(405, "read-only server")

    def send_head(self) -> IO[bytes] | None:
        """Reject paths outside the source/documentation allowlist."""

        translated = Path(self.translate_path(self.path)).resolve()
        try:
            relative = translated.relative_to(PROJECT_ROOT)
        except ValueError:
            self.send_error(404, "not found")
            return None
        first = relative.parts[0] if relative.parts else ""
        allowed = first in VIEWABLE_ROOTS or relative.as_posix() in VIEWABLE_ROOT_FILES
        hidden = any(part.startswith(".") for part in relative.parts if part != ".agents")
        if not allowed or hidden:
            self.send_error(404, "not found")
            return None
        return super().send_head()

    def log_message(self, format: str, *args: object) -> None:
        """Keep terminal output concise while preserving request visibility."""

        super().log_message(format, *args)

    def end_headers(self) -> None:
        """Expose the local checkout root for optional editor deep links."""

        self.send_header("X-Repository-Root", str(PROJECT_ROOT))
        super().end_headers()


def build_server(*, host: str, port: int) -> ThreadingHTTPServer:
    """Build a static server constrained to the resolved repository root."""

    handler = functools.partial(ReadOnlyRepositoryHandler, directory=str(PROJECT_ROOT))
    return ThreadingHTTPServer((host, port), handler)


def parse_args() -> argparse.Namespace:
    """Parse launcher arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--page", default=DEFAULT_PAGE)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def resolve_review_page(page: str) -> tuple[Path, str]:
    """Return one existing review page contained by the repository root."""

    candidate = (PROJECT_ROOT / page.lstrip("/")).resolve()
    try:
        relative = candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("review page must remain inside the repository") from exc
    if not candidate.is_file():
        raise ValueError(f"review page does not exist inside the repository: {relative}")
    return candidate, relative.as_posix()


def main() -> None:
    """Start the server and optionally open the requested review page."""

    args = parse_args()
    try:
        _, page = resolve_review_page(args.page)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    server = build_server(host=args.host, port=args.port)
    url = f"http://{args.host}:{server.server_port}/{page}"
    print(f"Serving read-only repository viewer at {url}")
    if not args.no_browser:
        threading.Timer(0.25, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
