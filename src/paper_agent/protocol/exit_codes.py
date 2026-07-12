from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    INTERNAL_ERROR = 1
    USAGE_ERROR = 2
    CONFIG_OR_AUTH = 3
    RESOURCE_STATE = 4
    NETWORK_OR_REMOTE = 5
    CONFLICT = 6
    LOCAL_IO_OR_INTEGRITY = 7

