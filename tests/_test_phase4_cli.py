from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from paper_agent import cli


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


def test_skills_cli_human_install_and_status_are_readable(tmp_path: Path) -> None:
    _run(tmp_path, "config", "init")

    install = _run(
        tmp_path,
        "skills",
        "install",
        "--platform",
        "all",
        "--human",
    )
    status = _run(
        tmp_path,
        "skills",
        "status",
        "--platform",
        "all",
        "--human",
    )

    assert install.returncode == 0, install.stderr
    assert f"Paper Agent Skills {cli.__version__}" in install.stdout
    assert "Codex" in install.stdout and "user" in install.stdout
    assert "Installed: paper-library, paper-workspace, zotero-upload" in install.stdout
    assert not install.stdout.lstrip().startswith("{")

    assert status.returncode == 0, status.stderr
    assert "Claude" in status.stdout and "user" in status.stdout
    assert f"paper-library: current (v{cli.__version__})" in status.stdout
    assert not status.stdout.lstrip().startswith("{")


@pytest.mark.parametrize(
    ("json_output", "human", "is_tty", "expected"),
    [
        (False, False, True, True),
        (False, False, False, False),
        (True, False, True, False),
        (False, True, False, True),
    ],
)
def test_output_mode_uses_human_format_for_interactive_terminal(
    monkeypatch: pytest.MonkeyPatch,
    json_output: bool,
    human: bool,
    is_tty: bool,
    expected: bool,
) -> None:
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: is_tty)

    assert cli._use_human_output(json_output=json_output, human=human) is expected


def test_skill_human_renderers_summarize_actions_and_status() -> None:
    target = {
        "platform": "codex",
        "scope": "user",
        "mode": "standalone",
        "root": r"C:\Users\test\.codex\skills",
    }
    action = cli._render_human(
        "skills.install",
        {
            "target": target,
            "installed": ["paper-library"],
            "updated": [],
            "skipped": ["paper-workspace"],
            "not_installed": [],
        },
    )
    status = cli._render_human(
        "skills.status",
        {
            "target": target,
            "skills": {
                "paper-library": {
                    "status": "current",
                    "installed_version": cli.__version__,
                    "target_modified": [],
                    "unmanaged_files": [],
                }
            },
        },
    )

    assert "Installed: paper-library" in action
    assert "Already current: paper-workspace" in action
    assert f"paper-library: current (v{cli.__version__})" in status
    assert not action.lstrip().startswith("{")
