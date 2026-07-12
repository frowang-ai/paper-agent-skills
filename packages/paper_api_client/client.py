"""Compatibility imports for callers migrating to :mod:`paper_agent`."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional

from dotenv import dotenv_values

from paper_agent.clients import FrowangClient
from paper_agent.config.credentials import ResolvedCredential
from paper_agent.protocol import CommandError, ErrorCode, ExitCode


DEFAULT_BASE_URL = "https://frowang.com/paper-api/api/v1"


class PaperClient(FrowangClient):
    """Deprecated name retaining the legacy ``request`` method."""

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Any = None,
        files: Any = None,
        data: Any = None,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        return self.request_json(
            method,
            path,
            params=params,
            json_body=json_body,
            files=files,
            data=data,
            timeout_seconds=timeout,
        )


def _credential_from(values: Mapping[str, object], source: str) -> Optional[ResolvedCredential]:
    current = values.get("FROWANG_API_KEY")
    legacy = values.get("PAPER_API_KEY")
    current_value = current.strip() if isinstance(current, str) else ""
    legacy_value = legacy.strip() if isinstance(legacy, str) else ""
    if current_value and legacy_value and current_value != legacy_value:
        raise CommandError(
            code=ErrorCode.CONFIG_INVALID,
            message="Conflicting Frowang API key aliases",
            exit_code=ExitCode.CONFIG_OR_AUTH,
            details={"source": source},
        )
    if current_value:
        return ResolvedCredential(current_value, f"{source}:FROWANG_API_KEY")
    if legacy_value:
        return ResolvedCredential(legacy_value, f"{source}:PAPER_API_KEY")
    return None


def load_api_key(
    explicit: Optional[str],
    *,
    skill_env_path: Optional[Path] = None,
    scripts_env_path: Optional[Path] = None,
    legacy_env_path: Optional[Path] = None,
) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    resolved = _credential_from(os.environ, "environment")
    if resolved:
        return resolved.value
    for path in (skill_env_path, scripts_env_path, legacy_env_path):
        if path and path.is_file():
            resolved = _credential_from(dotenv_values(path), str(path))
            if resolved:
                return resolved.value
    raise CommandError(
        code=ErrorCode.AUTH_MISSING,
        message="Frowang API key is not configured",
        exit_code=ExitCode.CONFIG_OR_AUTH,
    )


def load_base_url(
    explicit: Optional[str],
    *,
    skill_env_path: Optional[Path] = None,
    scripts_env_path: Optional[Path] = None,
    legacy_env_path: Optional[Path] = None,
) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    environment = os.environ.get("PAPER_API_BASE_URL", "").strip()
    if environment:
        return environment
    for path in (skill_env_path, scripts_env_path, legacy_env_path):
        if path and path.is_file():
            value = dotenv_values(path).get("PAPER_API_BASE_URL")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return DEFAULT_BASE_URL
