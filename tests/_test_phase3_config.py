from __future__ import annotations

from paper_agent.config import ConfigManager, ZoteroCredentialResolver
from paper_agent.config.paths import AppPaths


def _paths(tmp_path):
    return AppPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "log",
    )


def test_config_migration_adds_zotero_runtime_fields(tmp_path) -> None:
    paths = _paths(tmp_path)
    manager = ConfigManager(paths)
    manager.initialize()

    settings = manager.load()

    assert settings.active.zotero.mode == "local"
    assert settings.active.zotero.library_id == "0"
    assert settings.active.zotero.storage_dir is None


def test_zotero_credentials_use_environment_then_user_file(tmp_path) -> None:
    paths = _paths(tmp_path)
    manager = ConfigManager(paths)
    manager.initialize()
    resolver = ZoteroCredentialResolver(paths)

    environment = resolver.resolve({"ZOTERO_API_KEY": "zot_env"})
    assert environment.value == "zot_env"
    assert environment.source == "environment:ZOTERO_API_KEY"

    paths.credentials_file.write_text(
        "FROWANG_API_KEY=\nZOTERO_API_KEY=zot_file\n",
        encoding="utf-8",
    )
    from_file = resolver.resolve({})
    assert from_file.value == "zot_file"
    assert from_file.source == "credentials.env:ZOTERO_API_KEY"
