from __future__ import annotations

import json
from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode, ExitCode
from paper_agent.services import ArtifactSyncService, WorkspaceService
from paper_agent.storage import StateStore
from paper_agent.services import workspace_service as workspace_module

from _test_phase5_artifact_sync import FakeLibrary


def _services(tmp_path: Path) -> tuple[FakeLibrary, WorkspaceService]:
    library = FakeLibrary()
    store = StateStore(tmp_path / "state.sqlite3")
    artifact = ArtifactSyncService(
        library=library,  # type: ignore[arg-type]
        state_store=store,
        data_dir=tmp_path / "data",
        profile="default",
        base_url="https://frowang.test/paper-api/api/v1",
        clock=lambda: "2026-07-11T12:00:00Z",
    )
    workspace = WorkspaceService(
        artifact_sync=artifact,
        state_store=store,
        papers_dir_name="papers",
        clock=lambda: "2026-07-11T12:00:00Z",
    )
    return library, workspace


def _paper_root(project: Path) -> Path:
    manifest = json.loads((project / "papers" / "manifest.json").read_text())
    paper = next(iter(manifest["papers"].values()))
    return project / "papers" / paper["directory"]


def test_add_and_sync_new_revision_preserve_user_files(tmp_path: Path) -> None:
    library, service = _services(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service.init(project)

    added = service.add(project, ["P-1"])
    paper_root = _paper_root(project)
    notes = paper_root / "notes.md"
    notes.write_text("keep me\n", encoding="utf-8")
    assert added["added"][0]["revision"] == "task-1"

    library.revision = "task-2"
    synced = service.sync(project)

    assert synced["updated"][0]["from_revision"] == "task-1"
    assert synced["updated"][0]["to_revision"] == "task-2"
    assert notes.read_text(encoding="utf-8") == "keep me\n"
    manifest = json.loads((project / "papers" / "manifest.json").read_text())
    paper = next(iter(manifest["papers"].values()))
    assert paper["revision"] == "task-2"


def test_modified_managed_file_blocks_sync_and_remove(tmp_path: Path) -> None:
    library, service = _services(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service.init(project)
    service.add(project, ["P-1"])
    fulltext = _paper_root(project) / "full.md"
    fulltext.write_text("user edit\n", encoding="utf-8")
    library.revision = "task-2"

    with pytest.raises(CommandError) as sync_error:
        service.sync(project)
    assert sync_error.value.code == ErrorCode.CONFLICT
    assert fulltext.read_text(encoding="utf-8") == "user edit\n"

    with pytest.raises(CommandError) as remove_error:
        service.remove(project, ["P-1"])
    assert remove_error.value.code == ErrorCode.CONFLICT


def test_remove_deletes_only_managed_files(tmp_path: Path) -> None:
    _, service = _services(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service.init(project)
    service.add(project, ["P-1"])
    paper_root = _paper_root(project)
    (paper_root / "reading.md").write_text("notes\n", encoding="utf-8")

    result = service.remove(project, ["P-1"])

    assert result["removed"] == ["P-1"]
    assert (paper_root / "reading.md").is_file()
    assert not (paper_root / "full.md").exists()


def test_sync_restores_old_directory_when_manifest_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, service = _services(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service.init(project)
    service.add(project, ["P-1"])
    fulltext = _paper_root(project) / "full.md"
    original = fulltext.read_bytes()
    library.revision = "task-2"

    def fail_manifest(path: Path, value: object) -> None:
        raise CommandError(
            code=ErrorCode.LOCAL_IO_ERROR,
            message="simulated manifest failure",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        )

    monkeypatch.setattr(workspace_module, "_atomic_json", fail_manifest)
    with pytest.raises(CommandError):
        service.sync(project)

    assert fulltext.read_bytes() == original


def test_names_plan_and_apply_migrate_legacy_directory_and_keep_notes(
    tmp_path: Path,
) -> None:
    _, service = _services(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service.init(project)
    service.add(project, ["P-1"])
    manifest_path = project / "papers" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    paper_id, paper = next(iter(manifest["papers"].items()))
    generated = project / "papers" / paper["directory"]
    legacy = project / "papers" / "P-1"
    generated.rename(legacy)
    paper["directory"] = "P-1"
    paper.pop("directory_naming", None)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (legacy / "reading.md").write_text("keep me\n", encoding="utf-8")

    plan = service.names_plan(project, ["P-1"])
    assert plan["items"][0]["status"] == "rename_available"
    assert plan["items"][0]["proposed"] == (
        "2024-Smith-Test-Paper--P-1"
    )

    applied = service.names_apply(project, ["P-1"])
    target = project / "papers" / applied["renamed"][0]["to"]
    assert (target / "reading.md").read_text(encoding="utf-8") == "keep me\n"
    assert not legacy.exists()
    updated = json.loads(manifest_path.read_text())
    assert updated["papers"][paper_id]["directory_naming"]["protocol"] == (
        "year-author-short-title--short-id-v1"
    )


def test_names_apply_restores_legacy_directory_when_manifest_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, service = _services(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service.init(project)
    service.add(project, ["P-1"])
    manifest_path = project / "papers" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    paper = next(iter(manifest["papers"].values()))
    generated = project / "papers" / paper["directory"]
    legacy = project / "papers" / "P-1"
    generated.rename(legacy)
    paper["directory"] = "P-1"
    paper.pop("directory_naming", None)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def fail_manifest(path: Path, value: object) -> None:
        raise CommandError(
            code=ErrorCode.LOCAL_IO_ERROR,
            message="simulated manifest failure",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        )

    monkeypatch.setattr(workspace_module, "_atomic_json", fail_manifest)
    with pytest.raises(CommandError):
        service.names_apply(project, ["P-1"])

    assert legacy.is_dir()
    assert not (project / "papers" / "2024-Smith-Test-Paper--P-1").exists()


def test_sync_does_not_rename_after_metadata_change(tmp_path: Path) -> None:
    library, service = _services(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    service.init(project)
    service.add(project, ["P-1"])
    original_root = _paper_root(project)

    library.revision = "task-2"
    library.title = "Revised Paper Title"
    service.sync(project)

    assert original_root.is_dir()
    plan = service.names_plan(project, ["P-1"])
    assert plan["items"][0]["status"] == "rename_available"
    assert plan["items"][0]["reason"] == "metadata_changed"
    assert plan["items"][0]["proposed"] == (
        "2024-Smith-Revised-Paper-Title--P-1"
    )
