from __future__ import annotations

import hashlib
import json
import os
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from paper_agent.protocol import CommandError, ErrorCode, ExitCode


@dataclass(frozen=True)
class SkillSnapshot:
    name: str
    root: Path
    source_hash: str
    files: Mapping[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source_hash": self.source_hash,
            "files": dict(self.files),
        }


def _config_error(message: str, **details: object) -> CommandError:
    return CommandError(
        code=ErrorCode.CONFIG_INVALID,
        message=message,
        exit_code=ExitCode.CONFIG_OR_AUTH,
        details=details,
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CommandError(
            code=ErrorCode.LOCAL_IO_ERROR,
            message="Could not read a canonical Skill file",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
            details={"path": str(path), "error_type": type(exc).__name__},
        ) from exc
    return digest.hexdigest()


def _validate_skill_md(path: Path, expected_name: str) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _config_error(
            "Skill metadata cannot be read",
            skill=expected_name,
            error_type=type(exc).__name__,
        ) from exc
    if not lines or lines[0].strip() != "---":
        raise _config_error("SKILL.md must start with frontmatter", skill=expected_name)
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise _config_error("SKILL.md frontmatter is not closed", skill=expected_name) from exc
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    if fields.get("name") != expected_name or not fields.get("description"):
        raise _config_error(
            "SKILL.md frontmatter must contain matching name and description",
            skill=expected_name,
        )


class SkillSource:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self._manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, object]:
        path = self.root / "manifest.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _config_error(
                "Skill source manifest cannot be read",
                path=str(path),
                error_type=type(exc).__name__,
            ) from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise _config_error("Unsupported Skill source manifest", path=str(path))
        skills = raw.get("skills")
        if not isinstance(skills, dict) or not skills:
            raise _config_error("Skill source manifest has no skills", path=str(path))
        return raw

    def skill_names(self) -> list[str]:
        skills = self._manifest["skills"]
        assert isinstance(skills, dict)
        return sorted(str(name) for name in skills)

    def _included_files(self, name: str) -> list[Path]:
        skills = self._manifest["skills"]
        assert isinstance(skills, dict)
        entry = skills.get(name)
        if not isinstance(entry, dict):
            raise CommandError(
                code=ErrorCode.NOT_FOUND,
                message="Canonical Skill was not found",
                exit_code=ExitCode.RESOURCE_STATE,
                details={"skill": name, "available": self.skill_names()},
            )
        include = entry.get("include")
        if not isinstance(include, list) or not include:
            raise _config_error("Skill include list is missing", skill=name)
        skill_root = (self.root / name).resolve()
        if not skill_root.is_dir():
            raise _config_error("Canonical Skill directory is missing", skill=name)
        files: set[Path] = set()
        for raw_pattern in include:
            if not isinstance(raw_pattern, str):
                raise _config_error("Skill include pattern must be a string", skill=name)
            pattern_path = Path(raw_pattern)
            if pattern_path.is_absolute() or ".." in pattern_path.parts:
                raise _config_error("Skill include pattern escapes its root", skill=name)
            if raw_pattern.endswith("/**"):
                base = skill_root / raw_pattern[:-3]
                candidates = base.rglob("*") if base.is_dir() else []
            else:
                candidates = skill_root.glob(raw_pattern)
            for candidate in candidates:
                if candidate.is_symlink():
                    raise _config_error(
                        "Canonical Skill files cannot be symlinks",
                        skill=name,
                        path=str(candidate),
                    )
                if candidate.is_file():
                    resolved = candidate.resolve()
                    if not resolved.is_relative_to(skill_root):
                        raise _config_error("Skill file escapes its root", skill=name)
                    files.add(resolved)
        skill_md = skill_root / "SKILL.md"
        if skill_md.resolve() not in files:
            raise _config_error("Skill include list must contain SKILL.md", skill=name)
        _validate_skill_md(skill_md, name)
        return sorted(files, key=lambda path: path.relative_to(skill_root).as_posix())

    def snapshot(self, name: str) -> SkillSnapshot:
        skill_root = (self.root / name).resolve()
        hashes = {
            path.relative_to(skill_root).as_posix(): _file_hash(path)
            for path in self._included_files(name)
        }
        digest = hashlib.sha256()
        for relative, file_hash in hashes.items():
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_hash.encode("ascii"))
            digest.update(b"\n")
        return SkillSnapshot(name, skill_root, digest.hexdigest(), hashes)


def resolve_skills_source(
    env: Optional[Mapping[str, str]] = None,
) -> SkillSource:
    environment = env if env is not None else os.environ
    override = environment.get("PAPER_AGENT_SKILLS_SOURCE")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    candidates.extend(
        [
            Path(__file__).resolve().parents[3] / "skills",
            Path(sysconfig.get_path("data")) / "share" / "paper-agent" / "skills",
            Path(sys.prefix) / "share" / "paper-agent" / "skills",
        ]
    )
    for candidate in candidates:
        if (candidate / "manifest.json").is_file():
            return SkillSource(candidate)
    raise _config_error(
        "Canonical Paper Agent Skills could not be located",
        searched=[str(path.expanduser().resolve()) for path in candidates],
    )
