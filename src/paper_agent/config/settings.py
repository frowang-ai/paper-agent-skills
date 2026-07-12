from __future__ import annotations

import os
import tomllib
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from uuid import uuid4

import tomli_w

from paper_agent.protocol import CommandError, ErrorCode, ExitCode

from .paths import AppPaths


CURRENT_CONFIG_SCHEMA = 1
DEFAULT_BASE_URL = "https://frowang.com/paper-api/api/v1"


@dataclass(frozen=True)
class FrowangSettings:
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class ZoteroSettings:
    mode: str = "local"
    library_type: str = "user"
    library_id: str = "0"
    storage_dir: Optional[str] = None


@dataclass(frozen=True)
class ProfileSettings:
    frowang: FrowangSettings
    zotero: ZoteroSettings


@dataclass(frozen=True)
class WorkspaceSettings:
    papers_dir: str = "papers"
    materialization: str = "copy"


@dataclass(frozen=True)
class AppSettings:
    schema_version: int
    active_profile: str
    profiles: Mapping[str, ProfileSettings]
    workspace: WorkspaceSettings

    @property
    def active(self) -> ProfileSettings:
        return self.profiles[self.active_profile]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConfigInitResult:
    created_config: bool
    created_credentials: bool
    migrated: bool

    def as_dict(self, paths: AppPaths) -> dict[str, Any]:
        return {
            "created_config": self.created_config,
            "created_credentials": self.created_credentials,
            "migrated": self.migrated,
            "paths": paths.as_dict(),
        }


@dataclass(frozen=True)
class ConfigMigrationResult:
    changed: bool
    schema_version: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "schema_version": self.schema_version,
        }


def _default_config() -> dict[str, Any]:
    return {
        "schema_version": CURRENT_CONFIG_SCHEMA,
        "active_profile": "default",
        "profiles": {
            "default": {
                "frowang": {
                    "base_url": DEFAULT_BASE_URL,
                    "timeout_seconds": 120,
                },
                "zotero": {
                    "mode": "local",
                    "library_type": "user",
                    "library_id": "0",
                    "storage_dir": "",
                },
            }
        },
        "workspace": {
            "papers_dir": "papers",
            "materialization": "copy",
        },
    }


def _atomic_write_text(
    path: Path, content: str, *, mode: Optional[int] = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _config_error(message: str, **details: Any) -> CommandError:
    return CommandError(
        code=ErrorCode.CONFIG_INVALID,
        message=message,
        exit_code=ExitCode.CONFIG_OR_AUTH,
        details=details,
    )


def _local_io_error(operation: str, path: Path, exc: OSError) -> CommandError:
    return CommandError(
        code=ErrorCode.LOCAL_IO_ERROR,
        message="Paper Agent could not access a local configuration path",
        exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        details={
            "operation": operation,
            "path": str(path),
            "error_type": type(exc).__name__,
        },
    )


def _merge_config_defaults(raw: Mapping[str, Any]) -> dict[str, Any]:
    defaults = _default_config()
    normalized = deepcopy(defaults)

    for key, value in raw.items():
        if key not in {"profiles", "workspace"}:
            normalized[key] = deepcopy(value)

    raw_profiles = raw.get("profiles")
    if isinstance(raw_profiles, dict) and raw_profiles:
        profile_defaults = defaults["profiles"]["default"]
        merged_profiles: dict[str, Any] = {}
        for profile_name, profile_value in raw_profiles.items():
            if not isinstance(profile_value, dict):
                merged_profiles[profile_name] = deepcopy(profile_value)
                continue

            merged_profile = deepcopy(profile_defaults)
            for key, value in profile_value.items():
                if key in {"frowang", "zotero"} and isinstance(value, dict):
                    section = dict(merged_profile[key])
                    section.update(deepcopy(value))
                    merged_profile[key] = section
                else:
                    merged_profile[key] = deepcopy(value)
            merged_profiles[profile_name] = merged_profile
        normalized["profiles"] = merged_profiles
    elif raw_profiles is not None:
        normalized["profiles"] = deepcopy(raw_profiles)

    raw_workspace = raw.get("workspace")
    if isinstance(raw_workspace, dict):
        workspace = dict(defaults["workspace"])
        workspace.update(deepcopy(raw_workspace))
        normalized["workspace"] = workspace
    elif raw_workspace is not None:
        normalized["workspace"] = deepcopy(raw_workspace)

    return normalized


class ConfigManager:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def initialize(self) -> ConfigInitResult:
        try:
            for directory in (
                self.paths.config_dir,
                self.paths.data_dir,
                self.paths.cache_dir,
                self.paths.log_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)

            created_config = not self.paths.config_file.exists()
            if created_config:
                _atomic_write_text(
                    self.paths.config_file,
                    tomli_w.dumps(_default_config()),
                )

            migration = self.migrate()

            created_credentials = not self.paths.credentials_file.exists()
            if created_credentials:
                _atomic_write_text(
                    self.paths.credentials_file,
                    "# Paper Agent credentials. Never commit this file.\n"
                    "FROWANG_API_KEY=\n"
                    "ZOTERO_API_KEY=\n",
                    mode=0o600,
                )
        except OSError as exc:
            raise _local_io_error(
                "initialize_config", self.paths.config_dir, exc
            ) from exc

        return ConfigInitResult(
            created_config=created_config,
            created_credentials=created_credentials,
            migrated=migration.changed,
        )

    def _read_raw(self) -> dict[str, Any]:
        if not self.paths.config_file.is_file():
            raise _config_error(
                "Paper Agent config is not initialized",
                config_file=str(self.paths.config_file),
            )
        try:
            with self.paths.config_file.open("rb") as handle:
                raw = tomllib.load(handle)
        except OSError as exc:
            raise _local_io_error(
                "read_config", self.paths.config_file, exc
            ) from exc
        except tomllib.TOMLDecodeError as exc:
            raise _config_error(
                "Paper Agent config cannot be read",
                config_file=str(self.paths.config_file),
                error_type=type(exc).__name__,
            ) from exc
        if not isinstance(raw, dict):
            raise _config_error("Paper Agent config root must be a table")
        return raw

    def migrate(self) -> ConfigMigrationResult:
        raw = self._read_raw()
        schema_version = raw.get("schema_version")
        if schema_version != CURRENT_CONFIG_SCHEMA:
            raise _config_error(
                "Unsupported Paper Agent config schema",
                schema_version=schema_version,
                supported_schema=CURRENT_CONFIG_SCHEMA,
            )

        normalized = _merge_config_defaults(raw)

        changed = normalized != raw
        if changed:
            try:
                _atomic_write_text(self.paths.config_file, tomli_w.dumps(normalized))
            except OSError as exc:
                raise _local_io_error(
                    "migrate_config", self.paths.config_file, exc
                ) from exc
        return ConfigMigrationResult(
            changed=changed,
            schema_version=CURRENT_CONFIG_SCHEMA,
        )

    def load(self) -> AppSettings:
        raw = self._read_raw()
        schema_version = raw.get("schema_version")
        if schema_version != CURRENT_CONFIG_SCHEMA:
            raise _config_error(
                "Unsupported Paper Agent config schema",
                schema_version=schema_version,
                supported_schema=CURRENT_CONFIG_SCHEMA,
            )

        active_profile = raw.get("active_profile")
        profiles = raw.get("profiles")
        if not isinstance(active_profile, str) or not active_profile.strip():
            raise _config_error("active_profile must be a non-empty string")
        if not isinstance(profiles, dict) or active_profile not in profiles:
            raise _config_error(
                "active_profile does not exist in profiles",
                active_profile=active_profile,
            )

        parsed_profiles: dict[str, ProfileSettings] = {}
        for name, value in profiles.items():
            if not isinstance(name, str) or not isinstance(value, dict):
                raise _config_error("Each profile must be a TOML table")
            frowang_raw = value.get("frowang", {})
            zotero_raw = value.get("zotero", {})
            if not isinstance(frowang_raw, dict) or not isinstance(zotero_raw, dict):
                raise _config_error("Profile provider sections must be TOML tables", profile=name)

            base_url = frowang_raw.get("base_url", DEFAULT_BASE_URL)
            timeout = frowang_raw.get("timeout_seconds", 120)
            if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
                raise _config_error("frowang.base_url must be an HTTP(S) URL", profile=name)
            if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
                raise _config_error("frowang.timeout_seconds must be positive", profile=name)

            mode = zotero_raw.get("mode", "local")
            library_type = zotero_raw.get("library_type", "user")
            library_id = zotero_raw.get("library_id", "0")
            storage_dir = zotero_raw.get("storage_dir", "")
            if mode not in {"local", "remote"}:
                raise _config_error("zotero.mode must be local or remote", profile=name)
            if library_type not in {"user", "group"}:
                raise _config_error("zotero.library_type must be user or group", profile=name)
            if not isinstance(library_id, str) or not library_id.strip():
                raise _config_error("zotero.library_id must be a non-empty string", profile=name)
            if not isinstance(storage_dir, str):
                raise _config_error("zotero.storage_dir must be a string", profile=name)

            parsed_profiles[name] = ProfileSettings(
                frowang=FrowangSettings(
                    base_url=base_url.rstrip("/"),
                    timeout_seconds=float(timeout),
                ),
                zotero=ZoteroSettings(
                    mode=mode,
                    library_type=library_type,
                    library_id=library_id.strip(),
                    storage_dir=storage_dir.strip() or None,
                ),
            )

        workspace_raw = raw.get("workspace", {})
        if not isinstance(workspace_raw, dict):
            raise _config_error("workspace must be a TOML table")
        papers_dir = workspace_raw.get("papers_dir", "papers")
        materialization = workspace_raw.get("materialization", "copy")
        if not isinstance(papers_dir, str) or not papers_dir.strip():
            raise _config_error("workspace.papers_dir must be a non-empty string")
        if materialization != "copy":
            raise _config_error("workspace.materialization currently only supports copy")

        return AppSettings(
            schema_version=schema_version,
            active_profile=active_profile,
            profiles=parsed_profiles,
            workspace=WorkspaceSettings(
                papers_dir=papers_dir,
                materialization=materialization,
            ),
        )
