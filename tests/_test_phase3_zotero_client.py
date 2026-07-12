from __future__ import annotations

from pathlib import Path

import pytest

from paper_agent.clients.zotero import (
    ZoteroClient,
    discover_zotero_storage,
    find_attachment_pdf,
)
from paper_agent.protocol import CommandError, ErrorCode


def test_discovers_custom_storage_from_explicit_profile_file(tmp_path: Path) -> None:
    zotero_root = tmp_path / "Zotero" / "Zotero"
    profile = zotero_root / "Profiles" / "abc.default"
    data_dir = tmp_path / "Custom Zotero"
    storage = data_dir / "storage"
    profile.mkdir(parents=True)
    storage.mkdir(parents=True)
    profiles_ini = zotero_root / "profiles.ini"
    profiles_ini.write_text(
        "[Profile0]\nName=default\nIsRelative=1\nPath=Profiles/abc.default\nDefault=1\n",
        encoding="utf-8",
    )
    escaped = str(data_dir).replace("\\", "\\\\")
    (profile / "prefs.js").write_text(
        f'user_pref("extensions.zotero.dataDir", "{escaped}");\n',
        encoding="utf-8",
    )

    assert discover_zotero_storage(profiles_ini=profiles_ini) == storage.resolve()


def test_attachment_lookup_is_deterministic_and_rejects_traversal(tmp_path: Path) -> None:
    attachment = tmp_path / "storage" / "ABCD1234"
    attachment.mkdir(parents=True)
    (attachment / "z-paper.pdf").write_bytes(b"z")
    expected = attachment / "a-paper.PDF"
    expected.write_bytes(b"a")

    assert find_attachment_pdf("ABCD1234", tmp_path / "storage") == expected.resolve()
    with pytest.raises(CommandError) as caught:
        find_attachment_pdf("../escape", tmp_path / "storage")
    assert caught.value.code == ErrorCode.PERMISSION_DENIED


class _Backend:
    def __init__(self) -> None:
        self.collection_starts: list[int] = []

    def collections(self, *, start: int, limit: int):
        self.collection_starts.append(start)
        if start == 0:
            return [
                {"data": {"key": f"C{i}", "name": f"Collection {i}"}}
                for i in range(100)
            ]
        if start == 100:
            return [{"data": {"key": "C100", "name": "Collection 100"}}]
        return []

    def collection_items(self, key: str, *, start: int, limit: int):
        return []

    def children(self, key: str):
        return []

    def item(self, key: str):
        return {"data": {"key": key, "title": "Paper"}}


def test_client_paginates_collections_without_printing() -> None:
    backend = _Backend()
    client = ZoteroClient(
        backend=backend,
        mode="local",
        library_id="0",
        library_type="user",
        storage_dir=None,
    )

    collections = client.list_collections()

    assert len(collections) == 101
    assert backend.collection_starts == [0, 100]


def test_client_maps_backend_failure_to_public_error() -> None:
    class Broken(_Backend):
        def collections(self, *, start: int, limit: int):
            raise ConnectionRefusedError("127.0.0.1 refused")

    client = ZoteroClient(
        backend=Broken(),
        mode="local",
        library_id="0",
        library_type="user",
        storage_dir=None,
    )
    with pytest.raises(CommandError) as caught:
        client.list_collections()

    assert caught.value.code == ErrorCode.NETWORK_ERROR
    assert caught.value.details["provider"] == "zotero"

