from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from paper_agent.config import resolve_app_paths
from paper_agent.services import UpdateCheckService


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _service(
    tmp_path: Path,
    *,
    current: str = "0.9.2",
    fetcher=lambda: "0.9.2",
    env: dict[str, str] | None = None,
    clock=lambda: NOW,
) -> UpdateCheckService:
    paths = resolve_app_paths(
        {
            "PAPER_AGENT_CONFIG_DIR": str(tmp_path / "config"),
            "PAPER_AGENT_DATA_DIR": str(tmp_path / "data"),
            "PAPER_AGENT_CACHE_DIR": str(tmp_path / "cache"),
            "PAPER_AGENT_LOG_DIR": str(tmp_path / "log"),
        }
    )
    return UpdateCheckService(
        paths,
        current_version=current,
        env=env if env is not None else {},
        clock=clock,
        fetcher=fetcher,
    )


def test_update_available_when_pypi_is_newer(tmp_path: Path) -> None:
    result = _service(tmp_path, fetcher=lambda: "1.0.0").check()

    assert result["status"] == "update_available"
    assert result["update_available"] is True
    assert result["latest_version"] == "1.0.0"
    assert result["current_version"] == "0.9.2"
    assert result["source"] == "network"


def test_ok_when_pypi_is_not_newer(tmp_path: Path) -> None:
    result = _service(tmp_path, fetcher=lambda: "0.9.2").check()

    assert result["status"] == "ok"
    assert result["update_available"] is False


def test_fresh_cache_avoids_network(tmp_path: Path) -> None:
    service = _service(tmp_path, fetcher=lambda: "1.0.0")
    service.check()

    def _boom() -> str:
        raise AssertionError("network must not be called")

    cached = _service(tmp_path, fetcher=_boom).check()

    assert cached["source"] == "cache"
    assert cached["update_available"] is True


def test_stale_cache_refreshes(tmp_path: Path) -> None:
    service = _service(tmp_path, fetcher=lambda: "1.0.0")
    service.check()
    later = NOW + timedelta(hours=25)
    refreshed = _service(tmp_path, fetcher=lambda: "1.1.0", clock=lambda: later).check()

    assert refreshed["source"] == "network"
    assert refreshed["latest_version"] == "1.1.0"


def test_refresh_bypasses_fresh_cache(tmp_path: Path) -> None:
    service = _service(tmp_path, fetcher=lambda: "1.0.0")
    service.check()
    refreshed = _service(tmp_path, fetcher=lambda: "1.1.0").check(refresh=True)

    assert refreshed["source"] == "network"
    assert refreshed["latest_version"] == "1.1.0"


def test_network_failure_without_cache_degrades_to_unknown(tmp_path: Path) -> None:
    def _boom() -> str:
        raise OSError("offline")

    result = _service(tmp_path, fetcher=_boom).check()

    assert result["status"] == "unknown"
    assert result["update_available"] is False
    assert result["reason"] == "network_error"


def test_network_failure_with_stale_cache_uses_cache(tmp_path: Path) -> None:
    _service(tmp_path, fetcher=lambda: "1.0.0").check()
    later = NOW + timedelta(hours=25)

    def _boom() -> str:
        raise OSError("offline")

    result = _service(tmp_path, fetcher=_boom, clock=lambda: later).check()

    assert result["source"] == "cache"
    assert result["stale"] is True
    assert result["update_available"] is True


def test_disable_env_short_circuits(tmp_path: Path) -> None:
    def _boom() -> str:
        raise AssertionError("network must not be called")

    result = _service(tmp_path, env={"PAPER_AGENT_DISABLE_UPDATE_CHECK": "1"}, fetcher=_boom).check()

    assert result["status"] == "disabled"
    assert result["source"] == "disabled"


def test_invalid_upstream_version_is_not_an_update(tmp_path: Path) -> None:
    result = _service(tmp_path, fetcher=lambda: "not-a-version").check()

    assert result["status"] == "ok"
    assert result["update_available"] is False


def _cli_env(tmp_path: Path, **extra: str) -> dict[str, str]:
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
    env.update(extra)
    return env


def _run_cli(
    tmp_path: Path, *args: str, **extra_env: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "paper_agent", *args],
        cwd=REPO_ROOT,
        env=_cli_env(tmp_path, **extra_env),
        text=True,
        capture_output=True,
        check=False,
    )


def test_update_check_cli_envelope_when_disabled(tmp_path: Path) -> None:
    result = _run_cli(
        tmp_path, "update", "check", PAPER_AGENT_DISABLE_UPDATE_CHECK="1"
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["meta"]["command"] == "update.check"
    assert payload["data"]["status"] == "disabled"
    assert payload["data"]["update_available"] is False


def test_update_check_cli_human_output(tmp_path: Path) -> None:
    result = _run_cli(
        tmp_path,
        "update",
        "check",
        "--human",
        PAPER_AGENT_DISABLE_UPDATE_CHECK="1",
    )

    assert result.returncode == 0, result.stderr
    assert "update check disabled" in result.stdout


def test_doctor_includes_update_check(tmp_path: Path) -> None:
    result = _run_cli(
        tmp_path, "doctor", "--no-zotero", PAPER_AGENT_DISABLE_UPDATE_CHECK="1"
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    update = payload["data"]["checks"]["update"]
    assert update["status"] == "disabled"


def test_doctor_no_remote_skips_update_check(tmp_path: Path) -> None:
    result = _run_cli(
        tmp_path, "doctor", "--no-remote", "--no-zotero"
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    update = payload["data"]["checks"]["update"]
    assert update == {"status": "not_run", "reason": "disabled_by_option"}


@pytest.mark.parametrize("arg", ["--json"])
def test_update_check_json_flag_keeps_envelope(tmp_path: Path, arg: str) -> None:
    result = _run_cli(
        tmp_path, "update", "check", arg, PAPER_AGENT_DISABLE_UPDATE_CHECK="1"
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["data"]["status"] == "disabled"
