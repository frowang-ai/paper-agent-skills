from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from paper_agent.protocol import CommandError, ErrorCode, ExitCode
from paper_agent.skills import SkillSource


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _remove(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


class PluginBundleBuilder:
    def __init__(self, source: SkillSource) -> None:
        self.source = source

    @staticmethod
    def _manifests(version: str) -> tuple[dict[str, object], dict[str, object]]:
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", version):
            raise CommandError(
                code=ErrorCode.USAGE_ERROR,
                message="Plugin version must be strict semantic versioning",
                exit_code=ExitCode.USAGE_ERROR,
                details={"version": version},
            )
        description = "Frowang paper library and Zotero research workflows for coding agents."
        author = {"name": "Frowang"}
        codex: dict[str, object] = {
            "name": "paper-agent",
            "version": version,
            "description": description,
            "author": author,
            "license": "MIT",
            "keywords": ["papers", "research", "zotero", "frowang"],
            "skills": "./skills/",
            "interface": {
                "displayName": "Paper Agent",
                "shortDescription": "Manage and import research papers",
                "longDescription": (
                    "Search and manage a Frowang paper library, import Zotero collections, "
                    "and prepare papers for agentic research workflows."
                ),
                "developerName": "Frowang",
                "category": "Productivity",
                "capabilities": ["Interactive", "Write"],
                "defaultPrompt": [
                    "Search my paper library for relevant research.",
                    "Preview a Zotero collection before importing it.",
                ],
                "brandColor": "#176B55",
            },
        }
        claude: dict[str, object] = {
            "name": "paper-agent",
            "version": version,
            "description": description,
            "author": author,
            "license": "MIT",
            "keywords": ["papers", "research", "zotero", "frowang"],
        }
        return codex, claude

    def build(
        self,
        destination: Path,
        *,
        version: str,
        force: bool = False,
    ) -> dict[str, object]:
        target = destination.expanduser().resolve()
        if target.exists() and not force:
            raise CommandError(
                code=ErrorCode.CONFLICT,
                message="Plugin bundle destination already exists",
                exit_code=ExitCode.CONFLICT,
                details={"path": str(target)},
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".{target.name}.paper-agent-stage-{uuid4().hex}"
        backup = target.parent / f".{target.name}.paper-agent-backup-{uuid4().hex}"
        codex, claude = self._manifests(version)
        snapshots = [self.source.snapshot(name) for name in self.source.skill_names()]
        try:
            staging.mkdir(parents=True)
            for snapshot in snapshots:
                skill_target = staging / "skills" / snapshot.name
                for relative in snapshot.files:
                    source_file = snapshot.root / relative
                    target_file = skill_target / relative
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, target_file)
            _write_json(staging / ".codex-plugin" / "plugin.json", codex)
            _write_json(staging / ".claude-plugin" / "plugin.json", claude)
            _write_json(
                staging / "paper-agent-plugin-manifest.json",
                {
                    "schema_version": 1,
                    "name": "paper-agent",
                    "version": version,
                    "skills": {
                        snapshot.name: {
                            "source_hash": snapshot.source_hash,
                            "files": dict(snapshot.files),
                        }
                        for snapshot in snapshots
                    },
                },
            )
            if target.exists():
                os.replace(target, backup)
            os.replace(staging, target)
            _remove(backup)
        except CommandError:
            raise
        except OSError as exc:
            if not target.exists() and backup.exists():
                try:
                    os.replace(backup, target)
                except OSError:
                    pass
            raise CommandError(
                code=ErrorCode.LOCAL_IO_ERROR,
                message="Could not build the Paper Agent Plugin bundle",
                exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
                details={"path": str(target), "error_type": type(exc).__name__},
            ) from exc
        finally:
            _remove(staging)
        return {
            "path": str(target),
            "name": "paper-agent",
            "version": version,
            "skills": [snapshot.name for snapshot in snapshots],
            "skill_hashes": {
                snapshot.name: snapshot.source_hash for snapshot in snapshots
            },
            "manifests": {
                "codex": str(target / ".codex-plugin" / "plugin.json"),
                "claude": str(target / ".claude-plugin" / "plugin.json"),
            },
        }
