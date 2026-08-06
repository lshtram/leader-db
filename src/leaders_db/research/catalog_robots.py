"""Thread-safe origin-level robots policy cache for catalogue acquisition."""

from __future__ import annotations

from threading import Lock
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests


class RobotsPolicyCache:
    """Fetch one robots policy per origin and reuse it for every candidate URL."""

    def __init__(self, *, user_agent: str, timeout_seconds: float) -> None:
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._policies: dict[str, RobotFileParser | None] = {}
        self._locks: dict[str, Lock] = {}
        self._guard = Lock()

    def allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._guard:
            lock = self._locks.setdefault(origin, Lock())
        with lock:
            if origin not in self._policies:
                self._policies[origin] = self._fetch(origin)
            policy = self._policies[origin]
        return True if policy is None else policy.can_fetch(self._user_agent, url)

    def _fetch(self, origin: str) -> RobotFileParser | None:
        try:
            response = requests.get(
                f"{origin}/robots.txt",
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout_seconds,
            )
        except requests.RequestException:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


__all__ = ["RobotsPolicyCache"]
