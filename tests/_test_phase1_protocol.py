from __future__ import annotations

from paper_agent.protocol import CommandError, ErrorCode, ExitCode, error_envelope, success_envelope


def test_success_envelope_has_stable_schema() -> None:
    payload = success_envelope(
        data={"value": 1},
        command="test.command",
        runtime_version="0.2.0",
        request_id="request-1",
    )

    assert payload == {
        "schema_version": "1",
        "success": True,
        "data": {"value": 1},
        "meta": {
            "command": "test.command",
            "runtime_version": "0.2.0",
            "request_id": "request-1",
        },
    }


def test_error_envelope_and_command_error_are_machine_readable() -> None:
    error = CommandError(
        code=ErrorCode.CONFIG_INVALID,
        message="bad config",
        exit_code=ExitCode.CONFIG_OR_AUTH,
        details={"field": "schema_version"},
        retryable=False,
    )

    payload = error_envelope(
        error=error,
        command="config.show",
        runtime_version="0.2.0",
        request_id="request-2",
    )

    assert payload["success"] is False
    assert payload["error"] == {
        "code": "CONFIG_INVALID",
        "message": "bad config",
        "details": {"field": "schema_version"},
        "retryable": False,
    }
    assert error.exit_code == ExitCode.CONFIG_OR_AUTH


def test_command_error_copies_details() -> None:
    details = {"nested": {"value": 1}}
    error = CommandError(
        code=ErrorCode.INTERNAL_ERROR,
        message="failed",
        exit_code=ExitCode.INTERNAL_ERROR,
        details=details,
    )
    details["nested"]["value"] = 2

    assert error.details == {"nested": {"value": 1}}

