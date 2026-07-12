from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from platformdirs import user_cache_dir, user_config_dir, user_data_dir, user_log_dir


_APP_NAME = "paper-agent"
_APP_AUTHOR = "Frowang"


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    log_dir: Path

    def __post_init__(self) -> None:
        for field_name in ("config_dir", "data_dir", "cache_dir", "log_dir"):
            value = getattr(self, field_name).expanduser().resolve()
            object.__setattr__(self, field_name, value)

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def credentials_file(self) -> Path:
        return self.config_dir / "credentials.env"

    @property
    def state_db(self) -> Path:
        return self.data_dir / "state.sqlite3"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def locks_dir(self) -> Path:
        return self.data_dir / "locks"

    def as_dict(self) -> dict[str, str]:
        return {
            "config_dir": str(self.config_dir),
            "config_file": str(self.config_file),
            "credentials_file": str(self.credentials_file),
            "data_dir": str(self.data_dir),
            "state_db": str(self.state_db),
            "artifacts_dir": str(self.artifacts_dir),
            "locks_dir": str(self.locks_dir),
            "cache_dir": str(self.cache_dir),
            "log_dir": str(self.log_dir),
        }


def _path_from_env(
    env: Mapping[str, str], name: str, default: str
) -> Path:
    raw = env.get(name)
    return Path(raw if raw else default).expanduser().resolve()


def resolve_app_paths(env: Optional[Mapping[str, str]] = None) -> AppPaths:
    values = env if env is not None else __import__("os").environ
    return AppPaths(
        config_dir=_path_from_env(
            values,
            "PAPER_AGENT_CONFIG_DIR",
            user_config_dir(_APP_NAME, _APP_AUTHOR, roaming=True),
        ),
        data_dir=_path_from_env(
            values,
            "PAPER_AGENT_DATA_DIR",
            user_data_dir(_APP_NAME, _APP_AUTHOR, roaming=False),
        ),
        cache_dir=_path_from_env(
            values,
            "PAPER_AGENT_CACHE_DIR",
            user_cache_dir(_APP_NAME, _APP_AUTHOR),
        ),
        log_dir=_path_from_env(
            values,
            "PAPER_AGENT_LOG_DIR",
            user_log_dir(_APP_NAME, _APP_AUTHOR),
        ),
    )
