from __future__ import annotations

import importlib.util
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "serve_design_reviews.py"
    spec = importlib.util.spec_from_file_location("serve_design_reviews", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_server_serves_review_and_rejects_writes() -> None:
    module = _load_module()
    server = module.build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(
            f"{base}/docs/design-reviews/ruler-analysis-flow.html"
        ) as response:
            assert response.status == 200
            assert b"Ruler analysis" in response.read()
            assert response.headers["X-Repository-Root"] == str(module.PROJECT_ROOT)

        head = urllib.request.Request(f"{base}/AGENTS.md", method="HEAD")
        with urllib.request.urlopen(head) as response:
            assert response.status == 200
            assert response.read() == b""

        research_artifact = module.PROJECT_ROOT / "research" / "viewer-test.json"
        research_artifact.parent.mkdir(exist_ok=True)
        research_artifact.write_text('{"kind":"real-runtime-artifact"}', encoding="utf-8")
        try:
            with urllib.request.urlopen(f"{base}/research/viewer-test.json") as response:
                assert response.status == 200
                assert response.read() == b'{"kind":"real-runtime-artifact"}'
        finally:
            research_artifact.unlink(missing_ok=True)

        for method in ("POST", "PUT", "DELETE"):
            request = urllib.request.Request(f"{base}/AGENTS.md", data=b"x", method=method)
            try:
                urllib.request.urlopen(request)
            except urllib.error.HTTPError as exc:
                assert exc.code == 405
            else:
                raise AssertionError(f"{method} unexpectedly succeeded")

        for private_path in (".git/config", "data/catalog/leaders_db.sqlite", ".env"):
            try:
                urllib.request.urlopen(f"{base}/{private_path}")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
            else:
                raise AssertionError(f"private path unexpectedly served: {private_path}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_rejects_symlink_escape() -> None:
    module = _load_module()
    original_root = module.PROJECT_ROOT
    with tempfile.TemporaryDirectory(dir=original_root / "tmp") as directory:
        fake_root = Path(directory)
        (fake_root / "docs").mkdir()
        outside = fake_root.parent / "outside-viewer-secret.txt"
        outside.write_text("secret", encoding="utf-8")
        (fake_root / "docs" / "escape.txt").symlink_to(outside)
        module.PROJECT_ROOT = fake_root.resolve()
        server = module.build_server(host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/docs/escape.txt"
            try:
                urllib.request.urlopen(url)
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
            else:
                raise AssertionError("symlink escape unexpectedly succeeded")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            module.PROJECT_ROOT = original_root
            outside.unlink(missing_ok=True)


def test_review_page_must_remain_inside_repository() -> None:
    module = _load_module()
    try:
        module.resolve_review_page("../../etc/passwd")
    except ValueError as exc:
        assert "inside the repository" in str(exc)
    else:
        raise AssertionError("outside review page unexpectedly accepted")
