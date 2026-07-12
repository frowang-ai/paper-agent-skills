from __future__ import annotations

import configparser
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from paper_agent.config.settings import ZoteroSettings
from paper_agent.protocol import CommandError, ErrorCode, ExitCode


@dataclass(frozen=True)
class ZoteroCollection:
    key: str
    name: str
    parent_key: Optional[str]
    depth: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ZoteroPaper:
    item_key: str
    title: str
    attachment_key: Optional[str]
    attachment_filename: Optional[str]
    pdf_path: Optional[Path]

    @property
    def has_local_pdf(self) -> bool:
        return self.pdf_path is not None

    def as_dict(self) -> dict[str, object]:
        return {
            "item_key": self.item_key,
            "title": self.title,
            "attachment_key": self.attachment_key,
            "attachment_filename": self.attachment_filename,
            "has_local_pdf": self.has_local_pdf,
            "pdf_path": str(self.pdf_path) if self.pdf_path else None,
        }


class ZoteroBackend(Protocol):
    def collections(self, *, start: int, limit: int) -> list[dict[str, Any]]: ...
    def collection_items(
        self, key: str, *, start: int, limit: int
    ) -> list[dict[str, Any]]: ...
    def children(self, key: str) -> list[dict[str, Any]]: ...
    def item(self, key: str) -> dict[str, Any]: ...


def _zotero_error(operation: str, mode: str, exc: Exception) -> CommandError:
    message = str(exc).lower()
    if "401" in message or "403" in message or "forbidden" in message:
        return CommandError(
            code=ErrorCode.AUTH_INVALID,
            message="Zotero rejected the configured credential",
            exit_code=ExitCode.CONFIG_OR_AUTH,
            details={
                "provider": "zotero",
                "operation": operation,
                "mode": mode,
                "error_type": type(exc).__name__,
            },
        )
    if "404" in message:
        return CommandError(
            code=ErrorCode.NOT_FOUND,
            message="Zotero resource was not found",
            exit_code=ExitCode.RESOURCE_STATE,
            details={"provider": "zotero", "operation": operation, "mode": mode},
        )
    return CommandError(
        code=ErrorCode.NETWORK_ERROR,
        message=(
            "Could not connect to the Zotero local API"
            if mode == "local"
            else "Could not connect to the Zotero Web API"
        ),
        exit_code=ExitCode.NETWORK_OR_REMOTE,
        details={
            "provider": "zotero",
            "operation": operation,
            "mode": mode,
            "error_type": type(exc).__name__,
        },
        retryable=True,
    )


def _profile_candidates() -> list[Path]:
    home = Path.home()
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Zotero" / "Zotero" / "profiles.ini")
    candidates.extend(
        [
            home / "AppData" / "Roaming" / "Zotero" / "Zotero" / "profiles.ini",
            home / "Library" / "Application Support" / "Zotero" / "profiles.ini",
            home / ".zotero" / "zotero" / "profiles.ini",
        ]
    )
    return candidates


def discover_zotero_storage(
    *,
    profiles_ini: Optional[Path] = None,
    explicit_storage_dir: Optional[Path] = None,
) -> Optional[Path]:
    if explicit_storage_dir is not None:
        resolved = explicit_storage_dir.expanduser().resolve()
        return resolved if resolved.is_dir() else None

    ini_path = profiles_ini.expanduser().resolve() if profiles_ini else next(
        (candidate.expanduser().resolve() for candidate in _profile_candidates() if candidate.is_file()),
        None,
    )
    if ini_path is not None and ini_path.is_file():
        parser = configparser.ConfigParser()
        try:
            parser.read(ini_path, encoding="utf-8")
        except (OSError, configparser.Error):
            parser = configparser.ConfigParser()
        sections = parser.sections()
        selected = next(
            (section for section in sections if parser.get(section, "Default", fallback="0") == "1"),
            sections[0] if sections else None,
        )
        if selected:
            raw_profile = parser.get(selected, "Path", fallback="").strip()
            if raw_profile:
                profile_path = Path(raw_profile)
                if parser.get(selected, "IsRelative", fallback="1") == "1":
                    profile_path = ini_path.parent / profile_path
                prefs = profile_path.expanduser().resolve() / "prefs.js"
                if prefs.is_file():
                    try:
                        content = prefs.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        content = ""
                    match = re.search(
                        r'user_pref\("extensions\.zotero\.dataDir",\s*"([^"]+)"\)',
                        content,
                    )
                    if match:
                        raw_data_dir = match.group(1).replace("\\\\", "\\")
                        storage = (Path(raw_data_dir).expanduser() / "storage").resolve()
                        if storage.is_dir():
                            return storage

    defaults = [Path.home() / "Zotero" / "storage"]
    return next((path.resolve() for path in defaults if path.is_dir()), None)


def find_attachment_pdf(attachment_key: str, storage_dir: Path) -> Optional[Path]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attachment_key):
        raise CommandError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Invalid Zotero attachment key",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        )
    root = storage_dir.expanduser().resolve()
    attachment_dir = (root / attachment_key).resolve()
    if attachment_dir.parent != root or not attachment_dir.is_dir():
        return None
    try:
        pdfs = sorted(
            (path for path in attachment_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
            key=lambda path: path.name.lower(),
        )
    except OSError as exc:
        raise CommandError(
            code=ErrorCode.LOCAL_IO_ERROR,
            message="Could not inspect Zotero attachment storage",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
            details={"path": str(attachment_dir), "error_type": type(exc).__name__},
        ) from exc
    return pdfs[0].resolve() if pdfs else None


class ZoteroClient:
    def __init__(
        self,
        *,
        backend: ZoteroBackend,
        mode: str,
        library_id: str,
        library_type: str,
        storage_dir: Optional[Path],
    ) -> None:
        self.backend = backend
        self.mode = mode
        self.library_id = library_id
        self.library_type = library_type
        self.storage_dir = storage_dir.expanduser().resolve() if storage_dir else None

    def _call(self, operation: str, function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except CommandError:
            raise
        except Exception as exc:
            raise _zotero_error(operation, self.mode, exc) from exc

    def check(self) -> None:
        self._call("check", self.backend.collections, start=0, limit=1)

    def list_collections(self) -> list[ZoteroCollection]:
        raw: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = self._call(
                "list_collections", self.backend.collections, start=start, limit=100
            )
            raw.extend(batch)
            if len(batch) < 100:
                break
            start += 100
        result: list[ZoteroCollection] = []
        for item in raw:
            data = item.get("data", {})
            key = data.get("key")
            name = data.get("name")
            if isinstance(key, str) and isinstance(name, str):
                parent = data.get("parentCollection")
                result.append(
                    ZoteroCollection(
                        key=key,
                        name=name,
                        parent_key=parent if isinstance(parent, str) and parent else None,
                    )
                )
        return result

    def collection_tree(self, root_key: str) -> list[ZoteroCollection]:
        collections = self.list_collections()
        by_key = {item.key: item for item in collections}
        if root_key not in by_key:
            raise CommandError(
                code=ErrorCode.NOT_FOUND,
                message="Zotero collection was not found",
                exit_code=ExitCode.RESOURCE_STATE,
                details={"collection_key": root_key},
            )
        children: dict[str, list[ZoteroCollection]] = {}
        for item in collections:
            if item.parent_key:
                children.setdefault(item.parent_key, []).append(item)
        result: list[ZoteroCollection] = []

        def walk(key: str, depth: int) -> None:
            item = by_key[key]
            result.append(
                ZoteroCollection(item.key, item.name, item.parent_key, depth)
            )
            for child in children.get(key, []):
                walk(child.key, depth + 1)

        walk(root_key, 0)
        return result

    def _raw_collection_items(self, collection_key: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = self._call(
                "collection_items",
                self.backend.collection_items,
                collection_key,
                start=start,
                limit=100,
            )
            result.extend(batch)
            if len(batch) < 100:
                break
            start += 100
        return result

    def _paper_from_data(self, data: dict[str, Any]) -> ZoteroPaper:
        item_key = data.get("key")
        if not isinstance(item_key, str) or not item_key:
            raise CommandError(
                code=ErrorCode.REMOTE_ERROR,
                message="Zotero item is missing its key",
                exit_code=ExitCode.NETWORK_OR_REMOTE,
            )
        title = data.get("title")
        children = self._call("item_children", self.backend.children, item_key)
        attachment_key: Optional[str] = None
        attachment_filename: Optional[str] = None
        for child in children:
            child_data = child.get("data", {})
            if child_data.get("contentType") == "application/pdf":
                raw_key = child.get("key") or child_data.get("key")
                if isinstance(raw_key, str):
                    attachment_key = raw_key
                    raw_filename = child_data.get("filename")
                    attachment_filename = raw_filename if isinstance(raw_filename, str) else None
                    break
        pdf_path = (
            find_attachment_pdf(attachment_key, self.storage_dir)
            if attachment_key and self.storage_dir
            else None
        )
        return ZoteroPaper(
            item_key=item_key,
            title=title if isinstance(title, str) and title.strip() else "Untitled",
            attachment_key=attachment_key,
            attachment_filename=attachment_filename,
            pdf_path=pdf_path,
        )

    def collection_papers(self, collection_key: str) -> list[ZoteroPaper]:
        result: list[ZoteroPaper] = []
        for item in self._raw_collection_items(collection_key):
            data = item.get("data", {})
            if data.get("itemType") in {"attachment", "note"}:
                continue
            result.append(self._paper_from_data(data))
        return result

    def paper(self, item_key: str) -> ZoteroPaper:
        item = self._call("get_item", self.backend.item, item_key)
        return self._paper_from_data(item.get("data", {}))


def create_zotero_client(
    settings: ZoteroSettings,
    *,
    api_key: Optional[str] = None,
) -> ZoteroClient:
    try:
        from pyzotero import zotero as zotero_lib
    except ImportError as exc:  # pragma: no cover - packaging contract
        raise CommandError(
            code=ErrorCode.CONFIG_INVALID,
            message="The pyzotero runtime dependency is not installed",
            exit_code=ExitCode.CONFIG_OR_AUTH,
        ) from exc

    if settings.mode == "remote" and not api_key:
        raise CommandError(
            code=ErrorCode.AUTH_MISSING,
            message="Zotero API key is required in remote mode",
            exit_code=ExitCode.CONFIG_OR_AUTH,
        )
    backend = zotero_lib.Zotero(
        library_id=settings.library_id,
        library_type=settings.library_type,
        api_key=api_key if settings.mode == "remote" else None,
        local=settings.mode == "local",
    )
    configured_storage = Path(settings.storage_dir) if settings.storage_dir else None
    storage_dir = discover_zotero_storage(explicit_storage_dir=configured_storage)
    return ZoteroClient(
        backend=backend,
        mode=settings.mode,
        library_id=settings.library_id,
        library_type=settings.library_type,
        storage_dir=storage_dir,
    )
