from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import httpx
from packaging.version import InvalidVersion, Version

from paper_agent.config import AppPaths

PYPI_URL = "https://pypi.org/pypi/paper-agent-skills/json"
CACHE_FILENAME = "update_check.json"
CACHE_TTL_SECONDS = 24 * 60 * 60
DISABLE_ENV = "PAPER_AGENT_DISABLE_UPDATE_CHECK"
_TIMEOUT_SECONDS = 3.0


def _default_fetcher() -> str:
    response = httpx.get(PYPI_URL, timeout=_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    return str(payload["info"]["version"])


class UpdateCheckService:
    """Cached, non-blocking PyPI update check.

    The check never raises: network failures degrade to a stale cache hit or
    an ``unknown`` status so the calling command always succeeds.
    """

    def __init__(
        self,
        paths: AppPaths,
        *,
        current_version: str,
        env: Optional[Mapping[str, str]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        fetcher: Optional[Callable[[], str]] = None,
    ) -> None:
        self._cache_file = paths.cache_dir / CACHE_FILENAME
        self._current_version = current_version
        self._env = env if env is not None else os.environ
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._fetcher = fetcher or _default_fetcher

    def check(self, *, refresh: bool = False) -> dict[str, Any]:
        base: dict[str, Any] = {
            "current_version": self._current_version,
            "update_available": False,
        }
        if self._env.get(DISABLE_ENV) == "1":
            return {**base, "status": "disabled", "source": "disabled"}

        cached = self._read_cache()
        if cached is not None and not refresh and not self._is_stale(cached):
            return self._result(cached["latest_version"], cached["checked_at"], "cache")

        try:
            latest = self._fetcher()
        except Exception:
            if cached is not None:
                result = self._result(cached["latest_version"], cached["checked_at"], "cache")
                result["stale"] = True
                return result
            return {**base, "status": "unknown", "source": "network", "reason": "network_error"}

        checked_at = self._clock().isoformat()
        self._write_cache({"checked_at": checked_at, "latest_version": latest})
        return self._result(latest, checked_at, "network")

    def _result(self, latest: str, checked_at: str, source: str) -> dict[str, Any]:
        try:
            update_available = Version(latest) > Version(self._current_version)
        except InvalidVersion:
            update_available = False
        return {
            "status": "update_available" if update_available else "ok",
            "current_version": self._current_version,
            "latest_version": latest,
            "update_available": update_available,
            "checked_at": checked_at,
            "source": source,
        }

    def _is_stale(self, cached: Mapping[str, Any]) -> bool:
        try:
            checked_at = datetime.fromisoformat(str(cached["checked_at"]))
        except (KeyError, ValueError):
            return True
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        age = (self._clock() - checked_at).total_seconds()
        return age >= CACHE_TTL_SECONDS

    def _read_cache(self) -> Optional[dict[str, Any]]:
        try:
            payload = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or "latest_version" not in payload:
            return None
        return payload

    def _write_cache(self, payload: Mapping[str, Any]) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._cache_file.parent,
                delete=False,
            ) as temporary:
                json.dump(dict(payload), temporary)
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self._cache_file)
        except OSError:
            pass
