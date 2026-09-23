import json

import httpx
import pytest
from typer.testing import CliRunner

from paper_agent import cli
from paper_agent.clients.frowang import FrowangClient
from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services.library_service import LibraryService


@pytest.mark.parametrize("paper_id,base", [("P-1", "/papers/P-1"),
    ("collab~root~paper", "/collections/root/papers/paper")])
def test_cli_locate_add_and_stable_retry(monkeypatch, paper_id, base):
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload))
        data = {"candidates": [{"targetId": "a"*64}], "revision": "b"*64} if request.url.path.endswith("locate") else {"annotations": [{"id": "ann"}], "replayed": len(calls) > 2}
        return httpx.Response(200, json={"success": True, "data": data})
    with FrowangClient(api_key="test", base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(cli, "_library_service", lambda _: LibraryService(client))
        runner = CliRunner()
        result = runner.invoke(cli.app, ["library", "annotation", "locate", paper_id, "--quote", "important evidence", "--page", "5", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["data"]["candidates"][0]["targetId"] == "a"*64
        args = ["library", "annotation", "add", paper_id, "--quote", "important evidence", "--page", "5",
                "--target-id", "a"*64, "--revision", "b"*64, "--type", "underline", "--comment", "Reason", "--json"]
        first = runner.invoke(cli.app, args)
        second = runner.invoke(cli.app, args)
        assert first.exit_code == second.exit_code == 0, first.output
        assert json.loads(first.output)["meta"]["command"] == "library.annotation.add"
        assert calls[0][0] == base+"/annotations/locate"
        assert calls[1][0] == base+"/annotations"
        assert calls[1][1] == calls[2][1]
        assert calls[1][1]["type"] == "underline"
        assert json.loads(first.output)["data"]["request_id"] == calls[1][1]["request_id"]


def test_ambiguity_reaches_agent_with_candidates():
    def handler(request):
        return httpx.Response(409, json={"detail": {"code": "AMBIGUOUS_QUOTE", "message": "Multiple matches",
                               "revision": "b"*64, "candidates": [{"targetId": "a"*64, "prefix": "First"}]}})
    with FrowangClient(api_key="test", base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CommandError) as err:
            LibraryService(client).add_annotation("P-1", quote="evidence")
        assert err.value.code == ErrorCode.CONFLICT
        assert err.value.details["remote_code"] == "AMBIGUOUS_QUOTE"
        assert err.value.details["candidates"][0]["prefix"] == "First"


@pytest.mark.parametrize("options", [{"quote": " "}, {"quote": "x", "page": 0},
    {"quote": "x", "type": "delete"}, {"quote": "x", "color": "red"},
    {"quote": "x", "target_id": "unknown"}, {"quote": "x", "request_id": " "}])
def test_invalid_input_fails_before_network(options):
    with pytest.raises(CommandError) as err:
        LibraryService(None).add_annotation("P-1", **options)
    assert err.value.code == ErrorCode.USAGE_ERROR
