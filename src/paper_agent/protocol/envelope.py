from __future__ import annotations

from typing import Any

from .errors import CommandError


ENVELOPE_SCHEMA_VERSION = "1"


def _meta(*, command: str, runtime_version: str, request_id: str) -> dict[str, str]:
    return {
        "command": command,
        "runtime_version": runtime_version,
        "request_id": request_id,
    }


def success_envelope(
    *, data: Any, command: str, runtime_version: str, request_id: str
) -> dict[str, Any]:
    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "success": True,
        "data": data,
        "meta": _meta(
            command=command,
            runtime_version=runtime_version,
            request_id=request_id,
        ),
    }


def error_envelope(
    *, error: CommandError, command: str, runtime_version: str, request_id: str
) -> dict[str, Any]:
    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "success": False,
        "error": {
            "code": error.code.value,
            "message": error.message,
            "details": error.details,
            "retryable": error.retryable,
        },
        "meta": _meta(
            command=command,
            runtime_version=runtime_version,
            request_id=request_id,
        ),
    }

