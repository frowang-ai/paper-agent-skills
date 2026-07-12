from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Optional

from paper_agent.protocol import CommandError, ErrorCode, ExitCode


_SCHEMA_VERSION = 2


def _store_error(operation: str, path: Path, exc: Exception) -> CommandError:
    return CommandError(
        code=ErrorCode.LOCAL_IO_ERROR,
        message="Paper Agent could not access the global state database",
        exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        details={
            "operation": operation,
            "path": str(path),
            "error_type": type(exc).__name__,
        },
    )


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def _connect(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
        except (OSError, sqlite3.Error) as exc:
            raise _store_error("connect", self.path, exc) from exc
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS state_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS zotero_items (
                        profile TEXT NOT NULL,
                        library_id TEXT NOT NULL,
                        item_key TEXT NOT NULL,
                        frowang_paper_id TEXT,
                        short_id TEXT,
                        task_id TEXT NOT NULL,
                        synced_at TEXT NOT NULL,
                        PRIMARY KEY (profile, library_id, item_key)
                    );

                    CREATE TABLE IF NOT EXISTS zotero_collections (
                        profile TEXT NOT NULL,
                        library_id TEXT NOT NULL,
                        collection_key TEXT NOT NULL,
                        frowang_collection_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        synced_at TEXT NOT NULL,
                        PRIMARY KEY (profile, library_id, collection_key)
                    );

                    CREATE TABLE IF NOT EXISTS skill_installations (
                        platform TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        target_root TEXT NOT NULL,
                        skill_name TEXT NOT NULL,
                        package_version TEXT NOT NULL,
                        source_hash TEXT NOT NULL,
                        files_json TEXT NOT NULL,
                        installed_at TEXT NOT NULL,
                        PRIMARY KEY (
                            platform, scope, mode, target_root, skill_name
                        )
                    );

                    CREATE TABLE IF NOT EXISTS artifact_papers (
                        profile TEXT NOT NULL,
                        paper_id TEXT NOT NULL,
                        short_id TEXT,
                        title TEXT NOT NULL,
                        current_revision TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (profile, paper_id)
                    );

                    CREATE TABLE IF NOT EXISTS artifact_revisions (
                        profile TEXT NOT NULL,
                        paper_id TEXT NOT NULL,
                        revision TEXT NOT NULL,
                        status TEXT NOT NULL,
                        manifest_path TEXT NOT NULL,
                        synced_at TEXT NOT NULL,
                        PRIMARY KEY (profile, paper_id, revision)
                    );

                    CREATE TABLE IF NOT EXISTS artifacts (
                        profile TEXT NOT NULL,
                        paper_id TEXT NOT NULL,
                        revision TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        relative_path TEXT NOT NULL,
                        bytes INTEGER NOT NULL,
                        sha256 TEXT NOT NULL,
                        source_url TEXT,
                        PRIMARY KEY (profile, paper_id, revision, kind)
                    );

                    CREATE TABLE IF NOT EXISTS workspaces (
                        workspace_id TEXT PRIMARY KEY,
                        root_path TEXT NOT NULL UNIQUE,
                        manifest_path TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS workspace_papers (
                        workspace_id TEXT NOT NULL,
                        profile TEXT NOT NULL,
                        paper_id TEXT NOT NULL,
                        revision TEXT NOT NULL,
                        tracking_mode TEXT NOT NULL,
                        materialization_mode TEXT NOT NULL,
                        PRIMARY KEY (workspace_id, profile, paper_id)
                    );
                    """
                )
                connection.execute(
                    """
                    INSERT INTO state_metadata(key, value) VALUES('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    (str(_SCHEMA_VERSION),),
                )
        except sqlite3.Error as exc:
            raise _store_error("initialize", self.path, exc) from exc

    @staticmethod
    def _row(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        return dict(row) if row is not None else None

    def get_zotero_item(
        self, profile: str, library_id: str, item_key: str
    ) -> Optional[dict[str, Any]]:
        self.initialize()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM zotero_items
                    WHERE profile = ? AND library_id = ? AND item_key = ?
                    """,
                    (profile, library_id, item_key),
                ).fetchone()
        except sqlite3.Error as exc:
            raise _store_error("get_zotero_item", self.path, exc) from exc
        return self._row(row)

    def record_zotero_item(
        self,
        *,
        profile: str,
        library_id: str,
        item_key: str,
        frowang_paper_id: Optional[str],
        short_id: Optional[str],
        task_id: str,
        synced_at: str,
    ) -> None:
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO zotero_items(
                        profile, library_id, item_key, frowang_paper_id,
                        short_id, task_id, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile, library_id, item_key) DO UPDATE SET
                        frowang_paper_id=excluded.frowang_paper_id,
                        short_id=excluded.short_id,
                        task_id=excluded.task_id,
                        synced_at=excluded.synced_at
                    """,
                    (
                        profile,
                        library_id,
                        item_key,
                        frowang_paper_id,
                        short_id,
                        task_id,
                        synced_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise _store_error("record_zotero_item", self.path, exc) from exc

    def get_zotero_collection(
        self, profile: str, library_id: str, collection_key: str
    ) -> Optional[dict[str, Any]]:
        self.initialize()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM zotero_collections
                    WHERE profile = ? AND library_id = ? AND collection_key = ?
                    """,
                    (profile, library_id, collection_key),
                ).fetchone()
        except sqlite3.Error as exc:
            raise _store_error("get_zotero_collection", self.path, exc) from exc
        return self._row(row)

    def record_zotero_collection(
        self,
        *,
        profile: str,
        library_id: str,
        collection_key: str,
        frowang_collection_id: str,
        name: str,
        synced_at: str,
    ) -> None:
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO zotero_collections(
                        profile, library_id, collection_key,
                        frowang_collection_id, name, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile, library_id, collection_key) DO UPDATE SET
                        frowang_collection_id=excluded.frowang_collection_id,
                        name=excluded.name,
                        synced_at=excluded.synced_at
                    """,
                    (
                        profile,
                        library_id,
                        collection_key,
                        frowang_collection_id,
                        name,
                        synced_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise _store_error("record_zotero_collection", self.path, exc) from exc

    def zotero_status(
        self, profile: str, library_id: str, *, limit: int = 20
    ) -> dict[str, Any]:
        self.initialize()
        try:
            with self._connect() as connection:
                item_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM zotero_items
                    WHERE profile = ? AND library_id = ?
                    """,
                    (profile, library_id),
                ).fetchone()[0]
                collection_count = connection.execute(
                    """
                    SELECT COUNT(*) FROM zotero_collections
                    WHERE profile = ? AND library_id = ?
                    """,
                    (profile, library_id),
                ).fetchone()[0]
                recent = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT item_key, frowang_paper_id, short_id, task_id, synced_at
                        FROM zotero_items
                        WHERE profile = ? AND library_id = ?
                        ORDER BY synced_at DESC, item_key ASC
                        LIMIT ?
                        """,
                        (profile, library_id, limit),
                    ).fetchall()
                ]
        except sqlite3.Error as exc:
            raise _store_error("zotero_status", self.path, exc) from exc
        return {
            "profile": profile,
            "library_id": library_id,
            "state_db": str(self.path),
            "item_count": item_count,
            "collection_count": collection_count,
            "recent_items": recent,
        }

    def import_legacy_zotero_json(
        self,
        source: Path,
        *,
        profile: str,
        library_id: str,
    ) -> dict[str, int]:
        path = source.expanduser().resolve()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CommandError(
                code=ErrorCode.NOT_FOUND,
                message="Legacy Zotero sync state was not found",
                exit_code=ExitCode.RESOURCE_STATE,
                details={"path": str(path)},
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(
                code=ErrorCode.INTEGRITY_ERROR,
                message="Legacy Zotero sync state is not valid JSON",
                exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
                details={"path": str(path), "error_type": type(exc).__name__},
            ) from exc
        if not isinstance(raw, dict):
            raise CommandError(
                code=ErrorCode.INTEGRITY_ERROR,
                message="Legacy Zotero sync state root must be an object",
                exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
                details={"path": str(path)},
            )

        imported = 0
        skipped = 0
        self.initialize()
        for item_key, value in raw.items():
            if not isinstance(item_key, str) or not isinstance(value, dict):
                skipped += 1
                continue
            if self.get_zotero_item(profile, library_id, item_key):
                skipped += 1
                continue
            task_id = value.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                skipped += 1
                continue
            legacy_id = value.get("frowang_id")
            frowang_id = legacy_id if isinstance(legacy_id, str) else None
            synced_at = value.get("synced_at")
            self.record_zotero_item(
                profile=profile,
                library_id=library_id,
                item_key=item_key,
                frowang_paper_id=(
                    frowang_id if frowang_id and not frowang_id.startswith("P-") else None
                ),
                short_id=(frowang_id if frowang_id and frowang_id.startswith("P-") else None),
                task_id=task_id,
                synced_at=synced_at if isinstance(synced_at, str) else "legacy-import",
            )
            imported += 1
        return {"imported": imported, "skipped": skipped, "total": len(raw)}

    @staticmethod
    def _installation_row(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        result = dict(row)
        result["files"] = json.loads(result.pop("files_json"))
        return result

    def get_skill_installation(
        self,
        *,
        platform: str,
        scope: str,
        mode: str,
        target_root: Path,
        skill_name: str,
    ) -> Optional[dict[str, Any]]:
        self.initialize()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM skill_installations
                    WHERE platform = ? AND scope = ? AND mode = ?
                      AND target_root = ? AND skill_name = ?
                    """,
                    (
                        platform,
                        scope,
                        mode,
                        str(target_root.expanduser().resolve()),
                        skill_name,
                    ),
                ).fetchone()
        except sqlite3.Error as exc:
            raise _store_error("get_skill_installation", self.path, exc) from exc
        return self._installation_row(row)

    def list_skill_installations(
        self,
        *,
        platform: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        conditions: list[str] = []
        values: list[str] = []
        if platform:
            conditions.append("platform = ?")
            values.append(platform)
        if scope:
            conditions.append("scope = ?")
            values.append(scope)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT * FROM skill_installations
                    {where}
                    ORDER BY platform, scope, target_root, skill_name
                    """,
                    values,
                ).fetchall()
        except sqlite3.Error as exc:
            raise _store_error("list_skill_installations", self.path, exc) from exc
        return [self._installation_row(row) for row in rows if row is not None]

    def record_skill_installation(
        self,
        *,
        platform: str,
        scope: str,
        mode: str,
        target_root: Path,
        skill_name: str,
        package_version: str,
        source_hash: str,
        files: Mapping[str, str],
        installed_at: str,
    ) -> None:
        self.initialize()
        try:
            files_json = json.dumps(dict(files), sort_keys=True, separators=(",", ":"))
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO skill_installations(
                        platform, scope, mode, target_root, skill_name,
                        package_version, source_hash, files_json, installed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(
                        platform, scope, mode, target_root, skill_name
                    ) DO UPDATE SET
                        package_version=excluded.package_version,
                        source_hash=excluded.source_hash,
                        files_json=excluded.files_json,
                        installed_at=excluded.installed_at
                    """,
                    (
                        platform,
                        scope,
                        mode,
                        str(target_root.expanduser().resolve()),
                        skill_name,
                        package_version,
                        source_hash,
                        files_json,
                        installed_at,
                    ),
                )
        except (TypeError, sqlite3.Error) as exc:
            raise _store_error("record_skill_installation", self.path, exc) from exc

    def delete_skill_installation(
        self,
        *,
        platform: str,
        scope: str,
        mode: str,
        target_root: Path,
        skill_name: str,
    ) -> None:
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    DELETE FROM skill_installations
                    WHERE platform = ? AND scope = ? AND mode = ?
                      AND target_root = ? AND skill_name = ?
                    """,
                    (
                        platform,
                        scope,
                        mode,
                        str(target_root.expanduser().resolve()),
                        skill_name,
                    ),
                )
        except sqlite3.Error as exc:
            raise _store_error("delete_skill_installation", self.path, exc) from exc

    def get_artifact_revision(
        self, profile: str, paper_id: str, revision: str
    ) -> Optional[dict[str, Any]]:
        self.initialize()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM artifact_revisions
                    WHERE profile = ? AND paper_id = ? AND revision = ?
                    """,
                    (profile, paper_id, revision),
                ).fetchone()
        except sqlite3.Error as exc:
            raise _store_error("get_artifact_revision", self.path, exc) from exc
        return self._row(row)

    def record_artifact_revision(
        self,
        *,
        profile: str,
        paper_id: str,
        short_id: Optional[str],
        title: str,
        revision: str,
        manifest_path: Path,
        synced_at: str,
        artifacts: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO artifact_papers(
                        profile, paper_id, short_id, title,
                        current_revision, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(profile, paper_id) DO UPDATE SET
                        short_id=excluded.short_id,
                        title=excluded.title,
                        current_revision=excluded.current_revision,
                        updated_at=excluded.updated_at
                    """,
                    (profile, paper_id, short_id, title, revision, synced_at),
                )
                connection.execute(
                    """
                    INSERT INTO artifact_revisions(
                        profile, paper_id, revision, status,
                        manifest_path, synced_at
                    ) VALUES (?, ?, ?, 'committed', ?, ?)
                    ON CONFLICT(profile, paper_id, revision) DO UPDATE SET
                        status='committed',
                        manifest_path=excluded.manifest_path,
                        synced_at=excluded.synced_at
                    """,
                    (profile, paper_id, revision, str(manifest_path), synced_at),
                )
                connection.execute(
                    "DELETE FROM artifacts WHERE profile = ? AND paper_id = ? AND revision = ?",
                    (profile, paper_id, revision),
                )
                for kind, artifact in artifacts.items():
                    connection.execute(
                        """
                        INSERT INTO artifacts(
                            profile, paper_id, revision, kind, relative_path,
                            bytes, sha256, source_url
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            profile,
                            paper_id,
                            revision,
                            kind,
                            artifact["path"],
                            artifact["bytes"],
                            artifact["sha256"],
                            artifact.get("source_url"),
                        ),
                    )
        except (KeyError, TypeError, sqlite3.Error) as exc:
            raise _store_error("record_artifact_revision", self.path, exc) from exc

    def record_workspace(
        self,
        *,
        workspace_id: str,
        root_path: Path,
        manifest_path: Path,
        last_seen_at: str,
        papers: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO workspaces(
                        workspace_id, root_path, manifest_path, last_seen_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(workspace_id) DO UPDATE SET
                        root_path=excluded.root_path,
                        manifest_path=excluded.manifest_path,
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        workspace_id,
                        str(root_path.expanduser().resolve()),
                        str(manifest_path.expanduser().resolve()),
                        last_seen_at,
                    ),
                )
                connection.execute(
                    "DELETE FROM workspace_papers WHERE workspace_id = ?",
                    (workspace_id,),
                )
                for paper_id, paper in papers.items():
                    connection.execute(
                        """
                        INSERT INTO workspace_papers(
                            workspace_id, profile, paper_id, revision,
                            tracking_mode, materialization_mode
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            workspace_id,
                            paper["profile"],
                            paper_id,
                            paper["revision"],
                            paper.get("tracking", "latest"),
                            paper.get("materialization", "copy"),
                        ),
                    )
        except (KeyError, TypeError, sqlite3.Error) as exc:
            raise _store_error("record_workspace", self.path, exc) from exc
