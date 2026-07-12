from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from uuid import uuid4

from paper_agent.protocol import CommandError, ErrorCode, ExitCode
from paper_agent.skills import SkillSnapshot, SkillSource, SkillTarget
from paper_agent.storage import StateStore


def _hash_file(path: Path) -> Optional[str]:
    if path.is_symlink() or not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise _io_error("hash_target", path, exc) from exc
    return digest.hexdigest()


def _io_error(operation: str, path: Path, exc: Exception) -> CommandError:
    return CommandError(
        code=ErrorCode.LOCAL_IO_ERROR,
        message="Paper Agent could not update a Skill installation",
        exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        details={
            "operation": operation,
            "path": str(path),
            "error_type": type(exc).__name__,
        },
    )


def _conflict(skill: str, reason: str, **details: object) -> CommandError:
    return CommandError(
        code=ErrorCode.CONFLICT,
        message="Skill installation has local content that cannot be overwritten safely",
        exit_code=ExitCode.CONFLICT,
        details={"skill": skill, "reason": reason, **details},
    )


def _safe_relative(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise CommandError(
            code=ErrorCode.INTEGRITY_ERROR,
            message="Stored Skill installation contains an invalid path",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
            details={"path": value},
        )
    return relative


class SkillInstallService:
    def __init__(
        self,
        *,
        source: SkillSource,
        state_store: StateStore,
        package_version: str,
        clock: Callable[[], str],
    ) -> None:
        self.source = source
        self.state_store = state_store
        self.package_version = package_version
        self.clock = clock
        self.state_store.initialize()

    def _selected(self, names: Optional[Iterable[str]]) -> list[str]:
        available = self.source.skill_names()
        selected = available if not names else list(dict.fromkeys(names))
        unknown = sorted(set(selected) - set(available))
        if unknown:
            raise CommandError(
                code=ErrorCode.NOT_FOUND,
                message="One or more canonical Skills were not found",
                exit_code=ExitCode.RESOURCE_STATE,
                details={"skills": unknown, "available": available},
            )
        return selected

    def _record(self, target: SkillTarget, name: str) -> Optional[dict[str, Any]]:
        return self.state_store.get_skill_installation(
            platform=target.platform,
            scope=target.scope,
            mode=target.mode,
            target_root=target.root,
            skill_name=name,
        )

    @staticmethod
    def _actual_files(destination: Path) -> set[str]:
        if not destination.is_dir():
            return set()
        try:
            return {
                path.relative_to(destination).as_posix()
                for path in destination.rglob("*")
                if path.is_file() or path.is_symlink()
            }
        except OSError as exc:
            raise _io_error("list_target", destination, exc) from exc

    def _diff_one(
        self,
        target: SkillTarget,
        snapshot: SkillSnapshot,
        record: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        destination = target.root / snapshot.name
        actual = self._actual_files(destination)
        if record is None:
            return {
                "source_added": sorted(snapshot.files),
                "source_removed": [],
                "source_changed": [],
                "target_modified": [],
                "target_unmanaged": sorted(actual),
                "recorded": False,
                "destination_exists": destination.exists(),
            }

        recorded_files = record.get("files", {})
        if not isinstance(recorded_files, dict):
            raise CommandError(
                code=ErrorCode.INTEGRITY_ERROR,
                message="Skill installation record has invalid file metadata",
                exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
                details={"skill": snapshot.name},
            )
        recorded_names = set(recorded_files)
        source_names = set(snapshot.files)
        target_modified: list[str] = []
        for relative, expected_hash in recorded_files.items():
            path = destination / _safe_relative(relative)
            if _hash_file(path) != expected_hash:
                target_modified.append(relative)
        return {
            "source_added": sorted(source_names - recorded_names),
            "source_removed": sorted(recorded_names - source_names),
            "source_changed": sorted(
                relative
                for relative in source_names & recorded_names
                if snapshot.files[relative] != recorded_files[relative]
            ),
            "target_modified": sorted(target_modified),
            "target_unmanaged": sorted(actual - recorded_names),
            "recorded": True,
            "destination_exists": destination.is_dir(),
        }

    def diff(
        self,
        target: SkillTarget,
        names: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        selected = self._selected(names)
        return {
            "target": target.as_dict(),
            "skills": {
                name: self._diff_one(
                    target,
                    self.source.snapshot(name),
                    self._record(target, name),
                )
                for name in selected
            },
        }

    def status(
        self,
        target: SkillTarget,
        names: Optional[Iterable[str]] = None,
    ) -> dict[str, Any]:
        selected = self._selected(names)
        skills: dict[str, Any] = {}
        for name in selected:
            snapshot = self.source.snapshot(name)
            record = self._record(target, name)
            details = self._diff_one(target, snapshot, record)
            if not details["recorded"]:
                state = "unmanaged" if details["destination_exists"] else "not_installed"
            elif not details["destination_exists"]:
                state = "missing"
            elif details["target_modified"]:
                state = "modified"
            elif (
                details["source_added"]
                or details["source_removed"]
                or details["source_changed"]
                or (record and record.get("source_hash") != snapshot.source_hash)
            ):
                state = "update_available"
            else:
                state = "current"
            skills[name] = {
                "status": state,
                "source_hash": snapshot.source_hash,
                "installed_source_hash": record.get("source_hash") if record else None,
                "installed_version": record.get("package_version") if record else None,
                "target_modified": details["target_modified"],
                "unmanaged_files": details["target_unmanaged"],
            }
        return {"target": target.as_dict(), "skills": skills}

    def _copy_snapshot(self, snapshot: SkillSnapshot, destination: Path) -> None:
        for relative in snapshot.files:
            source_path = snapshot.root / _safe_relative(relative)
            target_path = destination / _safe_relative(relative)
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
            except OSError as exc:
                raise _io_error("stage_skill", target_path, exc) from exc

    @staticmethod
    def _remove_tree(path: Path) -> None:
        if not path.exists():
            return
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            else:
                shutil.rmtree(path)
        except OSError as exc:
            raise _io_error("remove_staging", path, exc) from exc

    def _apply_one(
        self,
        target: SkillTarget,
        snapshot: SkillSnapshot,
        record: Optional[dict[str, Any]],
    ) -> None:
        destination = target.root / snapshot.name
        try:
            target.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _io_error("create_target_root", target.root, exc) from exc
        staging = target.root / f".{snapshot.name}.paper-agent-stage-{uuid4().hex}"
        backup = target.root / f".{snapshot.name}.paper-agent-backup-{uuid4().hex}"
        destination_existed = destination.exists()
        try:
            if destination_existed:
                shutil.copytree(destination, staging, symlinks=True)
            else:
                staging.mkdir(parents=True)
            if record:
                recorded_files = record.get("files", {})
                for relative in set(recorded_files) - set(snapshot.files):
                    obsolete = staging / _safe_relative(relative)
                    if obsolete.is_symlink() or obsolete.is_file():
                        obsolete.unlink()
            self._copy_snapshot(snapshot, staging)

            if destination_existed:
                os.replace(destination, backup)
            os.replace(staging, destination)
            try:
                self.state_store.record_skill_installation(
                    platform=target.platform,
                    scope=target.scope,
                    mode=target.mode,
                    target_root=target.root,
                    skill_name=snapshot.name,
                    package_version=self.package_version,
                    source_hash=snapshot.source_hash,
                    files=snapshot.files,
                    installed_at=self.clock(),
                )
            except Exception:
                self._remove_tree(destination)
                if backup.exists():
                    os.replace(backup, destination)
                raise
            self._remove_tree(backup)
        except CommandError:
            raise
        except OSError as exc:
            if not destination.exists() and backup.exists():
                try:
                    os.replace(backup, destination)
                except OSError:
                    pass
            raise _io_error("commit_skill", destination, exc) from exc
        finally:
            self._remove_tree(staging)

    def _apply(
        self,
        target: SkillTarget,
        names: Optional[Iterable[str]],
        *,
        force: bool,
        require_existing: bool,
    ) -> dict[str, Any]:
        selected = self._selected(names)
        prepared: list[tuple[str, SkillSnapshot, Optional[dict[str, Any]], str]] = []
        for name in selected:
            snapshot = self.source.snapshot(name)
            record = self._record(target, name)
            details = self._diff_one(target, snapshot, record)
            if require_existing and record is None:
                prepared.append((name, snapshot, record, "not_installed"))
                continue
            if details["destination_exists"] and record is None and not force:
                raise _conflict(name, "unmanaged_target", destination=str(target.root / name))
            if details["target_modified"] and not force:
                raise _conflict(name, "managed_files_modified", paths=details["target_modified"])
            source_changed = bool(
                details["source_added"]
                or details["source_removed"]
                or details["source_changed"]
                or (record and record.get("source_hash") != snapshot.source_hash)
            )
            if record and details["destination_exists"] and not source_changed:
                action = "skipped"
            elif record:
                action = "updated"
            else:
                action = "installed"
            prepared.append((name, snapshot, record, action))

        result: dict[str, Any] = {
            "target": target.as_dict(),
            "installed": [],
            "updated": [],
            "skipped": [],
            "not_installed": [],
        }
        for name, snapshot, record, action in prepared:
            if action in {"skipped", "not_installed"}:
                result[action].append(name)
                continue
            self._apply_one(target, snapshot, record)
            result[action].append(name)
        return result

    def install(
        self,
        target: SkillTarget,
        names: Optional[Iterable[str]] = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        return self._apply(
            target,
            names,
            force=force,
            require_existing=False,
        )

    def update(
        self,
        target: SkillTarget,
        names: Optional[Iterable[str]] = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        return self._apply(
            target,
            names,
            force=force,
            require_existing=True,
        )

    @staticmethod
    def _prune_empty_directories(root: Path) -> None:
        if not root.is_dir():
            return
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass

    def uninstall(
        self,
        target: SkillTarget,
        names: Optional[Iterable[str]] = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        selected = self._selected(names)
        prepared: list[tuple[str, Optional[dict[str, Any]], dict[str, Any]]] = []
        for name in selected:
            snapshot = self.source.snapshot(name)
            record = self._record(target, name)
            details = self._diff_one(target, snapshot, record)
            if record and details["target_modified"] and not force:
                raise _conflict(name, "managed_files_modified", paths=details["target_modified"])
            prepared.append((name, record, details))

        result: dict[str, Any] = {
            "target": target.as_dict(),
            "uninstalled": [],
            "not_installed": [],
            "preserved_unmanaged": {},
        }
        for name, record, details in prepared:
            if record is None:
                result["not_installed"].append(name)
                continue
            destination = target.root / name
            for relative, expected_hash in record["files"].items():
                path = destination / _safe_relative(relative)
                current_hash = _hash_file(path)
                if path.is_symlink() or (path.exists() and (force or current_hash == expected_hash)):
                    try:
                        path.unlink()
                    except OSError as exc:
                        raise _io_error("uninstall_skill", path, exc) from exc
            self._prune_empty_directories(destination)
            self.state_store.delete_skill_installation(
                platform=target.platform,
                scope=target.scope,
                mode=target.mode,
                target_root=target.root,
                skill_name=name,
            )
            result["uninstalled"].append(name)
            result["preserved_unmanaged"][name] = details["target_unmanaged"]
        return result
