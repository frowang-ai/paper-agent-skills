"""Workspace materialization (ArtifactSyncService) for collab~ scoped references.

``workspace add`` must accept the ``collab~<collection_key>~<paper_id>`` IDs
returned by ``library collection items``. Two invariants are covered here:

1. Identity: the scoped reference is preserved as the manifest/state paper_id,
   while on-disk cache directories derive a safe segment (``~`` is not a valid
   cache path character).
2. Revision truth: the collab detail endpoint reports the collaborative task
   (``task_collab_*``), but read-only asset endpoints fall back to the
   underlying paper's artifacts. The cached revision must follow the task that
   actually produced the downloaded artifacts (parsed from asset URLs), not the
   detail endpoint's task id.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services import ArtifactSyncService
from paper_agent.storage import StateStore

COLLAB_REF = "collab~9f50976a-e7ec-45fd-afb7-d7a05b805cd8~bef386ed-b583-4331-b54f-c582ccdbea6e"
COLLAB_PAPER_ID = COLLAB_REF
COLLAB_TASK = "task_collab_a1c7e7128c52469fad41430598490136"
PRIVATE_TASK = "task_20261018110757_60a3c05d"


class FakeCollabLibrary:
    """Collab detail says task_collab_*; assets fall back to private artifacts."""

    def __init__(self, *, show_task: str = COLLAB_TASK, asset_task: str = PRIVATE_TASK) -> None:
        self.show_task = show_task
        self.asset_task = asset_task
        self.show_calls: list[str] = []
        self.metadata_calls: list[str] = []
        self.assets_calls: list[str] = []
        self.downloads: list[str] = []
        self.show_paper_id = COLLAB_PAPER_ID
        self.asset_shape = "/outputs/{task}/complete.md"

    def show(self, paper_ref: str) -> dict[str, object]:
        self.show_calls.append(paper_ref)
        return {
            "paper_id": self.show_paper_id,
            "title": "Asymmetry and Timing in the Volunteer's Dilemma",
            "publication_year": 2024,
            "authors": [{"family": "Weesie", "given": "Jeroen"}],
            "latest_task_id": self.show_task,
        }

    def metadata(self, paper_ref: str) -> dict[str, object]:
        self.metadata_calls.append(paper_ref)
        return {
            "title": "Asymmetry and Timing in the Volunteer's Dilemma",
            "publication_year": 2024,
            "authors": [{"family": "Weesie", "given": "Jeroen"}],
            "doi": "10.0000/collab",
        }

    def assets(self, paper_ref: str) -> dict[str, object]:
        self.assets_calls.append(paper_ref)
        task = self.asset_task
        full_url = self.asset_shape.format(task=task)
        layout_url = (
            f"/outputs/{task}/layout.json"
            if self.asset_shape.startswith("/outputs/")
            else f"/files/{task}-layout.json"
        )
        return {
            "paper_id": "bef386ed-b583-4331-b54f-c582ccdbea6e",
            "assets": {
                "ocr_markdown_url": full_url,
                "layout_url": layout_url,
            },
        }

    def download_asset(self, asset_url: str, destination: Path) -> dict[str, object]:
        content = (
            b'{"pages": []}\n' if asset_url.endswith("layout.json") else b"# Collab\n\nEvidence.\n"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        self.downloads.append(asset_url)
        return {
            "path": str(destination),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "source_url": asset_url,
        }


def _service(tmp_path: Path, library: FakeCollabLibrary) -> ArtifactSyncService:
    return ArtifactSyncService(
        library=library,  # type: ignore[arg-type]
        state_store=StateStore(tmp_path / "state.sqlite3"),
        data_dir=tmp_path / "data",
        profile="default",
        base_url="https://frowang.test/paper-api/api/v1",
        clock=lambda: "2026-10-18T12:00:00Z",
    )


def test_sync_collab_reference_materializes_shared_copy(tmp_path: Path) -> None:
    library = FakeCollabLibrary()
    service = _service(tmp_path, library)

    result = service.sync(COLLAB_REF)
    revision_root = Path(result["revision_root"])
    manifest = json.loads((revision_root / "artifact-manifest.json").read_text(encoding="utf-8"))

    assert result["cache_hit"] is False
    # 身份保持 scoped 引用，不丢失 collection 归属
    assert manifest["paper_id"] == COLLAB_PAPER_ID
    # revision 以产物真实任务为准，而不是 collab detail 的 task_collab_*
    assert manifest["revision"] == PRIVATE_TASK
    assert (revision_root / "full.md").read_text(encoding="utf-8").startswith("# Collab")
    # 缓存目录段不含 ~，但保留 root 与 paper 的可读映射
    assert "collab-9f50976a" in str(revision_root)
    assert "~" not in str(revision_root)
    # 学术元数据继续走 collab workspace 端点（读引用原样传递）
    assert library.metadata_calls == [COLLAB_REF]
    # 状态库以 scoped ID 记录
    assert service.state_store.get_artifact_revision(
        "default", COLLAB_PAPER_ID, PRIVATE_TASK
    )["status"] == "committed"


def test_sync_collab_reference_cache_hit(tmp_path: Path) -> None:
    library = FakeCollabLibrary()
    service = _service(tmp_path, library)

    first = service.sync(COLLAB_REF)
    downloads_after_first = len(library.downloads)
    second = service.sync(COLLAB_REF)

    assert second["cache_hit"] is True
    assert second["revision_root"] == first["revision_root"]
    assert len(library.downloads) == downloads_after_first


def test_sync_revision_follows_asset_urls_when_divergent(tmp_path: Path) -> None:
    """私有论文同样适用：detail 任务号与产物任务号不一致时以产物为准。"""
    library = FakeCollabLibrary(
        show_task="task_show_stale",
        asset_task="task_url_fresh",
    )
    library.show_paper_id = "11111111-2222-3333-4444-555555555555"
    service = _service(tmp_path, library)

    result = service.sync("11111111-2222-3333-4444-555555555555")
    manifest = json.loads(
        (Path(result["revision_root"]) / "artifact-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["revision"] == "task_url_fresh"


def test_sync_keeps_detail_revision_when_asset_urls_unshaped(tmp_path: Path) -> None:
    """产物 URL 不含 /outputs/<task>/ 形态时退回 detail 任务号，不炸。"""
    library = FakeCollabLibrary(show_task="task_from_detail")
    library.asset_shape = "/files/{task}-complete.md"
    library.show_paper_id = "11111111-2222-3333-4444-555555555555"
    service = _service(tmp_path, library)

    result = service.sync("11111111-2222-3333-4444-555555555555")
    manifest = json.loads(
        (Path(result["revision_root"]) / "artifact-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["revision"] == "task_from_detail"


def test_sync_collab_not_ready_propagates_without_caching(tmp_path: Path) -> None:
    """私有侧产物缺失（metadata 404）时 NOT_READY 原样传播，不落缓存。"""

    class _NotReadyLibrary(FakeCollabLibrary):
        def metadata(self, paper_ref: str) -> dict[str, object]:
            self.metadata_calls.append(paper_ref)
            raise CommandError(
                code=ErrorCode.NOT_READY,
                message="Paper metadata is not ready",
                exit_code=4,
            )

    library = _NotReadyLibrary()
    service = _service(tmp_path, library)

    with pytest.raises(CommandError) as caught:
        service.sync(COLLAB_REF)

    assert caught.value.code == ErrorCode.NOT_READY
    assert not (tmp_path / "data" / "artifacts" / "papers" / "default" / "collab-9f50976a").exists()
