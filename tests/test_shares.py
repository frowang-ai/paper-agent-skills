"""Paper-share CLI, short-ID resolution, scoped routing and mutation errors."""
import json

import httpx
import pytest
from typer.testing import CliRunner

from paper_agent import cli
from paper_agent.clients import FrowangClient
from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services import LibraryService


@pytest.mark.parametrize("ref,base", [
    ("P-24r", "/papers/paper-uuid"),
    ("paper-uuid", "/papers/paper-uuid"),
    ("collab~root~paper-uuid", "/collections/root/papers/paper-uuid"),
])
def test_share_commands_use_api_key_and_correct_copy(monkeypatch, ref, base):
    calls = []

    def handler(request):
        assert request.headers["X-API-Key"] == "test-secret"
        assert "Authorization" not in request.headers
        calls.append((request.method, request.url.path))
        if request.url.path == "/papers/P-24r":
            return httpx.Response(200, json={"success": True, "data": {"paper_id": "paper-uuid"}})
        if request.method == "POST":
            assert json.loads(request.content) == {"kind": "claim"}
            data = {"share_id": "share-1", "share_url": "https://frowang.com/s/token", "kind": "claim"}
        elif request.method == "GET":
            data = [{"share_id": "share-1", "status": "active", "kind": "claim"}]
        else:
            data = None
        return httpx.Response(200, json={"success": True, "data": data})

    with FrowangClient("test-secret", "https://test", transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(cli, "_library_service", lambda _: LibraryService(client))
        runner = CliRunner()
        for command, extra in (("create", []), ("list", []), ("revoke", ["share-1"])):
            result = runner.invoke(cli.app, ["library", "share", command, ref, *extra, "--json"])
            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["success"] is True
            assert payload["meta"]["command"] == "library.share." + command
            assert "test-secret" not in result.output
            if command == "create":
                assert payload["data"]["share_url"] == "https://frowang.com/s/token"
        assert ("POST", base + "/shares") in calls
        assert ("GET", base + "/shares") in calls
        assert ("DELETE", base + "/shares/share-1") in calls


def test_invalid_share_kind_fails_before_network():
    with pytest.raises(CommandError) as exc:
        LibraryService(None).create_share("P-1", kind="permanent")
    assert exc.value.code == ErrorCode.USAGE_ERROR


@pytest.mark.parametrize("status,code", [(401, ErrorCode.AUTH_INVALID), (404, ErrorCode.NOT_FOUND),
    (409, ErrorCode.CONFLICT), (429, ErrorCode.REMOTE_ERROR), (500, ErrorCode.REMOTE_ERROR)])
def test_share_creation_errors_are_not_retried(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"detail": {"code": "SHARE_TEST", "message": "denied"}})

    with FrowangClient("test-secret", "https://test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CommandError) as exc:
            LibraryService(client).create_share("paper-uuid")
    assert exc.value.code == code
    assert len(calls) == 1


def test_share_creation_timeout_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("unknown outcome", request=request)

    with FrowangClient("test-secret", "https://test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CommandError) as exc:
            LibraryService(client).create_share("paper-uuid")
    assert exc.value.code == ErrorCode.NETWORK_ERROR
    assert len(calls) == 1


def test_share_info_and_encoded_revoke_id():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True, "data": {}})

    with FrowangClient("test-secret", "https://test", transport=httpx.MockTransport(handler)) as client:
        service = LibraryService(client)
        service.create_share("paper-uuid", kind="info")
        service.revoke_share("paper-uuid", "share/other")
    assert json.loads(calls[0].content) == {"kind": "info"}
    assert calls[1].url.raw_path == b"/papers/paper-uuid/shares/share%2Fother"
