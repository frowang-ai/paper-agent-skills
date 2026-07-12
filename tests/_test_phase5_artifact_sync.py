from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services import ArtifactSyncService
from paper_agent.storage import StateStore


class FakeLibrary:
    def __init__(self) -> None:
        self.revision = "task-1"
        self.title = "Test Paper"
        self.publication_year = 2024
        self.authors: list[object] = [{"family": "Smith", "given": "Alice"}]
        self.downloads: list[str] = []
        self.layout = b'{"pages": []}\n'

    def show(self, paper_ref: str) -> dict[str, object]:
        return {
            "paper_id": "11111111-1111-1111-1111-111111111111",
            "title": self.title,
            "publication_year": self.publication_year,
            "authors": self.authors,
            "latest_task_id": self.revision,
        }

    def assets(self, paper_ref: str) -> dict[str, object]:
        return {
            "paper_id": "11111111-1111-1111-1111-111111111111",
            "assets": {
                "ocr_markdown_url": f"/outputs/{self.revision}/complete.md",
                "layout_url": f"/outputs/{self.revision}/layout.json",
            },
        }

    def download_asset(self, asset_url: str, destination: Path) -> dict[str, object]:
        content = self.layout if asset_url.endswith("layout.json") else b"# Test\n\nEvidence.\n"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        self.downloads.append(asset_url)
        return {
            "path": str(destination),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "source_url": asset_url,
        }


def _service(tmp_path: Path, library: FakeLibrary) -> ArtifactSyncService:
    return ArtifactSyncService(
        library=library,  # type: ignore[arg-type]
        state_store=StateStore(tmp_path / "state.sqlite3"),
        data_dir=tmp_path / "data",
        profile="default",
        base_url="https://frowang.test/paper-api/api/v1",
        clock=lambda: "2026-07-11T12:00:00Z",
    )


def test_sync_commits_text_revision_and_reuses_verified_cache(tmp_path: Path) -> None:
    library = FakeLibrary()
    service = _service(tmp_path, library)

    first = service.sync("P-1")
    revision_root = Path(first["revision_root"])
    manifest = json.loads((revision_root / "artifact-manifest.json").read_text())

    assert first["cache_hit"] is False
    assert manifest["paper_id"] == "11111111-1111-1111-1111-111111111111"
    assert set(manifest["artifacts"]) == {"metadata", "fulltext", "layout"}
    assert (revision_root / "full.md").read_text().startswith("# Test")
    assert service.state_store.get_artifact_revision(
        "default", manifest["paper_id"], "task-1"
    )["status"] == "committed"

    second = service.sync("P-1")
    assert second["cache_hit"] is True
    assert len(library.downloads) == 2


def test_invalid_layout_never_commits_revision(tmp_path: Path) -> None:
    library = FakeLibrary()
    library.layout = b"not-json"
    service = _service(tmp_path, library)

    with pytest.raises(CommandError) as caught:
        service.sync("P-1")

    assert caught.value.code == ErrorCode.INTEGRITY_ERROR
    assert not list((tmp_path / "data" / "artifacts" / "papers").rglob("task-1"))
