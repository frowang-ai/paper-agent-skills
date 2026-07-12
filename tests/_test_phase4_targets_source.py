from __future__ import annotations

import json
from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode
from paper_agent.skills import SkillSource, resolve_skill_target


def test_resolves_user_and_project_targets(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"

    assert resolve_skill_target("codex", "user", home=home).root == (
        home / ".codex" / "skills"
    ).resolve()
    assert resolve_skill_target("claude", "user", home=home).root == (
        home / ".claude" / "skills"
    ).resolve()
    assert resolve_skill_target(
        "codex", "project", project_root=project, home=home
    ).root == (project / ".agents" / "skills").resolve()
    assert resolve_skill_target(
        "claude", "project", project_root=project, home=home
    ).root == (project / ".claude" / "skills").resolve()


def test_project_target_requires_explicit_project_root(tmp_path: Path) -> None:
    with pytest.raises(CommandError) as caught:
        resolve_skill_target("codex", "project", home=tmp_path)
    assert caught.value.code == ErrorCode.USAGE_ERROR


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    skill = root / "paper-library"
    (skill / "references").mkdir(parents=True)
    (skill / "downloads").mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: paper-library\ndescription: Test skill.\n---\n\n# Test\n",
        encoding="utf-8",
    )
    (skill / "references" / "usage.md").write_text("usage\n", encoding="utf-8")
    (skill / ".env").write_text("SECRET=do-not-copy\n", encoding="utf-8")
    (skill / "downloads" / "paper.pdf").write_bytes(b"pdf")
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


def test_skill_source_uses_manifest_allowlist_and_stable_hash(tmp_path: Path) -> None:
    source = SkillSource(_source(tmp_path))

    snapshot = source.snapshot("paper-library")

    assert source.skill_names() == ["paper-library"]
    assert set(snapshot.files) == {"SKILL.md", "references/usage.md"}
    assert len(snapshot.source_hash) == 64
    assert ".env" not in snapshot.files
    assert "downloads/paper.pdf" not in snapshot.files


def test_production_skills_include_codex_interface_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = SkillSource(repo_root / "skills")

    for skill_name in source.skill_names():
        snapshot = source.snapshot(skill_name)
        metadata_path = "agents/openai.yaml"

        assert metadata_path in snapshot.files
        metadata = (snapshot.root / metadata_path).read_text(encoding="utf-8")
        assert "display_name:" in metadata
        assert "short_description:" in metadata
        assert f"${skill_name}" in metadata
