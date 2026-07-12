from __future__ import annotations

import sys
from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "paper-library" / "scripts"))

import paper_cli  # noqa: E402
from paper_api_client import load_api_key  # noqa: E402


def test_legacy_wrapper_translates_all_command_groups() -> None:
    assert paper_cli._translate_argv(["paper", "list"]) == ["library", "list"]
    assert paper_cli._translate_argv(["tag", "add", "P-1", "NLP"]) == [
        "library", "tag", "add", "P-1", "NLP"
    ]
    assert paper_cli._translate_argv(["note", "list", "P-1"]) == [
        "library", "note", "list", "P-1"
    ]
    assert paper_cli._translate_argv(["collection", "list"]) == [
        "library", "collection", "list"
    ]
    assert paper_cli._translate_argv(["key", "list", "--jwt-token", "jwt"]) == [
        "library", "key", "list", "--jwt-token", "jwt"
    ]


def test_legacy_wrapper_moves_global_options_to_new_positions() -> None:
    translated = paper_cli._translate_argv(
        ["--human", "--api-key", "pk_explicit", "paper", "list"]
    )
    assert translated == [
        "library", "--api-key", "pk_explicit", "list", "--human"
    ]


def test_compat_key_loader_prefers_explicit_then_environment(monkeypatch) -> None:
    monkeypatch.setenv("FROWANG_API_KEY", "pk_environment")
    assert load_api_key("pk_explicit") == "pk_explicit"
    assert load_api_key(None) == "pk_environment"


def test_compat_key_loader_reads_legacy_skill_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FROWANG_API_KEY", raising=False)
    monkeypatch.delenv("PAPER_API_KEY", raising=False)
    skill_env = tmp_path / ".env"
    skill_env.write_text("PAPER_API_KEY=pk_skill_local\n", encoding="utf-8")

    assert load_api_key(None, skill_env_path=skill_env) == "pk_skill_local"


def test_compat_key_loader_raises_public_error_instead_of_system_exit(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FROWANG_API_KEY", raising=False)
    monkeypatch.delenv("PAPER_API_KEY", raising=False)

    with pytest.raises(CommandError) as caught:
        load_api_key(None, skill_env_path=tmp_path / "missing.env")

    assert caught.value.code == ErrorCode.AUTH_MISSING
