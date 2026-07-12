from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from paper_agent import cli


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


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
    tmp_path: Path,
    *args: str,
    stdin_text: str | None = None,
    **extra_env: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "paper_agent", *args],
        cwd=REPO_ROOT,
        env=_cli_env(tmp_path, **extra_env),
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _json_stdout(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def test_capabilities_returns_one_json_document(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "capabilities")
    payload = _json_stdout(result)

    assert result.returncode == 0
    assert payload["success"] is True
    assert payload["meta"]["command"] == "capabilities"
    assert "config" in payload["data"]["capabilities"]
    assert result.stderr == ""


def test_config_init_show_and_auth_status(tmp_path: Path) -> None:
    init_result = _run_cli(tmp_path, "config", "init")
    init_payload = _json_stdout(init_result)
    assert init_result.returncode == 0
    assert init_payload["data"]["created_config"] is True

    show_result = _run_cli(tmp_path, "config", "show")
    show_payload = _json_stdout(show_result)
    assert show_result.returncode == 0
    assert show_payload["data"]["settings"]["active_profile"] == "default"
    assert show_payload["data"]["paths"]["config_file"].endswith("config.toml")

    auth_result = _run_cli(tmp_path, "auth", "status", FROWANG_API_KEY="pk_do_not_print")
    auth_payload = _json_stdout(auth_result)
    assert auth_result.returncode == 0
    assert auth_payload["data"] == {
        "provider": "frowang",
        "configured": True,
        "source": "environment:FROWANG_API_KEY",
    }
    assert "pk_do_not_print" not in auth_result.stdout
    assert "pk_do_not_print" not in auth_result.stderr


def test_auth_set_from_stdin_status_and_delete_never_echo_secret(
    tmp_path: Path,
) -> None:
    secret = "pk_agent_supplied_secret"
    set_result = _run_cli(
        tmp_path,
        "auth",
        "set",
        "--stdin",
        stdin_text=secret + "\n",
    )
    set_payload = _json_stdout(set_result)

    assert set_result.returncode == 0
    assert set_payload["meta"]["command"] == "auth.set"
    assert set_payload["data"]["stored"] is True
    assert set_payload["data"]["source"] == "credentials.env:FROWANG_API_KEY"
    assert set_payload["data"]["external_sources_unchanged"] is True
    assert secret not in set_result.stdout
    assert secret not in set_result.stderr

    status_result = _run_cli(tmp_path, "auth", "status")
    status_payload = _json_stdout(status_result)
    assert status_payload["data"]["configured"] is True
    assert status_payload["data"]["source"] == "credentials.env:FROWANG_API_KEY"
    assert secret not in status_result.stdout
    assert secret not in status_result.stderr

    delete_result = _run_cli(tmp_path, "auth", "delete")
    delete_payload = _json_stdout(delete_result)
    assert delete_result.returncode == 0
    assert delete_payload["meta"]["command"] == "auth.delete"
    assert delete_payload["data"]["stored"] is False
    assert delete_payload["data"]["external_sources_unchanged"] is True
    assert secret not in delete_result.stdout
    assert secret not in delete_result.stderr


def test_auth_set_from_stdin_rejects_empty_input(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "auth", "set", "--stdin", stdin_text="\n")
    payload = _json_stdout(result)

    assert result.returncode == 3
    assert payload["error"]["code"] == "AUTH_INVALID"


def test_auth_set_default_input_uses_hidden_terminal_prompt(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_getpass(prompt: str, *, stream) -> str:
        observed.update(prompt=prompt, stream=stream)
        return "pk_hidden"

    monkeypatch.setattr(cli, "getpass", fake_getpass)

    assert cli._read_frowang_secret(from_stdin=False) == "pk_hidden"
    assert observed == {"prompt": "Frowang API key: ", "stream": sys.stderr}


def test_auth_delete_does_not_claim_to_remove_environment_credentials(
    tmp_path: Path,
) -> None:
    secret = "pk_environment_only"

    delete_result = _run_cli(
        tmp_path,
        "auth",
        "delete",
        FROWANG_API_KEY=secret,
    )
    delete_payload = _json_stdout(delete_result)
    status_result = _run_cli(
        tmp_path,
        "auth",
        "status",
        FROWANG_API_KEY=secret,
    )
    status_payload = _json_stdout(status_result)

    assert delete_payload["data"]["stored"] is False
    assert delete_payload["data"]["external_sources_unchanged"] is True
    assert status_payload["data"]["configured"] is True
    assert status_payload["data"]["source"] == "environment:FROWANG_API_KEY"
    assert secret not in delete_result.stdout + delete_result.stderr
    assert secret not in status_result.stdout + status_result.stderr


def test_doctor_reports_warning_without_auth_and_ok_with_auth(tmp_path: Path) -> None:
    _run_cli(tmp_path, "config", "init")

    warning_result = _run_cli(tmp_path, "doctor")
    warning_payload = _json_stdout(warning_result)
    assert warning_result.returncode == 0
    assert warning_payload["data"]["status"] == "warning"
    assert warning_payload["data"]["checks"]["credentials"]["status"] == "warning"

    ok_result = _run_cli(
        tmp_path,
        "doctor",
        "--no-remote",
        "--no-zotero",
        FROWANG_API_KEY="pk_configured",
    )
    ok_payload = _json_stdout(ok_result)
    assert ok_result.returncode == 0
    assert ok_payload["data"]["status"] == "ok"


def test_unknown_command_returns_json_usage_error(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "does-not-exist")
    payload = _json_stdout(result)

    assert result.returncode == 2
    assert payload["success"] is False
    assert payload["error"]["code"] == "USAGE_ERROR"
    assert payload["meta"]["command"] == "cli"


def test_no_command_and_conflicting_output_flags_are_usage_errors(tmp_path: Path) -> None:
    no_command = _run_cli(tmp_path)
    no_command_payload = _json_stdout(no_command)
    assert no_command.returncode == 2
    assert no_command_payload["error"]["code"] == "USAGE_ERROR"

    conflicting = _run_cli(tmp_path, "capabilities", "--json", "--human")
    conflicting_payload = _json_stdout(conflicting)
    assert conflicting.returncode == 2
    assert conflicting_payload["error"]["code"] == "USAGE_ERROR"


def test_installed_console_script_uses_the_same_contract(tmp_path: Path) -> None:
    executable_name = "paper-agent.exe" if os.name == "nt" else "paper-agent"
    executable = Path(sys.executable).with_name(executable_name)
    assert executable.is_file()

    result = subprocess.run(
        [str(executable), "capabilities"],
        cwd=REPO_ROOT,
        env=_cli_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )
    payload = _json_stdout(result)

    assert result.returncode == 0
    assert payload["success"] is True
    assert payload["meta"]["command"] == "capabilities"
