from __future__ import annotations

import hashlib
import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from uuid import uuid4

from paper_agent.protocol import CommandError, ErrorCode, ExitCode
from paper_agent.storage import StateStore
from paper_agent.workspace import WorkspaceDirectoryNamingProtocol

from .artifact_sync_service import ArtifactSyncService


def _workspace_error(message: str, **details: object) -> CommandError:
    return CommandError(
        code=ErrorCode.WORKSPACE_INVALID,
        message=message,
        exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        details=details,
    )


def _conflict(message: str, **details: object) -> CommandError:
    return CommandError(
        code=ErrorCode.CONFLICT,
        message=message,
        exit_code=ExitCode.CONFLICT,
        details=details,
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError as exc:
        raise _workspace_error(
            "Paper Agent could not write the workspace manifest",
            path=str(path),
            error_type=type(exc).__name__,
        ) from exc
    finally:
        if temporary.exists():
            temporary.unlink()


class WorkspaceService:
    def __init__(
        self,
        *,
        artifact_sync: Optional[ArtifactSyncService],
        state_store: StateStore,
        papers_dir_name: str,
        clock: Callable[[], str],
        naming_protocol: Optional[WorkspaceDirectoryNamingProtocol] = None,
    ) -> None:
        relative = Path(papers_dir_name)
        if relative.is_absolute() or ".." in relative.parts or relative in {Path(""), Path(".")}:
            raise _workspace_error("workspace.papers_dir must be a safe relative path")
        self.artifact_sync = artifact_sync
        self.state_store = state_store
        self.papers_dir_name = relative
        self.clock = clock
        self.naming_protocol = naming_protocol or WorkspaceDirectoryNamingProtocol()

    def _paths(self, project_root: Path) -> tuple[Path, Path, Path]:
        project = project_root.expanduser().resolve()
        if not project.is_dir():
            raise _workspace_error("Project root does not exist", project_root=str(project))
        papers = (project / self.papers_dir_name).resolve()
        if not papers.is_relative_to(project):
            raise _workspace_error("Workspace papers directory escapes the project root")
        return project, papers, papers / "manifest.json"

    def _load(self, project_root: Path) -> tuple[Path, Path, Path, dict[str, Any]]:
        project, papers, path = self._paths(project_root)
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise _workspace_error(
                "Paper workspace is not initialized", manifest=str(path)
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise _workspace_error(
                "Paper workspace manifest is invalid",
                manifest=str(path),
                error_type=type(exc).__name__,
            ) from exc
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("workspace_id"), str)
            or not isinstance(manifest.get("papers"), dict)
        ):
            raise _workspace_error("Unsupported paper workspace manifest", manifest=str(path))
        return project, papers, path, manifest

    def _record(self, project: Path, path: Path, manifest: dict[str, Any]) -> None:
        self.state_store.record_workspace(
            workspace_id=manifest["workspace_id"],
            root_path=project,
            manifest_path=path,
            last_seen_at=self.clock(),
            papers=manifest["papers"],
        )

    def init(self, project_root: Path) -> dict[str, Any]:
        project, papers, path = self._paths(project_root)
        if path.exists():
            _, _, _, manifest = self._load(project)
            self._record(project, path, manifest)
            return {
                "created": False,
                "workspace_id": manifest["workspace_id"],
                "project_root": str(project),
                "papers_root": str(papers),
                "manifest": str(path),
            }
        if papers.exists() and any(papers.iterdir()):
            raise _conflict(
                "Existing papers directory is not a managed workspace", path=str(papers)
            )
        now = self.clock()
        manifest = {
            "schema_version": 1,
            "workspace_id": str(uuid4()),
            "created_at": now,
            "updated_at": now,
            "papers_dir": ".",
            "papers": {},
        }
        _atomic_json(path, manifest)
        self._record(project, path, manifest)
        return {
            "created": True,
            "workspace_id": manifest["workspace_id"],
            "project_root": str(project),
            "papers_root": str(papers),
            "manifest": str(path),
        }

    @staticmethod
    def _managed_status(papers: Path, paper: dict[str, Any]) -> dict[str, list[str]]:
        root = papers / paper["directory"]
        missing: list[str] = []
        modified: list[str] = []
        for relative, expected in paper.get("managed_assets", {}).items():
            path = root / relative
            if not path.is_file():
                missing.append(relative)
            elif _hash_file(path) != expected:
                modified.append(relative)
        return {"missing": sorted(missing), "modified": sorted(modified)}

    def status(self, project_root: Path) -> dict[str, Any]:
        project, papers, path, manifest = self._load(project_root)
        result: dict[str, Any] = {}
        for paper_id, paper in manifest["papers"].items():
            differences = self._managed_status(papers, paper)
            state = "modified" if differences["modified"] else "missing" if differences["missing"] else "ok"
            result[paper_id] = {
                "status": state,
                "short_id": paper.get("short_id"),
                "title": paper.get("title"),
                "directory": str(papers / paper["directory"]),
                "revision": paper["revision"],
                **differences,
            }
        self._record(project, path, manifest)
        return {
            "workspace_id": manifest["workspace_id"],
            "project_root": str(project),
            "manifest": str(path),
            "papers": result,
        }

    def list(self, project_root: Path) -> dict[str, Any]:
        return self.status(project_root)

    def _require_sync(self) -> ArtifactSyncService:
        if self.artifact_sync is None:
            raise _workspace_error("This workspace operation requires remote artifact access")
        return self.artifact_sync

    @staticmethod
    def _managed_from_artifacts(artifacts: dict[str, Any]) -> dict[str, str]:
        return {item["path"]: item["sha256"] for item in artifacts.values()}

    @staticmethod
    def _copy_artifacts(source_root: Path, target_root: Path, artifacts: dict[str, Any]) -> None:
        for artifact in artifacts.values():
            relative = Path(artifact["path"])
            source = source_root / relative
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @staticmethod
    def _artifact_metadata(artifact: dict[str, Any]) -> dict[str, Any]:
        try:
            metadata_entry = artifact["artifacts"]["metadata"]
            metadata_path = Path(artifact["revision_root"]) / metadata_entry["path"]
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
            raise _workspace_error(
                "Cached paper metadata cannot be used for workspace naming",
                paper_id=artifact.get("paper_id"),
                error_type=type(exc).__name__,
            ) from exc
        if not isinstance(metadata, dict):
            raise _workspace_error(
                "Cached paper metadata must be a JSON object",
                paper_id=artifact.get("paper_id"),
            )
        return metadata

    def add(self, project_root: Path, paper_refs: Iterable[str]) -> dict[str, Any]:
        project, papers, path, manifest = self._load(project_root)
        sync = self._require_sync()
        refs = list(dict.fromkeys(paper_refs))
        if not refs:
            raise _workspace_error("At least one paper ID is required")
        added: list[dict[str, Any]] = []
        skipped: list[str] = []
        for paper_ref in refs:
            artifact = sync.sync(paper_ref)
            paper_id = artifact["paper_id"]
            if paper_id in manifest["papers"]:
                skipped.append(paper_ref)
                continue
            naming = self.naming_protocol.generate(
                metadata=self._artifact_metadata(artifact),
                paper_id=paper_id,
                short_id=artifact.get("short_id"),
                revision=artifact["revision"],
            )
            directory = naming.directory
            destination = papers / directory
            if destination.exists():
                raise _conflict(
                    "Workspace paper directory already exists",
                    paper_id=paper_id,
                    path=str(destination),
                )
            staging = papers / ".staging" / f"{directory}-{uuid4().hex}"
            try:
                staging.mkdir(parents=True)
                self._copy_artifacts(
                    Path(artifact["revision_root"]), staging, artifact["artifacts"]
                )
                os.replace(staging, destination)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            entry = {
                "short_id": artifact.get("short_id"),
                "title": artifact["title"],
                "profile": sync.profile,
                "revision": artifact["revision"],
                "directory": directory,
                "directory_naming": naming.as_dict(),
                "tracking": "latest",
                "materialization": "copy",
                "materialized_at": self.clock(),
                "managed_assets": self._managed_from_artifacts(artifact["artifacts"]),
            }
            manifest["papers"][paper_id] = entry
            added.append({"paper_id": paper_id, **entry})
            manifest["updated_at"] = self.clock()
            try:
                _atomic_json(path, manifest)
            except CommandError:
                shutil.rmtree(destination, ignore_errors=True)
                del manifest["papers"][paper_id]
                added.pop()
                raise
            self._record(project, path, manifest)
        return {"added": added, "skipped": skipped, "manifest": str(path)}

    @staticmethod
    def _select(manifest: dict[str, Any], refs: Optional[Iterable[str]]) -> list[str]:
        if refs is None:
            return list(manifest["papers"])
        selected: list[str] = []
        for ref in refs:
            matches = [
                paper_id
                for paper_id, paper in manifest["papers"].items()
                if ref == paper_id or ref == paper.get("short_id")
            ]
            if not matches:
                raise _workspace_error("Paper is not in this workspace", paper_ref=ref)
            if matches[0] not in selected:
                selected.append(matches[0])
        return selected

    @staticmethod
    def _workspace_metadata(
        papers: Path, paper_id: str, paper: dict[str, Any]
    ) -> dict[str, Any]:
        root = papers / paper["directory"]
        expected = paper.get("managed_assets", {}).get("metadata.json")
        metadata_path = root / "metadata.json"
        if not isinstance(expected, str) or _hash_file(metadata_path) != expected:
            raise _conflict(
                "Workspace metadata is missing or modified",
                paper_id=paper_id,
                path=str(metadata_path),
            )
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _workspace_error(
                "Workspace metadata is invalid",
                paper_id=paper_id,
                path=str(metadata_path),
                error_type=type(exc).__name__,
            ) from exc
        if not isinstance(metadata, dict):
            raise _workspace_error(
                "Workspace metadata must be a JSON object", paper_id=paper_id
            )
        return metadata

    def names_plan(
        self,
        project_root: Path,
        paper_refs: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        project, papers, path, manifest = self._load(project_root)
        selected = self._select(manifest, paper_refs)
        items: list[dict[str, Any]] = []
        for paper_id in selected:
            paper = manifest["papers"][paper_id]
            current = paper["directory"]
            source = papers / current
            naming = self.naming_protocol.generate(
                metadata=self._workspace_metadata(papers, paper_id, paper),
                paper_id=paper_id,
                short_id=paper.get("short_id"),
                revision=paper["revision"],
            )
            proposed = naming.directory
            target = papers / proposed
            if not source.is_dir():
                status = "conflict"
                reason = "source_missing"
            elif current == proposed:
                status = "current"
                reason = "already_current"
            elif target.exists():
                status = "conflict"
                reason = "target_exists"
            else:
                status = "rename_available"
                reason = (
                    "legacy_name"
                    if not isinstance(paper.get("directory_naming"), dict)
                    else "metadata_changed"
                )
            items.append(
                {
                    "paper_id": paper_id,
                    "short_id": paper.get("short_id"),
                    "current": current,
                    "proposed": proposed,
                    "status": status,
                    "reason": reason,
                    "directory_naming": naming.as_dict(),
                }
            )
        self._record(project, path, manifest)
        return {
            "workspace_id": manifest["workspace_id"],
            "manifest": str(path),
            "items": items,
            "rename_count": sum(item["status"] == "rename_available" for item in items),
            "conflict_count": sum(item["status"] == "conflict" for item in items),
        }

    def names_apply(
        self,
        project_root: Path,
        paper_refs: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        project, papers, path, manifest = self._load(project_root)
        plan = self.names_plan(project_root, paper_refs)
        conflicts = [item for item in plan["items"] if item["status"] == "conflict"]
        if conflicts:
            raise _conflict(
                "Workspace directory rename has conflicts", items=conflicts
            )
        renamed: list[dict[str, Any]] = []
        unchanged: list[str] = []
        for item in plan["items"]:
            paper_id = item["paper_id"]
            if item["status"] == "current":
                unchanged.append(item.get("short_id") or paper_id)
                continue
            paper = manifest["papers"][paper_id]
            previous = deepcopy(paper)
            source = papers / item["current"]
            target = papers / item["proposed"]
            try:
                os.replace(source, target)
            except OSError as exc:
                raise _workspace_error(
                    "Paper Agent could not rename the workspace paper directory",
                    paper_id=paper_id,
                    source=str(source),
                    target=str(target),
                    error_type=type(exc).__name__,
                ) from exc
            paper["directory"] = item["proposed"]
            paper["directory_naming"] = item["directory_naming"]
            manifest["updated_at"] = self.clock()
            try:
                _atomic_json(path, manifest)
            except CommandError:
                try:
                    os.replace(target, source)
                except OSError as restore_error:
                    raise _workspace_error(
                        "Workspace directory rename failed and could not be restored",
                        paper_id=paper_id,
                        source=str(source),
                        target=str(target),
                        error_type=type(restore_error).__name__,
                    ) from restore_error
                manifest["papers"][paper_id] = previous
                raise
            self._record(project, path, manifest)
            renamed.append(
                {
                    "paper_id": paper_id,
                    "short_id": paper.get("short_id"),
                    "from": item["current"],
                    "to": item["proposed"],
                }
            )
        if not renamed:
            self._record(project, path, manifest)
        return {
            "renamed": renamed,
            "unchanged": unchanged,
            "manifest": str(path),
        }

    def sync(self, project_root: Path, paper_refs: Optional[Iterable[str]] = None) -> dict[str, Any]:
        project, papers, path, manifest = self._load(project_root)
        remote = self._require_sync()
        selected = self._select(manifest, paper_refs)
        for paper_id in selected:
            differences = self._managed_status(papers, manifest["papers"][paper_id])
            if differences["modified"] or differences["missing"]:
                raise _conflict(
                    "Workspace managed files were changed",
                    paper_id=paper_id,
                    **differences,
                )
        updated: list[dict[str, Any]] = []
        unchanged: list[str] = []
        for paper_id in selected:
            paper = manifest["papers"][paper_id]
            artifact = remote.sync(paper.get("short_id") or paper_id)
            if artifact["revision"] == paper["revision"]:
                unchanged.append(paper.get("short_id") or paper_id)
                continue
            destination = papers / paper["directory"]
            staging = papers / ".staging" / f"{paper['directory']}-{uuid4().hex}"
            backup = papers / ".staging" / f"{paper['directory']}-backup-{uuid4().hex}"
            previous_entry = deepcopy(paper)
            try:
                shutil.copytree(destination, staging)
                for relative in paper["managed_assets"]:
                    managed = staging / relative
                    if managed.exists():
                        managed.unlink()
                self._copy_artifacts(
                    Path(artifact["revision_root"]), staging, artifact["artifacts"]
                )
                os.replace(destination, backup)
                os.replace(staging, destination)
            except OSError as exc:
                if not destination.exists() and backup.exists():
                    os.replace(backup, destination)
                raise _workspace_error(
                    "Paper Agent could not update workspace files",
                    paper_id=paper_id,
                    error_type=type(exc).__name__,
                ) from exc
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            previous = paper["revision"]
            paper.update(
                revision=artifact["revision"],
                title=artifact["title"],
                materialized_at=self.clock(),
                managed_assets=self._managed_from_artifacts(artifact["artifacts"]),
            )
            updated.append(
                {
                    "paper_id": paper_id,
                    "short_id": paper.get("short_id"),
                    "from_revision": previous,
                    "to_revision": artifact["revision"],
                }
            )
            manifest["updated_at"] = self.clock()
            try:
                _atomic_json(path, manifest)
            except CommandError:
                shutil.rmtree(destination, ignore_errors=True)
                if backup.exists():
                    os.replace(backup, destination)
                manifest["papers"][paper_id] = previous_entry
                updated.pop()
                raise
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            self._record(project, path, manifest)
        if not updated:
            self._record(project, path, manifest)
        return {"updated": updated, "unchanged": unchanged, "manifest": str(path)}

    def remove(
        self,
        project_root: Path,
        paper_refs: Iterable[str],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        project, papers, path, manifest = self._load(project_root)
        selected = self._select(manifest, paper_refs)
        for paper_id in selected:
            differences = self._managed_status(papers, manifest["papers"][paper_id])
            if (differences["modified"] or differences["missing"]) and not force:
                raise _conflict(
                    "Workspace managed files were changed",
                    paper_id=paper_id,
                    **differences,
                )
        removed: list[str] = []
        preserved: dict[str, list[str]] = {}
        for paper_id in selected:
            paper = manifest["papers"][paper_id]
            root = papers / paper["directory"]
            for relative in paper["managed_assets"]:
                managed = root / relative
                if managed.is_file() or managed.is_symlink():
                    managed.unlink()
            for directory in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                if directory.is_dir():
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            try:
                root.rmdir()
            except OSError:
                preserved[paper.get("short_id") or paper_id] = sorted(
                    item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()
                )
            alias = paper.get("short_id") or paper_id
            del manifest["papers"][paper_id]
            removed.append(alias)
        manifest["updated_at"] = self.clock()
        _atomic_json(path, manifest)
        self._record(project, path, manifest)
        return {"removed": removed, "preserved_user_files": preserved, "manifest": str(path)}
