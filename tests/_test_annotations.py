from __future__ import annotations

import pytest

from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services import LibraryService


def _annotation(**overrides):
    base = {
        "id": "ann-1",
        "type": "highlight",
        "color": "#ffd400",
        "pageIndex": 3,
        "rects": [[100, 200, 300, 220]],
        "text": "selected text",
        "comment": "existing",
        "source": "user",
        "createdAt": "2026-08-01T10:00:00.000000",
        "updatedAt": "2026-08-01T10:00:00.000000",
        "isDeleted": False,
        "sortKey": "00003...",
    }
    base.update(overrides)
    return base


class _FakeClient:
    def __init__(self, annotations=None, server_time="2026-08-17T12:00:00.000000"):
        self.calls = []
        self._annotations = (
            annotations if annotations is not None else [_annotation()]
        )
        self._server_time = server_time

    def request_json(self, method: str, path: str, **kwargs):
        self.calls.append({"method": method, "path": path, **kwargs})
        if method == "GET":
            return {
                "success": True,
                "data": {
                    "annotations": self._annotations,
                    "serverTime": self._server_time,
                },
            }
        return {"success": True, "data": {"accepted": 1, "deleted": 0}}


def test_list_annotations_passes_since_param() -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]

    data = service.list_annotations("P-1", since="2026-08-01T00:00:00.000000")

    assert client.calls[0] == {
        "method": "GET",
        "path": "/papers/P-1/annotations",
        "params": {"since": "2026-08-01T00:00:00.000000"},
    }
    assert data["annotations"][0]["id"] == "ann-1"


def test_list_annotations_omits_since_when_absent() -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]

    service.list_annotations("P-1")

    assert client.calls[0]["params"] == {}


def test_append_comment_merges_and_upserts_via_sync() -> None:
    client = _FakeClient(annotations=[_annotation()])
    service = LibraryService(client)  # type: ignore[arg-type]

    service.append_annotation_comment("P-1", "ann-1", "agent insight")

    sync = client.calls[1]
    assert sync["method"] == "POST"
    assert sync["path"] == "/papers/P-1/annotations/sync"
    upsert = sync["json_body"]["upserts"][0]
    assert upsert["comment"] == "existing\nagent insight"
    # 服务器时钟 +1s，保证 LWW 覆盖
    assert upsert["updatedAt"] == "2026-08-17T12:00:01.000000"
    # 响应模型没有的字段不回传
    assert "isDeleted" not in upsert
    assert "sortKey" not in upsert


def test_append_comment_first_comment_has_no_leading_newline() -> None:
    client = _FakeClient(annotations=[_annotation(comment="")])
    service = LibraryService(client)  # type: ignore[arg-type]

    service.append_annotation_comment("P-1", "ann-1", "first!")

    upsert = client.calls[1]["json_body"]["upserts"][0]
    assert upsert["comment"] == "first!"


def test_append_comment_unknown_annotation_raises_not_found() -> None:
    client = _FakeClient(annotations=[_annotation()])
    service = LibraryService(client)  # type: ignore[arg-type]

    with pytest.raises(CommandError) as caught:
        service.append_annotation_comment("P-1", "ann-missing", "text")
    assert caught.value.code == ErrorCode.NOT_FOUND
    # 未发起任何写请求
    assert len(client.calls) == 1


def test_append_comment_rejects_blank_text() -> None:
    client = _FakeClient(annotations=[_annotation()])
    service = LibraryService(client)  # type: ignore[arg-type]

    with pytest.raises(CommandError) as caught:
        service.append_annotation_comment("P-1", "ann-1", "   ")
    assert caught.value.code == ErrorCode.USAGE_ERROR
