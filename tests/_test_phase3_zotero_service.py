from __future__ import annotations

from pathlib import Path

from paper_agent.clients.zotero import ZoteroCollection, ZoteroPaper
from paper_agent.services import ZoteroImportService
from paper_agent.storage import StateStore


class _FakeZotero:
    mode = "local"
    library_id = "0"
    storage_dir = None

    def __init__(self, pdf: Path) -> None:
        self.pdf = pdf
        self.extra_items: list[ZoteroPaper] = []

    def collection_tree(self, root_key: str):
        return [
            ZoteroCollection(key="ROOT", name="Root", parent_key=None, depth=0),
            ZoteroCollection(key="CHILD", name="Child", parent_key="ROOT", depth=1),
        ]

    def collection_papers(self, collection_key: str):
        shared = ZoteroPaper(
            item_key="ITEM1",
            title="Shared Paper",
            attachment_key="ATT1",
            attachment_filename="shared.pdf",
            pdf_path=self.pdf,
        )
        if collection_key == "ROOT":
            return [shared, *self.extra_items]
        return [shared]

    def paper(self, item_key: str):
        return self.collection_papers("ROOT")[0]


class _FakeLibrary:
    def __init__(self) -> None:
        self.uploads: list[tuple[Path, str]] = []
        self.created: list[tuple[str, object]] = []
        self.memberships: list[tuple[str, tuple[str, ...]]] = []

    def upload(self, file: Path, *, filename: str | None = None):
        self.uploads.append((file, filename or file.name))
        number = len(self.uploads)
        return {
            "paper_id": f"uuid-{number}",
            "short_id": f"P-{number}",
            "task_id": f"task-{number}",
            "is_new": True,
        }

    def create_collection(self, name: str, parent_key: str | None = None):
        self.created.append((name, parent_key))
        return {"short_id": f"C-{len(self.created)}"}

    def add_collection_items(self, key: str, task_ids: list[str]):
        self.memberships.append((key, tuple(task_ids)))
        return {"ok": True}


def test_collection_upload_deduplicates_items_and_reuses_collection_mappings(
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    zotero = _FakeZotero(pdf)
    library = _FakeLibrary()
    store = StateStore(tmp_path / "state.sqlite3")
    service = ZoteroImportService(
        zotero=zotero,  # type: ignore[arg-type]
        library=library,  # type: ignore[arg-type]
        state_store=store,
        profile="default",
        clock=lambda: "2026-07-11T12:00:00Z",
        sleep=lambda seconds: None,
    )

    first = service.upload_collection("ROOT")

    assert first["uploaded"] == 1
    assert len(library.uploads) == 1
    assert library.created == [("Root", None), ("Child", "C-1")]
    assert set(library.memberships) == {
        ("C-1", ("task-1",)),
        ("C-2", ("task-1",)),
    }

    second = service.upload_collection("ROOT")
    assert second["skipped"] == 1
    assert len(library.uploads) == 1
    assert len(library.created) == 2


def test_dry_run_has_no_remote_or_state_side_effects(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    library = _FakeLibrary()
    store = StateStore(tmp_path / "state.sqlite3")
    service = ZoteroImportService(
        zotero=_FakeZotero(pdf),  # type: ignore[arg-type]
        library=library,  # type: ignore[arg-type]
        state_store=store,
        profile="default",
        clock=lambda: "2026-07-11T12:00:00Z",
    )

    result = service.upload_collection("ROOT", dry_run=True)

    assert result["dry_run"] is True
    assert result["pending"] == 1
    assert library.uploads == []
    assert library.created == []
    assert store.zotero_status("default", "0")["item_count"] == 0

