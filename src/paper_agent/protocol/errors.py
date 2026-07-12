from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Mapping, Optional

from .exit_codes import ExitCode


class ErrorCode(str, Enum):
    USAGE_ERROR = "USAGE_ERROR"
    CONFIG_INVALID = "CONFIG_INVALID"
    AUTH_MISSING = "AUTH_MISSING"
    AUTH_INVALID = "AUTH_INVALID"
    NOT_FOUND = "NOT_FOUND"
    NOT_READY = "NOT_READY"
    NETWORK_ERROR = "NETWORK_ERROR"
    REMOTE_ERROR = "REMOTE_ERROR"
    WORKSPACE_INVALID = "WORKSPACE_INVALID"
    CONFLICT = "CONFLICT"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    LOCAL_IO_ERROR = "LOCAL_IO_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class CommandError(Exception):
    """A public, machine-readable command failure."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        exit_code: ExitCode,
        details: Optional[Mapping[str, Any]] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = deepcopy(dict(details or {}))
        self.retryable = retryable
