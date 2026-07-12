from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from paper_agent.clients import FrowangClient
from paper_agent.protocol import CommandError, ErrorCode, ExitCode


def _client(handler, *, max_get_retries: int = 0) -> FrowangClient:
    return FrowangClient(
        api_key="pk_test_secret",
        base_url="https://example.test/paper-api/api/v1",
        transport=httpx.MockTransport(handler),
        max_get_retries=max_get_retries,
    )


def test_client_sends_auth_user_agent_and_decodes_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "pk_test_secret"
        assert request.headers["User-Agent"].startswith("paper-agent/")
        return httpx.Response(200, json={"success": True, "data": {"papers": []}})

    with _client(handler) as client:
        result = client.request_json("GET", "/papers")

    assert result["data"] == {"papers": []}


def test_client_retries_safe_get_after_server_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, json={"detail": "temporarily unavailable"})
        return httpx.Response(200, json={"success": True, "data": {"ok": True}})

    with _client(handler, max_get_retries=1) as client:
        result = client.request_json("GET", "/papers")

    assert attempts == 2
    assert result["data"]["ok"] is True


@pytest.mark.parametrize(
    ("status", "detail", "code", "exit_code"),
    [
        (401, {"code": "INVALID_API_KEY", "message": "bad key"}, ErrorCode.AUTH_INVALID, ExitCode.CONFIG_OR_AUTH),
        (404, {"code": "NOT_FOUND", "message": "missing"}, ErrorCode.NOT_FOUND, ExitCode.RESOURCE_STATE),
        (404, {"code": "NOT_READY", "message": "processing"}, ErrorCode.NOT_READY, ExitCode.RESOURCE_STATE),
        (409, "conflict", ErrorCode.CONFLICT, ExitCode.CONFLICT),
        (500, "failed", ErrorCode.REMOTE_ERROR, ExitCode.NETWORK_OR_REMOTE),
    ],
)
def test_client_maps_http_failures(
    status: int,
    detail: object,
    code: ErrorCode,
    exit_code: ExitCode,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": detail})

    with _client(handler) as client, pytest.raises(CommandError) as caught:
        client.request_json("POST", "/papers/P-1/reprocess")

    assert caught.value.code == code
    assert caught.value.exit_code == exit_code
    assert "pk_test_secret" not in caught.value.message
    assert "pk_test_secret" not in json.dumps(caught.value.details)


def test_client_maps_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot connect", request=request)

    with _client(handler) as client, pytest.raises(CommandError) as caught:
        client.request_json("GET", "/papers")

    assert caught.value.code == ErrorCode.NETWORK_ERROR
    assert caught.value.retryable is True


def test_download_asset_encodes_path_and_writes_atomically(tmp_path: Path) -> None:
    seen_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.raw_path.decode("ascii")
        return httpx.Response(200, content=b"paper content")

    destination = tmp_path / "paper.md"
    with _client(handler) as client:
        result = client.download_asset(
            "/paper-api/outputs/task/file name & notes.md",
            destination,
        )

    assert "%20" in seen_path and "%26" in seen_path
    assert destination.read_bytes() == b"paper content"
    assert result.path == destination.resolve()
    assert result.bytes_written == len(b"paper content")
    assert len(result.sha256) == 64


def test_download_asset_rejects_foreign_origin(tmp_path: Path) -> None:
    with _client(lambda request: httpx.Response(200)) as client:
        with pytest.raises(CommandError) as caught:
            client.download_asset(
                "https://attacker.test/paper-api/outputs/file.md",
                tmp_path / "file.md",
            )

    assert caught.value.code == ErrorCode.PERMISSION_DENIED


def test_download_asset_normalizes_backend_root_outputs_path(tmp_path: Path) -> None:
    seen_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.path
        return httpx.Response(200, content=b"layout")

    with _client(handler) as client:
        client.download_asset("/outputs/task-1/layout.json", tmp_path / "layout.json")

    assert seen_path == "/paper-api/outputs/task-1/layout.json"
