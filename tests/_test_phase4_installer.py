from __future__ import annotations

import json
from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.services import SkillInstallService
from paper_agent.skills import SkillSource, SkillTarget
from paper_agent.storage import StateStore


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    skill = root / "paper-library"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: paper-library\ndescription: Install test.\n---\n",
        encoding="utf-8",
    )
    (skill / "references" / "commands.md").write_text("v1\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skills": {
                    "paper-library": {
                        "include": ["SKILL.md", "references/**"]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def _service(tmp_path: Path) -> tuple[SkillInstallService, SkillTarget, Path]:
    source_root = _source(tmp_path)
    target = SkillTarget(
        platform="codex",
        scope="user",
        mode="standalone",
        root=(tmp_path / "codex-skills").resolve(),
    )
    service = SkillInstallService(
        source=SkillSource(source_root),
        state_store=StateStore(tmp_path / "state.sqlite3"),
        package_version="0.5.0",
        clock=lambda: "2026-07-11T12:00:00Z",
    )
    return service, target, source_root


def test_install_update_and_uninstall_preserve_user_files(tmp_path: Path) -> None:
    service, target, source_root = _service(tmp_path)

    installed = service.install(target, ["paper-library"])
    destination = target.root / "paper-library"
    assert installed["installed"] == ["paper-library"]
    assert service.status(target)["skills"]["paper-library"]["status"] == "current"

    user_file = destination / "notes.md"
    user_file.write_text("keep me\n", encoding="utf-8")
    (source_root / "paper-library" / "references" / "commands.md").write_text(
        "v2\n", encoding="utf-8"
    )
    assert service.status(target)["skills"]["paper-library"]["status"] == "update_available"

    updated = service.update(target, ["paper-library"])
    assert updated["updated"] == ["paper-library"]
    assert user_file.read_text(encoding="utf-8") == "keep me\n"

    removed = service.uninstall(target, ["paper-library"])
    assert removed["uninstalled"] == ["paper-library"]
    assert user_file.read_text(encoding="utf-8") == "keep me\n"
    assert not (destination / "SKILL.md").exists()


def test_modified_managed_file_blocks_update_without_force(tmp_path: Path) -> None:
    service, target, source_root = _service(tmp_path)
    service.install(target, ["paper-library"])
    destination = target.root / "paper-library"
    (destination / "SKILL.md").write_text("user changed\n", encoding="utf-8")
    (source_root / "paper-library" / "references" / "commands.md").write_text(
        "v2\n", encoding="utf-8"
    )

    diff = service.diff(target, ["paper-library"])["skills"]["paper-library"]
    assert diff["target_modified"] == ["SKILL.md"]
    with pytest.raises(CommandError) as caught:
        service.update(target, ["paper-library"])
    assert caught.value.code == ErrorCode.CONFLICT

    forced = service.update(target, ["paper-library"], force=True)
    assert forced["updated"] == ["paper-library"]
    assert (destination / "SKILL.md").read_text(encoding="utf-8").startswith("---")


def test_modified_managed_file_blocks_uninstall_without_force(tmp_path: Path) -> None:
    service, target, _ = _service(tmp_path)
    service.install(target, ["paper-library"])
    destination = target.root / "paper-library"
    managed = destination / "SKILL.md"
    managed.write_text("user changed\n", encoding="utf-8")

    with pytest.raises(CommandError) as caught:
        service.uninstall(target, ["paper-library"])
    assert caught.value.code == ErrorCode.CONFLICT
    assert managed.read_text(encoding="utf-8") == "user changed\n"

    forced = service.uninstall(target, ["paper-library"], force=True)
    assert forced["uninstalled"] == ["paper-library"]
    assert not managed.exists()


def test_unknown_existing_directory_is_not_adopted_implicitly(tmp_path: Path) -> None:
    service, target, _ = _service(tmp_path)
    unknown = target.root / "paper-library"
    unknown.mkdir(parents=True)
    (unknown / "SKILL.md").write_text("unknown\n", encoding="utf-8")

    with pytest.raises(CommandError) as caught:
        service.install(target, ["paper-library"])

    assert caught.value.code == ErrorCode.CONFLICT
    assert (unknown / "SKILL.md").read_text(encoding="utf-8") == "unknown\n"
