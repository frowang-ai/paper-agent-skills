from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional
from uuid import uuid4

from paper_agent.protocol import CommandError, ErrorCode, ExitCode
from paper_agent.storage import StateStore

from .library_service import LibraryService


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _error(code: ErrorCode, message: str, **details: object) -> CommandError:
    exit_code = (
        ExitCode.RESOURCE_STATE
        if code in {ErrorCode.NOT_FOUND, ErrorCode.NOT_READY}
        else ExitCode.CONFLICT
        if code == ErrorCode.CONFLICT
        else ExitCode.LOCAL_IO_OR_INTEGRITY
    )
    return CommandError(code=code, message=message, exit_code=exit_code, details=details)


def _segment(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or not _SAFE_SEGMENT.fullmatch(text) or text in {".", ".."}:
        raise _error(ErrorCode.INTEGRITY_ERROR, f"Invalid {label} path segment", value=text)
    return text


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def _paper_lock(root: Path, identity: str) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".lock"
    path = root / name
    for attempt in range(2):
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            break
        except FileExistsError as exc:
            if attempt == 0:
                try:
                    pid = int(path.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    pid = -1
                if not _process_exists(pid):
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    continue
            raise _error(
                ErrorCode.CONFLICT,
                "Another Paper Agent process is syncing this paper",
                lock=str(path),
            ) from exc
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


class ArtifactSyncService:
    def __init__(
        self,
        *,
        library: LibraryService,
        state_store: StateStore,
        data_dir: Path,
        profile: str,
        base_url: str,
        clock: Callable[[], str],
    ) -> None:
        self.library = library
        self.state_store = state_store
        self.data_dir = data_dir.expanduser().resolve()
        self.profile = _segment(profile, "profile")
        self.base_url = base_url
        self.clock = clock

    @property
    def papers_root(self) -> Path:
        return self.data_dir / "artifacts" / "papers" / self.profile

    def _verify(self, root: Path) -> dict[str, Any]:
        manifest_path = root / "artifact-manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = manifest["artifacts"]
            if manifest.get("status") != "committed" or not isinstance(artifacts, dict):
                raise ValueError("invalid manifest state")
            for artifact in artifacts.values():
                path = root / artifact["path"]
                if not path.is_file() or path.stat().st_size != artifact["bytes"]:
                    raise ValueError("artifact size mismatch")
                if _hash_file(path) != artifact["sha256"]:
                    raise ValueError("artifact hash mismatch")
            json.loads((root / artifacts["layout"]["path"]).read_text(encoding="utf-8"))
            if not (root / artifacts["fulltext"]["path"]).read_text(encoding="utf-8").strip():
                raise ValueError("empty markdown")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _error(
                ErrorCode.INTEGRITY_ERROR,
                "Cached paper revision failed integrity verification",
                path=str(root),
                error_type=type(exc).__name__,
            ) from exc
        return manifest

    def verify_revision(self, root: Path) -> dict[str, Any]:
        return self._verify(root.expanduser().resolve())

    def sync(self, paper_ref: str) -> dict[str, Any]:
        metadata = self.library.show(paper_ref)
        if not isinstance(metadata, dict):
            raise _error(ErrorCode.INTEGRITY_ERROR, "Paper metadata response is invalid")
        paper_id = _segment(metadata.get("paper_id"), "paper_id")
        revision = _segment(
            metadata.get("latest_task_id") or metadata.get("task_id"), "revision"
        )
        title = str(metadata.get("title") or "Untitled paper")
        short_id = paper_ref if re.fullmatch(r"P-[A-Za-z0-9]+", paper_ref) else None
        revision_root = self.papers_root / paper_id / revision

        with _paper_lock(self.data_dir / "locks", f"{self.profile}:{paper_id}"):
            if revision_root.exists():
                manifest = self._verify(revision_root)
                if (
                    manifest.get("profile") != self.profile
                    or manifest.get("paper_id") != paper_id
                    or manifest.get("revision") != revision
                    or manifest.get("source", {}).get("base_url") != self.base_url
                ):
                    raise _error(
                        ErrorCode.INTEGRITY_ERROR,
                        "Cached paper identity does not match the active profile",
                        path=str(revision_root),
                    )
                self._record(manifest, revision_root)
                return self._result(manifest, revision_root, cache_hit=True)

            remote_assets = self.library.assets(paper_ref)
            assets = remote_assets.get("assets") if isinstance(remote_assets, dict) else None
            if not isinstance(assets, dict):
                raise _error(ErrorCode.NOT_READY, "Paper assets are not ready", paper_id=paper_id)
            full_url = assets.get("ocr_markdown_url")
            layout_url = assets.get("layout_url")
            if not isinstance(full_url, str) or not isinstance(layout_url, str):
                raise _error(
                    ErrorCode.NOT_READY,
                    "Paper text assets are not ready",
                    paper_id=paper_id,
                    revision=revision,
                )
            tree_url = assets.get("attribute_tree_url")

            staging = self.papers_root / ".staging" / f"{paper_id}-{revision}-{uuid4().hex}"
            try:
                staging.mkdir(parents=True)
                academic = self.library.metadata(paper_ref)
                if not isinstance(academic, dict):
                    raise ValueError("invalid academic metadata")
                metadata_path = staging / "metadata.json"
                _write_json(metadata_path, academic)
                full_result = self.library.download_asset(full_url, staging / "full.md")
                layout_result = self.library.download_asset(layout_url, staging / "layout.json")
                if not (staging / "full.md").read_text(encoding="utf-8").strip():
                    raise ValueError("empty markdown")
                json.loads((staging / "layout.json").read_text(encoding="utf-8"))
                tree_result: Optional[dict[str, object]] = None
                if isinstance(tree_url, str) and tree_url:
                    tree_result = self.library.download_asset(
                        tree_url, staging / "attribute_tree.json"
                    )
                    json.loads(
                        (staging / "attribute_tree.json").read_text(encoding="utf-8")
                    )
                entries = {
                    "metadata": {
                        "path": "metadata.json",
                        "bytes": metadata_path.stat().st_size,
                        "sha256": _hash_file(metadata_path),
                        "required": True,
                    },
                    "fulltext": {
                        "path": "full.md",
                        "bytes": full_result["bytes"],
                        "sha256": full_result["sha256"],
                        "source_url": full_url,
                        "required": True,
                    },
                    "layout": {
                        "path": "layout.json",
                        "bytes": layout_result["bytes"],
                        "sha256": layout_result["sha256"],
                        "source_url": layout_url,
                        "required": True,
                    },
                }
                if tree_result is not None:
                    entries["attribute_tree"] = {
                        "path": "attribute_tree.json",
                        "bytes": tree_result["bytes"],
                        "sha256": tree_result["sha256"],
                        "source_url": tree_url,
                        "required": False,
                    }
                manifest = {
                    "schema_version": 1,
                    "status": "committed",
                    "profile": self.profile,
                    "paper_id": paper_id,
                    "short_id": short_id,
                    "title": title,
                    "revision": revision,
                    "source": {"base_url": self.base_url, "synced_at": self.clock()},
                    "sync_profile": "text",
                    "images_available": False,
                    "artifacts": entries,
                }
                _write_json(staging / "artifact-manifest.json", manifest)
                revision_root.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging, revision_root)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                raise _error(
                    ErrorCode.INTEGRITY_ERROR,
                    "Downloaded paper assets failed validation",
                    paper_id=paper_id,
                    revision=revision,
                    error_type=type(exc).__name__,
                ) from exc
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

            self._record(manifest, revision_root)
            return self._result(manifest, revision_root, cache_hit=False)

    def _record(self, manifest: dict[str, Any], root: Path) -> None:
        self.state_store.record_artifact_revision(
            profile=manifest["profile"],
            paper_id=manifest["paper_id"],
            short_id=manifest.get("short_id"),
            title=manifest["title"],
            revision=manifest["revision"],
            manifest_path=root / "artifact-manifest.json",
            synced_at=manifest["source"]["synced_at"],
            artifacts=manifest["artifacts"],
        )

    @staticmethod
    def _result(
        manifest: dict[str, Any], root: Path, *, cache_hit: bool
    ) -> dict[str, Any]:
        return {
            "paper_id": manifest["paper_id"],
            "short_id": manifest.get("short_id"),
            "title": manifest["title"],
            "revision": manifest["revision"],
            "revision_root": str(root),
            "manifest": str(root / "artifact-manifest.json"),
            "cache_hit": cache_hit,
            "artifacts": manifest["artifacts"],
        }
