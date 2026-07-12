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
        }
    )
    env.pop("FROWANG_API_KEY", None)
    env.pop("PAPER_API_KEY", None)
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


def test_zotero_status_uses_global_state_without_credentials(tmp_path: Path) -> None:
    _run(tmp_path, "config", "init")
    result = _run(tmp_path, "zotero", "status")
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["meta"]["command"] == "zotero.status"
    assert payload["data"]["state_db"] == str((tmp_path / "data" / "state.sqlite3").resolve())
    assert payload["data"]["item_count"] == 0


def test_zotero_migrate_state_is_idempotent(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps({"ITEM1": {"frowang_id": "P-1", "task_id": "task-1"}}),
        encoding="utf-8",
    )
    _run(tmp_path, "config", "init")

    first = _run(tmp_path, "zotero", "migrate-state", str(legacy))
    second = _run(tmp_path, "zotero", "migrate-state", str(legacy))

    assert first.returncode == 0
    assert json.loads(first.stdout)["data"]["imported"] == 1
    assert second.returncode == 0
    assert json.loads(second.stdout)["data"]["skipped"] == 1


def test_legacy_zotero_wrapper_translates_sync_status() -> None:
    scripts = REPO_ROOT / "skills" / "zotero-upload" / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import zotero_upload_cli

        assert zotero_upload_cli._translate_argv(["collections"]) == [
            "zotero",
            "collections",
        ]
        assert zotero_upload_cli._translate_argv(["sync-status"]) == [
            "zotero",
            "status",
        ]
    finally:
        sys.path.remove(str(scripts))
