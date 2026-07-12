from __future__ import annotations

from pathlib import Path

import pytest

from paper_agent.protocol import CommandError, ErrorCode


from paper_api_client import load_api_key


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
