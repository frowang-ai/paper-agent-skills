from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SRC_ROOT),
            "PAPER_AGENT_CONFIG_DIR": str(tmp_path / "config"),
            "PAPER_AGENT_DATA_DIR": str(tmp_path / "data"),
            "PAPER_AGENT_CACHE_DIR": str(tmp_path / "cache"),
            "PAPER_AGENT_LOG_DIR": str(tmp_path / "log"),
            "PAPER_AGENT_SKILLS_SOURCE": str(REPO_ROOT / "skills"),
            "PAPER_AGENT_CODEX_SKILLS_DIR": str(tmp_path / "codex-skills"),
            "PAPER_AGENT_CLAUDE_SKILLS_DIR": str(tmp_path / "claude-skills"),
        }
    )
    return env


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "paper_agent", *args],
        cwd=REPO_ROOT,
        env=_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )


def test_skills_cli_install_status_diff_and_uninstall(tmp_path: Path) -> None:
    _run(tmp_path, "config", "init")

    install = _run(
        tmp_path,
        "skills",
        "install",
        "--platform",
        "codex",
        "paper-library",
    )
    assert install.returncode == 0, install.stderr
    assert json.loads(install.stdout)["data"]["installed"] == ["paper-library"]

    status = _run(tmp_path, "skills", "status", "--platform", "codex")
    assert json.loads(status.stdout)["data"]["skills"]["paper-library"]["status"] == "current"

    diff = _run(tmp_path, "skills", "diff", "--platform", "codex", "paper-library")
    assert json.loads(diff.stdout)["data"]["skills"]["paper-library"]["target_modified"] == []

    uninstall = _run(
        tmp_path,
        "skills",
        "uninstall",
        "--platform",
        "codex",
        "paper-library",
    )
    assert json.loads(uninstall.stdout)["data"]["uninstalled"] == ["paper-library"]


def test_skills_cli_platform_all_installs_both_user_targets(tmp_path: Path) -> None:
    _run(tmp_path, "config", "init")

    install = _run(tmp_path, "skills", "install", "--platform", "all")

    assert install.returncode == 0, install.stderr
    targets = json.loads(install.stdout)["data"]["targets"]
    assert [item["target"]["platform"] for item in targets] == ["codex", "claude"]
    for platform in ("codex", "claude"):
        root = tmp_path / f"{platform}-skills"
        assert (root / "paper-library" / "SKILL.md").is_file()
        assert (root / "zotero-upload" / "SKILL.md").is_file()
