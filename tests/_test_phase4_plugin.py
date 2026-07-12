from __future__ import annotations

import json
from pathlib import Path

from paper_agent.plugins import PluginBundleBuilder
from paper_agent.skills import SkillSource


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_plugin_bundle_has_dual_manifests_and_only_production_skills(
    tmp_path: Path,
) -> None:
    source = SkillSource(REPO_ROOT / "skills")
    destination = tmp_path / "paper-agent"
    result = PluginBundleBuilder(source).build(
        destination,
        version="0.5.0",
    )

    codex = json.loads(
        (destination / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    claude = json.loads(
        (destination / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert codex["name"] == claude["name"] == "paper-agent"
    assert codex["skills"] == "./skills/"
    assert result["skills"] == ["paper-library", "paper-workspace", "zotero-upload"]
    for skill_name in result["skills"]:
        assert (
            destination / "skills" / skill_name / "agents" / "openai.yaml"
        ).is_file()
    assert not (destination / "skills" / "demo-zotero-connection").exists()
    assert not list(destination.rglob(".env"))
    assert not list(destination.rglob("*.pdf"))
