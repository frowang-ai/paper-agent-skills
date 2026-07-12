from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from paper_agent.clients import ZoteroClient, ZoteroCollection, ZoteroPaper
from paper_agent.protocol import CommandError, ErrorCode, ExitCode
from paper_agent.storage import StateStore

from .library_service import LibraryService


def _safe_pdf_filename(title: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(". ")
    if not normalized:
        normalized = "Untitled"
    return f"{normalized[:120]}.pdf"


def _remote_id(data: Any, *names: str) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    for name in names:
        value = data.get(name)
        if isinstance(value, str) and value:
            return value
    return None


class ZoteroImportService:
    def __init__(
        self,
        *,
        zotero: ZoteroClient,
        library: Optional[LibraryService],
        state_store: StateStore,
        profile: str,
        clock: Callable[[], str],
        sleep: Callable[[float], None] = time.sleep,
        upload_interval_seconds: float = 1.0,
    ) -> None:
        self.zotero = zotero
        self.library = library
        self.state_store = state_store
        self.profile = profile
        self.clock = clock
        self.sleep = sleep
        self.upload_interval_seconds = upload_interval_seconds
        self.state_store.initialize()

    def _library(self) -> LibraryService:
        if self.library is None:
            raise CommandError(
                code=ErrorCode.AUTH_MISSING,
                message="Frowang credentials are required for Zotero upload",
                exit_code=ExitCode.CONFIG_OR_AUTH,
            )
        return self.library

    @property
    def library_id(self) -> str:
        return self.zotero.library_id

    def collections(self) -> dict[str, Any]:
        collections = self.zotero.list_collections()
        by_parent: dict[Optional[str], list[ZoteroCollection]] = {}
        for item in collections:
            by_parent.setdefault(item.parent_key, []).append(item)
        rendered: list[dict[str, object]] = []

        def walk(item: ZoteroCollection, depth: int) -> None:
            rendered.append(
                ZoteroCollection(item.key, item.name, item.parent_key, depth).as_dict()
            )
            for child in by_parent.get(item.key, []):
                walk(child, depth + 1)

        for root in by_parent.get(None, []):
            walk(root, 0)
        return {
            "mode": self.zotero.mode,
            "library_id": self.library_id,
            "count": len(rendered),
            "collections": rendered,
        }

    def items(self, collection_key: str, *, recursive: bool = False) -> dict[str, Any]:
        tree = (
            self.zotero.collection_tree(collection_key)
            if recursive
            else [self.zotero.collection_tree(collection_key)[0]]
        )
        groups: list[dict[str, Any]] = []
        total = 0
        with_pdf = 0
        for collection in tree:
            papers = self.zotero.collection_papers(collection.key)
            total += len(papers)
            with_pdf += sum(paper.has_local_pdf for paper in papers)
            groups.append(
                {
                    "collection": collection.as_dict(),
                    "papers": [paper.as_dict() for paper in papers],
                }
            )
        return {
            "mode": self.zotero.mode,
            "library_id": self.library_id,
            "recursive": recursive,
            "total": total,
            "with_local_pdf": with_pdf,
            "groups": groups,
        }

    def _require_pdf(self, paper: ZoteroPaper) -> Path:
        if paper.pdf_path is None:
            raise CommandError(
                code=ErrorCode.NOT_READY,
                message="Zotero PDF attachment is not available locally",
                exit_code=ExitCode.RESOURCE_STATE,
                details={
                    "item_key": paper.item_key,
                    "attachment_key": paper.attachment_key,
                },
            )
        return paper.pdf_path

    def _upload_paper(self, paper: ZoteroPaper) -> dict[str, Any]:
        response = self._library().upload(
            self._require_pdf(paper),
            filename=_safe_pdf_filename(paper.title),
        )
        if not isinstance(response, dict):
            raise CommandError(
                code=ErrorCode.REMOTE_ERROR,
                message="Frowang upload returned an unexpected response",
                exit_code=ExitCode.NETWORK_OR_REMOTE,
            )
        task_id = _remote_id(response, "task_id")
        if not task_id:
            raise CommandError(
                code=ErrorCode.REMOTE_ERROR,
                message="Frowang upload response did not include task_id",
                exit_code=ExitCode.NETWORK_OR_REMOTE,
                details={"item_key": paper.item_key},
            )
        return response

    def _record_item(self, paper: ZoteroPaper, response: dict[str, Any]) -> None:
        task_id = _remote_id(response, "task_id")
        assert task_id is not None
        self.state_store.record_zotero_item(
            profile=self.profile,
            library_id=self.library_id,
            item_key=paper.item_key,
            frowang_paper_id=_remote_id(response, "paper_id"),
            short_id=_remote_id(response, "short_id"),
            task_id=task_id,
            synced_at=self.clock(),
        )

    def upload_one(
        self,
        item_key: str,
        *,
        target_collection: Optional[str] = None,
        no_sync: bool = False,
    ) -> dict[str, Any]:
        existing = self.state_store.get_zotero_item(
            self.profile, self.library_id, item_key
        )
        if existing and not no_sync:
            return {"status": "skipped", "reason": "already_synced", **existing}
        paper = self.zotero.paper(item_key)
        response = self._upload_paper(paper)
        task_id = _remote_id(response, "task_id")
        assert task_id is not None
        if target_collection:
            self._library().add_collection_items(target_collection, [task_id])
        self._record_item(paper, response)
        return {
            "status": "uploaded" if response.get("is_new", True) else "duplicate",
            "item_key": item_key,
            "title": paper.title,
            "paper_id": _remote_id(response, "paper_id"),
            "short_id": _remote_id(response, "short_id"),
            "task_id": task_id,
            "target_collection": target_collection,
        }

    def _collect_memberships(
        self, tree: list[ZoteroCollection]
    ) -> tuple[dict[str, ZoteroPaper], dict[str, set[str]]]:
        papers: dict[str, ZoteroPaper] = {}
        memberships: dict[str, set[str]] = {}
        for collection in tree:
            for paper in self.zotero.collection_papers(collection.key):
                papers.setdefault(paper.item_key, paper)
                memberships.setdefault(paper.item_key, set()).add(collection.key)
        return papers, memberships

    def _collection_mapping(
        self,
        tree: list[ZoteroCollection],
        *,
        root_name: Optional[str],
    ) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for collection in tree:
            existing = self.state_store.get_zotero_collection(
                self.profile, self.library_id, collection.key
            )
            if existing:
                mapping[collection.key] = existing["frowang_collection_id"]
                continue
            parent_id = mapping.get(collection.parent_key) if collection.parent_key else None
            name = root_name if collection.depth == 0 and root_name else collection.name
            response = self._library().create_collection(name, parent_id)
            collection_id = _remote_id(response, "short_id", "key", "id")
            if not collection_id:
                raise CommandError(
                    code=ErrorCode.REMOTE_ERROR,
                    message="Frowang collection response did not include an identifier",
                    exit_code=ExitCode.NETWORK_OR_REMOTE,
                    details={"zotero_collection_key": collection.key},
                )
            mapping[collection.key] = collection_id
            self.state_store.record_zotero_collection(
                profile=self.profile,
                library_id=self.library_id,
                collection_key=collection.key,
                frowang_collection_id=collection_id,
                name=name,
                synced_at=self.clock(),
            )
        return mapping

    def upload_collection(
        self,
        collection_key: str,
        *,
        frowang_name: Optional[str] = None,
        dry_run: bool = False,
        no_sync: bool = False,
    ) -> dict[str, Any]:
        tree = self.zotero.collection_tree(collection_key)
        papers, memberships = self._collect_memberships(tree)
        pending: dict[str, ZoteroPaper] = {}
        already_synced = 0
        missing_pdf = 0
        for item_key, paper in papers.items():
            existing = self.state_store.get_zotero_item(
                self.profile, self.library_id, item_key
            )
            if existing and not no_sync:
                already_synced += 1
            elif not paper.has_local_pdf:
                missing_pdf += 1
            else:
                pending[item_key] = paper

        preview = {
            "mode": self.zotero.mode,
            "library_id": self.library_id,
            "root_collection": collection_key,
            "collection_count": len(tree),
            "unique_papers": len(papers),
            "pending": len(pending),
            "skipped": already_synced,
            "missing_pdf": missing_pdf,
            "dry_run": dry_run,
            "papers": [
                {
                    "item_key": paper.item_key,
                    "title": paper.title,
                    "collections": sorted(memberships[paper.item_key]),
                }
                for paper in pending.values()
            ],
        }
        if dry_run or not pending:
            return {
                **preview,
                "uploaded": 0,
                "duplicates": 0,
                "errors": 0,
                "results": [],
            }

        remote_collections = self._collection_mapping(tree, root_name=frowang_name)
        results: list[dict[str, Any]] = []
        uploaded = 0
        duplicates = 0
        errors = 0
        membership_errors_total = 0
        pending_values = list(pending.values())
        for index, paper in enumerate(pending_values):
            try:
                response = self._upload_paper(paper)
                task_id = _remote_id(response, "task_id")
                assert task_id is not None
                membership_errors: list[dict[str, str]] = []
                for zotero_collection in sorted(memberships[paper.item_key]):
                    target = remote_collections[zotero_collection]
                    try:
                        self._library().add_collection_items(target, [task_id])
                    except CommandError as exc:
                        membership_errors.append(
                            {"collection": target, "code": exc.code.value, "message": exc.message}
                        )
                self._record_item(paper, response)
                membership_errors_total += len(membership_errors)
                status = "uploaded" if response.get("is_new", True) else "duplicate"
                uploaded += status == "uploaded"
                duplicates += status == "duplicate"
                results.append(
                    {
                        "item_key": paper.item_key,
                        "title": paper.title,
                        "status": status,
                        "paper_id": _remote_id(response, "paper_id"),
                        "short_id": _remote_id(response, "short_id"),
                        "task_id": task_id,
                        "membership_errors": membership_errors,
                    }
                )
            except CommandError as exc:
                errors += 1
                results.append(
                    {
                        "item_key": paper.item_key,
                        "title": paper.title,
                        "status": "error",
                        "error_code": exc.code.value,
                        "reason": exc.message,
                    }
                )
            if index + 1 < len(pending_values) and self.upload_interval_seconds > 0:
                self.sleep(self.upload_interval_seconds)
        return {
            **preview,
            "uploaded": uploaded,
            "duplicates": duplicates,
            "errors": errors,
            "membership_errors": membership_errors_total,
            "results": results,
            "remote_collections": remote_collections,
        }

    def status(self, *, limit: int = 20) -> dict[str, Any]:
        return self.state_store.zotero_status(
            self.profile, self.library_id, limit=limit
        )

    def migrate_state(self, source: Path) -> dict[str, int]:
        return self.state_store.import_legacy_zotero_json(
            source,
            profile=self.profile,
            library_id=self.library_id,
        )
