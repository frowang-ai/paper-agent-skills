from __future__ import annotations

from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services import LibraryService


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def request_json(self, method: str, path: str, **kwargs):
        self.calls.append({"method": method, "path": path, **kwargs})
        return {"success": True, "data": {"method": method, "path": path}}


def test_service_unwraps_remote_envelope_and_preserves_search_contract() -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]

    result = service.search("instrumental variables", scope="discovery", limit=12)

    assert result == {"method": "GET", "path": "/papers/search"}
    assert client.calls == [
        {
            "method": "GET",
            "path": "/papers/search",
            "params": {"q": "instrumental variables", "scope": "discovery", "limit": 12},
        }
    ]


def test_service_layered_search_validates_and_normalizes_layers() -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]

    service.search_layered("IV", layer="all", layers="l1, L3", limit=5)
    assert client.calls[0]["path"] == "/papers/search/all"
    assert client.calls[0]["params"] == {"q": "IV", "limit": 5, "layers": "L1,L3"}

    with pytest.raises(CommandError) as caught:
        service.search_layered("IV", layer="L9")
    assert caught.value.code == ErrorCode.USAGE_ERROR


def test_service_note_add_uses_query_parameter() -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]

    service.add_note("P-1", "important")

    assert client.calls[0] == {
        "method": "POST",
        "path": "/papers/P-1/notes",
        "params": {"content": "important"},
    }


def test_service_rejects_non_pdf_before_network(tmp_path: Path) -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]
    text_file = tmp_path / "paper.txt"
    text_file.write_text("not a PDF", encoding="utf-8")

    with pytest.raises(CommandError) as caught:
        service.upload(text_file)

    assert caught.value.code == ErrorCode.USAGE_ERROR
    assert client.calls == []

