"""Collaborative-copy (collab~) routing tests.

A reference like ``collab~<root_key>~<paper_id>`` must reach the workspace
routes (``/collections/{root}/papers/{pid}/...``) so notes/annotations/tags
land on the shared copy instead of the private library, and so operations
without a workspace equivalent fail loudly instead of hitting the wrong copy.
"""
from __future__ import annotations

import pytest

from paper_agent.collab import (
    is_collab_id,
    paper_base,
    split_collab_id,
    underlying_paper_id,
)
from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services import LibraryService

COLLAB_ID = "collab~root-key-1~paper-uuid-9"
BASE = "/collections/root-key-1/papers/paper-uuid-9"


class _FakeClient:
    def __init__(self, get_responses: dict[str, object] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.get_responses = get_responses or {}

    def request_json(self, method: str, path: str, **kwargs):
        self.calls.append({"method": method, "path": path, **kwargs})
        if method == "GET" and path in self.get_responses:
            return self.get_responses[path]
        return {"success": True, "data": {"method": method, "path": path}}


def _service(client: _FakeClient) -> LibraryService:
    return LibraryService(client)  # type: ignore[arg-type]


def test_split_collab_id_parses_three_segments() -> None:
    assert split_collab_id(COLLAB_ID) == ("root-key-1", "paper-uuid-9")
    assert split_collab_id("P-1cm") is None
    assert split_collab_id("ee4c1f82-7792-4669-927e-dae3d2f43971") is None
    assert is_collab_id(COLLAB_ID) is True
    assert is_collab_id("P-1cm") is False
    assert underlying_paper_id(COLLAB_ID) == "paper-uuid-9"
    assert underlying_paper_id("P-1cm") == "P-1cm"


def test_split_collab_id_rejects_malformed() -> None:
    with pytest.raises(CommandError) as caught:
        split_collab_id("collab~only-two")
    assert caught.value.code == ErrorCode.USAGE_ERROR
    with pytest.raises(CommandError):
        split_collab_id("collab~root~")


def test_paper_base_routes_collab_to_workspace() -> None:
    assert paper_base(COLLAB_ID) == BASE
    assert paper_base("P-1cm") == "/papers/P-1cm"


def test_show_uses_workspace_detail_for_collab() -> None:
    client = _FakeClient()
    _service(client).show(COLLAB_ID)
    assert client.calls[0]["path"] == BASE


def test_note_list_and_add_use_workspace_records() -> None:
    client = _FakeClient()
    service = _service(client)

    service.list_notes(COLLAB_ID)
    assert client.calls[0]["method"] == "GET"
    assert client.calls[0]["path"] == f"{BASE}/notes"

    service.add_note(COLLAB_ID, "数据部分疑点")
    assert client.calls[1] == {
        "method": "POST",
        "path": f"{BASE}/notes",
        "json_body": {"content": "数据部分疑点"},
    }


def test_note_add_private_keeps_query_param_contract() -> None:
    client = _FakeClient()
    _service(client).add_note("P-1", "important")
    assert client.calls[0] == {
        "method": "POST",
        "path": "/papers/P-1/notes",
        "params": {"content": "important"},
    }


def test_tags_route_to_workspace_for_collab() -> None:
    client = _FakeClient()
    service = _service(client)

    service.add_tags(COLLAB_ID, ["econ"])
    assert client.calls[0]["path"] == f"{BASE}/tags"
    assert client.calls[0]["json_body"] == ["econ"]

    service.set_tags(COLLAB_ID, ["a", "b"])
    assert client.calls[1]["method"] == "PUT"
    assert client.calls[1]["path"] == f"{BASE}/tags"

    service.remove_tag(COLLAB_ID, "a")
    assert client.calls[2]["method"] == "DELETE"
    assert client.calls[2]["path"] == f"{BASE}/tags/a"


def test_update_metadata_uses_workspace_patch() -> None:
    client = _FakeClient()
    _service(client).update_metadata(COLLAB_ID, {"title": "T", "year": None})
    assert client.calls[0] == {
        "method": "PATCH",
        "path": f"{BASE}/metadata",
        "json_body": {"title": "T"},
    }


def test_reprocess_maps_to_workspace_action() -> None:
    client = _FakeClient()
    _service(client).reprocess(COLLAB_ID)
    assert client.calls[0] == {"method": "POST", "path": f"{BASE}/actions/reprocess"}


def test_delete_rejected_for_collab() -> None:
    client = _FakeClient()
    with pytest.raises(CommandError) as caught:
        _service(client).delete(COLLAB_ID)
    assert caught.value.code == ErrorCode.USAGE_ERROR
    assert client.calls == []


def test_read_only_fallback_uses_underlying_paper() -> None:
    client = _FakeClient()
    service = _service(client)

    service.assets(COLLAB_ID)
    assert client.calls[0]["path"] == "/papers/paper-uuid-9/assets"


def test_get_content_fallback_uses_underlying_paper() -> None:
    client = _FakeClient(
        get_responses={
            "/papers/paper-uuid-9/fulltext": {
                "success": True,
                "data": {"content": "full text"},
            }
        }
    )
    service = _service(client)
    assert service.get_content(COLLAB_ID, "fulltext") == "full text"
    assert client.calls[0]["path"] == "/papers/paper-uuid-9/fulltext"


def test_list_annotations_collab_full_snapshot_no_since() -> None:
    client = _FakeClient()
    service = _service(client)

    service.list_annotations(COLLAB_ID)
    assert client.calls[0]["path"] == f"{BASE}/annotations"

    with pytest.raises(CommandError) as caught:
        service.list_annotations(COLLAB_ID, since="2026-08-01T00:00:00.000000")
    assert caught.value.code == ErrorCode.USAGE_ERROR


def _annotation(annotation_id: str, comment: str = "") -> dict[str, object]:
    return {
        "id": annotation_id,
        "type": "highlight",
        "color": "#ffd400",
        "pageIndex": 0,
        "rects": [],
        "text": "selected",
        "comment": comment,
        "source": "user",
        "author_id": "758",
        "author_name": "Fro",
        "isDeleted": False,
    }


def test_append_annotation_comment_collab_syncs_and_verifies() -> None:
    snapshot = {
        "success": True,
        "data": {"annotations": [_annotation("ann-1", "orig")], "fullSnapshot": True},
    }
    updated = {
        "success": True,
        "data": {
            "annotations": [_annotation("ann-1", "orig\nagent note")],
            "fullSnapshot": True,
        },
    }
    responses = {f"{BASE}/annotations": [snapshot, updated]}

    class _SeqClient(_FakeClient):
        def request_json(self, method: str, path: str, **kwargs):
            self.calls.append({"method": method, "path": path, **kwargs})
            if method == "GET" and path in responses:
                return responses[path].pop(0)
            return {"success": True, "data": {"accepted": 1, "deleted": 0}}

    seq_client = _SeqClient()
    service = _service(seq_client)
    service.append_annotation_comment(COLLAB_ID, "ann-1", "agent note")

    sync_call = next(c for c in seq_client.calls if c["path"].endswith("/annotations/sync"))
    upsert = sync_call["json_body"]["upserts"][0]
    assert upsert["comment"] == "orig\nagent note"
    # 服务端字段不得回传
    assert "author_id" not in upsert
    assert "isDeleted" not in upsert


# ── 协作关系管理：邀请 / 申请审批 / 成员（0.9.4） ─────────────────────


def test_collab_invite_and_join_request_paths() -> None:
    client = _FakeClient()
    service = _service(client)

    service.create_collab_invite("C-38")
    assert client.calls[0] == {"method": "POST", "path": "/collections/C-38/collab-invites"}

    service.collab_invite_status("C-38")
    assert client.calls[1] == {"method": "GET", "path": "/collections/C-38/collab-invites"}

    service.revoke_collab_invite("C-38", "inv-1")
    assert client.calls[2] == {
        "method": "DELETE",
        "path": "/collections/C-38/collab-invites/inv-1",
    }

    service.collab_invite_preview("tok abc")
    assert client.calls[3] == {"method": "GET", "path": "/collab-invites/tok%20abc"}

    service.apply_collab_invite("tok")
    assert client.calls[4] == {"method": "POST", "path": "/collab-invites/tok/apply"}


def test_collab_join_requests_and_members_paths() -> None:
    client = _FakeClient()
    service = _service(client)

    service.list_join_requests("C-38")
    assert client.calls[0]["path"] == "/collections/C-38/join-requests"
    assert client.calls[0]["params"] == {}

    service.list_join_requests("C-38", status=" Pending ")
    assert client.calls[1]["params"] == {"status": "pending"}

    with pytest.raises(CommandError) as caught:
        service.list_join_requests("C-38", status="bogus")
    assert caught.value.code == ErrorCode.USAGE_ERROR

    service.approve_join_request("C-38", "req-1")
    assert client.calls[2]["path"] == "/collections/C-38/join-requests/req-1/approve"

    service.approve_all_join_requests("C-38")
    assert client.calls[3]["path"] == "/collections/C-38/join-requests/approve-all"

    service.reject_join_request("C-38", "req-2")
    assert client.calls[4]["path"] == "/collections/C-38/join-requests/req-2/reject"

    service.list_collab_members("C-38")
    assert client.calls[5] == {"method": "GET", "path": "/collections/C-38/members"}

    service.remove_collab_member("C-38", "761")
    assert client.calls[6] == {"method": "DELETE", "path": "/collections/C-38/members/761"}

    service.leave_collab_collection("C-38")
    assert client.calls[7] == {"method": "POST", "path": "/collections/C-38/leave"}

    service.collab_info("C-38")
    assert client.calls[8] == {"method": "GET", "path": "/collections/C-38/collab-info"}

    service.collab_pending_summary()
    assert client.calls[9] == {"method": "GET", "path": "/collab-pending-summary"}


def test_append_annotation_comment_collab_rejected_when_not_author() -> None:
    import copy

    def _snapshot() -> dict[str, object]:
        return {
            "success": True,
            "data": {
                "annotations": [_annotation("ann-1", "orig")],
                "fullSnapshot": True,
            },
        }

    class _StaticClient(_FakeClient):
        def request_json(self, method: str, path: str, **kwargs):
            self.calls.append({"method": method, "path": path, **kwargs})
            if method == "GET":
                return copy.deepcopy(_snapshot())  # 服务端拒绝写入，快照不变
            return {"success": True, "data": {"accepted": 1, "deleted": 0}}

    service = _service(_StaticClient())
    with pytest.raises(CommandError) as caught:
        service.append_annotation_comment(COLLAB_ID, "ann-1", "agent note")
    assert caught.value.code == ErrorCode.REMOTE_ERROR
