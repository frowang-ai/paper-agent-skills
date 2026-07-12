from __future__ import annotations

from pathlib import Path

import pytest

from paper_agent.config import (
    AppPaths,
    ConfigManager,
    CredentialResolver,
    CredentialStore,
    resolve_app_paths,
)
from paper_agent.protocol import CommandError, ErrorCode, ExitCode


def _isolated_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "log",
    )


def test_resolve_app_paths_honors_explicit_environment_roots(tmp_path: Path) -> None:
    env = {
        "PAPER_AGENT_CONFIG_DIR": str(tmp_path / "config-root"),
        "PAPER_AGENT_DATA_DIR": str(tmp_path / "data-root"),
        "PAPER_AGENT_CACHE_DIR": str(tmp_path / "cache-root"),
        "PAPER_AGENT_LOG_DIR": str(tmp_path / "log-root"),
    }

    paths = resolve_app_paths(env)

    assert paths.config_dir == (tmp_path / "config-root").resolve()
    assert paths.data_dir == (tmp_path / "data-root").resolve()
    assert paths.cache_dir == (tmp_path / "cache-root").resolve()
    assert paths.log_dir == (tmp_path / "log-root").resolve()
    assert paths.config_file == paths.config_dir / "config.toml"
    assert paths.credentials_file == paths.config_dir / "credentials.env"
    assert paths.state_db == paths.data_dir / "state.sqlite3"
    assert paths.artifacts_dir == paths.data_dir / "artifacts"
    assert paths.locks_dir == paths.data_dir / "locks"


def test_default_app_paths_do_not_depend_on_cwd(monkeypatch, tmp_path: Path) -> None:
    first = resolve_app_paths({})
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    second = resolve_app_paths({})

    assert first == second
    assert first.config_dir.is_absolute()
    assert first.data_dir.is_absolute()


def test_config_init_is_idempotent_and_preserves_user_values(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    manager = ConfigManager(paths)

    first = manager.initialize()
    assert first.created_config is True
    assert first.created_credentials is True
    assert paths.config_file.exists()
    assert paths.credentials_file.exists()
    assert paths.data_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.log_dir.is_dir()

    original = paths.config_file.read_text(encoding="utf-8")
    customized = original.replace("timeout_seconds = 120", "timeout_seconds = 45")
    paths.config_file.write_text(customized, encoding="utf-8")

    second = manager.initialize()
    settings = manager.load()

    assert second.created_config is False
    assert second.created_credentials is False
    assert settings.active.frowang.timeout_seconds == 45
    assert "timeout_seconds = 45" in paths.config_file.read_text(encoding="utf-8")


def test_config_init_preserves_existing_credentials_file(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    paths.config_dir.mkdir(parents=True)
    paths.credentials_file.write_text("FROWANG_API_KEY=pk_existing\n", encoding="utf-8")

    result = ConfigManager(paths).initialize()

    assert result.created_credentials is False
    assert paths.credentials_file.read_text(encoding="utf-8") == "FROWANG_API_KEY=pk_existing\n"


def test_config_migrate_materializes_defaults_for_custom_profile(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    paths.config_dir.mkdir(parents=True)
    paths.config_file.write_text(
        "schema_version = 1\nactive_profile = \"research\"\n\n"
        "[profiles.research.frowang]\n"
        "base_url = \"https://paper.example.test/api\"\n",
        encoding="utf-8",
    )

    result = ConfigManager(paths).migrate()
    settings = ConfigManager(paths).load()
    persisted = paths.config_file.read_text(encoding="utf-8")

    assert result.changed is True
    assert settings.active_profile == "research"
    assert settings.active.frowang.base_url == "https://paper.example.test/api"
    assert settings.active.frowang.timeout_seconds == 120
    assert settings.active.zotero.mode == "local"
    assert "timeout_seconds = 120" in persisted
    assert "[profiles.research.zotero]" in persisted
    assert "[workspace]" in persisted


def test_config_load_rejects_unknown_schema(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    paths.config_dir.mkdir(parents=True)
    paths.config_file.write_text(
        "schema_version = 99\nactive_profile = \"default\"\n",
        encoding="utf-8",
    )

    with pytest.raises(CommandError) as exc_info:
        ConfigManager(paths).load()

    assert exc_info.value.code == ErrorCode.CONFIG_INVALID
    assert exc_info.value.details["schema_version"] == 99


def test_config_init_maps_filesystem_failures_to_public_error(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    paths.config_dir.parent.mkdir(parents=True, exist_ok=True)
    paths.config_dir.write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(CommandError) as exc_info:
        ConfigManager(paths).initialize()

    assert exc_info.value.code == ErrorCode.LOCAL_IO_ERROR
    assert exc_info.value.exit_code == ExitCode.LOCAL_IO_OR_INTEGRITY
    assert exc_info.value.details["operation"] == "initialize_config"


def test_config_load_rejects_missing_active_profile(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    paths.config_dir.mkdir(parents=True)
    paths.config_file.write_text(
        "schema_version = 1\nactive_profile = \"missing\"\n\n"
        "[profiles.default.frowang]\n"
        "base_url = \"https://example.test/api\"\n"
        "timeout_seconds = 120\n",
        encoding="utf-8",
    )

    with pytest.raises(CommandError) as exc_info:
        ConfigManager(paths).load()

    assert exc_info.value.code == ErrorCode.CONFIG_INVALID
    assert exc_info.value.details["active_profile"] == "missing"


def test_credentials_prefer_new_env_name_and_never_return_secret_in_status(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    ConfigManager(paths).initialize()
    resolver = CredentialResolver(paths)

    status = resolver.status({"FROWANG_API_KEY": "pk_super_secret"})

    assert status.configured is True
    assert status.source == "environment:FROWANG_API_KEY"
    assert "pk_super_secret" not in repr(status)
    assert "pk_super_secret" not in str(status.as_dict())


def test_credentials_support_legacy_env_and_file_without_leaking_value(tmp_path: Path) -> None:
    paths = _isolated_paths(tmp_path)
    ConfigManager(paths).initialize()
    resolver = CredentialResolver(paths)

    legacy = resolver.resolve({"PAPER_API_KEY": "pk_legacy"})
    assert legacy.value == "pk_legacy"
    assert legacy.source == "environment:PAPER_API_KEY"

    paths.credentials_file.write_text("FROWANG_API_KEY=pk_from_file\n", encoding="utf-8")
    from_file = resolver.resolve({})
    assert from_file.value == "pk_from_file"
    assert from_file.source == "credentials.env:FROWANG_API_KEY"


def test_credentials_reject_conflicting_new_and_legacy_env_names(tmp_path: Path) -> None:
    resolver = CredentialResolver(_isolated_paths(tmp_path))

    with pytest.raises(CommandError) as exc_info:
        resolver.resolve(
            {
                "FROWANG_API_KEY": "pk_new",
                "PAPER_API_KEY": "pk_old",
            }
        )

    assert exc_info.value.code == ErrorCode.CONFIG_INVALID
    assert "pk_new" not in str(exc_info.value.details)
    assert "pk_old" not in str(exc_info.value.details)


def test_credential_store_sets_canonical_key_and_preserves_other_content(
    tmp_path: Path,
) -> None:
    paths = _isolated_paths(tmp_path)
    ConfigManager(paths).initialize()
    paths.credentials_file.write_text(
        "# Keep this comment.\n"
        "PAPER_API_KEY=pk_legacy\n"
        "ZOTERO_API_KEY=zotero_secret\n"
        "CUSTOM_SETTING=keep-me\n",
        encoding="utf-8",
    )
    secret = "pk_'quoted\\value"

    result = CredentialStore(paths).set_frowang(secret)
    persisted = paths.credentials_file.read_text(encoding="utf-8")

    assert result.changed is True
    assert result.stored is True
    assert result.source == "credentials.env:FROWANG_API_KEY"
    assert "# Keep this comment." in persisted
    assert "PAPER_API_KEY" not in persisted
    assert "ZOTERO_API_KEY=zotero_secret" in persisted
    assert "CUSTOM_SETTING=keep-me" in persisted
    assert CredentialResolver(paths).resolve({}).value == secret
    assert secret not in repr(result)
    assert secret not in str(result.as_dict())


def test_credential_store_delete_removes_both_frowang_aliases_only(
    tmp_path: Path,
) -> None:
    paths = _isolated_paths(tmp_path)
    ConfigManager(paths).initialize()
    paths.credentials_file.write_text(
        "FROWANG_API_KEY=pk_current\n"
        "PAPER_API_KEY=pk_legacy\n"
        "ZOTERO_API_KEY=zotero_secret\n",
        encoding="utf-8",
    )

    result = CredentialStore(paths).delete_frowang()
    persisted = paths.credentials_file.read_text(encoding="utf-8")

    assert result.changed is True
    assert result.stored is False
    assert result.source is None
    assert "FROWANG_API_KEY" not in persisted
    assert "PAPER_API_KEY" not in persisted
    assert "ZOTERO_API_KEY=zotero_secret" in persisted


def test_credential_store_delete_is_noop_when_file_does_not_exist(
    tmp_path: Path,
) -> None:
    paths = _isolated_paths(tmp_path)

    result = CredentialStore(paths).delete_frowang()

    assert result.changed is False
    assert result.stored is False
    assert not paths.credentials_file.exists()


def test_credential_store_rejects_empty_or_multiline_secret(tmp_path: Path) -> None:
    store = CredentialStore(_isolated_paths(tmp_path))

    for value in ("", "   ", "pk_one\npk_two"):
        with pytest.raises(CommandError) as exc_info:
            store.set_frowang(value)
        assert exc_info.value.code == ErrorCode.AUTH_INVALID
