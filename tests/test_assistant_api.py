from __future__ import annotations

import json
from typing import Any

import httpx
from typer.testing import CliRunner

from paper_agent import cli
from paper_agent.clients import FrowangClient


def _client(handler) -> FrowangClient:
    return FrowangClient(
        api_key="pk_test_secret",
        base_url="https://example.test/paper-api/api/v1",
        transport=httpx.MockTransport(handler),
        max_get_retries=0,
    )


class _ChunkedStream(httpx.ByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def test_agentic_stream_parses_events_incrementally_and_sends_context() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=(
                'data: {"run_started":{"run_id":"r1"}}\n\n'
                ': ping\n\n'
                'data: {"content":"answer"}\n\n'
                'data: [DONE]\n\n'
            ),
        )

    with _client(handler) as client:
        events = list(
            client.stream_agentic_chat(
                "question",
                context={"active_paper": {"paper_id": "P-1"}},
            )
        )

    assert seen["path"] == "/paper-api/api/v1/chat/agentic"
    assert seen["body"] == {
        "message": "question",
        "conversation_id": None,
        "context": {"active_paper": {"paper_id": "P-1"}},
    }
    assert events == [{"run_started": {"run_id": "r1"}}, {"content": "answer"}]


def test_agentic_stream_rejects_an_unbounded_single_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text='data: {"content":"12345"}\n\n',
        )

    with _client(handler) as client:
        stream = client.stream_agentic_chat("question", max_event_bytes=4)
        try:
            next(stream)
        except Exception as exc:
            assert "exceeded the client limit" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("oversized SSE event was accepted")


def test_agentic_stream_handles_byte_boundaries_and_multibyte_text() -> None:
    wire = 'data: {"content":"你好"}\n\ndata: [DONE]\n\n'.encode("utf-8")
    chunks = [wire[:8], wire[8:9], wire[9:13], wire[13:]]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            stream=_ChunkedStream(chunks),
        )

    with _client(handler) as client:
        assert list(client.stream_agentic_chat("question")) == [{"content": "你好"}]


def test_agentic_stream_rejects_an_unterminated_oversized_line() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_ChunkedStream([b"data: ", b"12345"]),
        )

    with _client(handler) as client:
        stream = client.stream_agentic_chat("question", max_event_bytes=4)
        try:
            next(stream)
        except Exception as exc:
            assert "line exceeded" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("unterminated oversized SSE line was accepted")


def test_agentic_stream_requires_done_but_preserves_prior_events() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=_ChunkedStream([b'data: {"run_started":{"run_id":"r1"}}\n\n']),
        )

    with _client(handler) as client:
        stream = client.stream_agentic_chat("question")
        events = []
        try:
            events.extend(stream)
        except Exception as exc:
            assert "ended before [DONE]" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("clean EOF without DONE was accepted")

    assert events == [{"run_started": {"run_id": "r1"}}]


def test_agentic_stream_rejects_a_non_sse_success_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/json"}, json={})

    with _client(handler) as client:
        stream = client.stream_agentic_chat("question")
        try:
            next(stream)
        except Exception as exc:
            assert "not an SSE stream" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("non-SSE response was accepted")


def test_chat_json_wrappers_use_public_routes_and_payloads() -> None:
    calls: list[tuple[str, str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/retry"):
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text="data: [DONE]\n\n",
            )
        return httpx.Response(200, json={"success": True, "data": {}})

    with _client(handler) as client:
        client.list_chat_conversations(limit=3)
        client.get_chat_history("conv 1")
        client.stop_chat_run("run-1")
        client.delete_chat_conversation("conv-1")
        client.delete_chat_message("conv-1", "msg-1")
        list(client.retry_agentic_chat("conv-1", "msg-1"))

    assert calls[:5] == [
        ("GET", "/paper-api/api/v1/chat/conversations", None),
        ("GET", "/paper-api/api/v1/chat/conversations/conv 1/history", None),
        ("POST", "/paper-api/api/v1/chat/runs/run-1/stop", None),
        ("DELETE", "/paper-api/api/v1/chat/conversations/conv-1", None),
        ("DELETE", "/paper-api/api/v1/chat/conversations/conv-1/messages/msg-1", None),
    ]
    assert calls[5] == (
        "POST",
        "/paper-api/api/v1/chat/conversations/conv-1/retry",
        {"message_id": "msg-1"},
    )


def test_assistant_cli_emits_each_sse_event_without_collecting_stream(monkeypatch) -> None:
    class FakeAssistant:
        def ask(self, message: str, *, conversation_id=None, context=None):
            assert message == "hello"
            assert conversation_id is None
            assert context == {"page": 2}
            yield {"run_started": {"run_id": "r1"}}
            yield {"content": "answer"}

    monkeypatch.setattr(cli, "_assistant_service", lambda ctx: FakeAssistant())
    result = CliRunner().invoke(
        cli.app,
        ["assistant", "ask", "hello", "--context", '{"page":2}', "--json"],
    )

    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [line["data"] for line in lines] == [
        {"run_started": {"run_id": "r1"}},
        {"content": "answer"},
    ]
    assert all(line["meta"]["command"] == "assistant.ask" for line in lines)
