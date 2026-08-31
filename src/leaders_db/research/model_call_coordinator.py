"""Thread-safe coordination for fail-stopped model calls."""

from __future__ import annotations

from threading import Lock


class ModelCallCoordinator:
    """Atomically separate authorized in-flight calls from post-failure launches."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._failed = False
        self._in_flight = 0

    def authorize_launch(self) -> None:
        with self._lock:
            if self._failed:
                raise RuntimeError("model call launch blocked after material failure")
            self._in_flight += 1

    def ensure_open(self) -> None:
        """Reject work that must not wait or reserve after a material failure."""

        with self._lock:
            if self._failed:
                raise RuntimeError("model call launch blocked after material failure")

    def complete_call(self) -> None:
        with self._lock:
            self._in_flight -= 1

    def publish_failure(self) -> None:
        with self._lock:
            self._failed = True

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight
