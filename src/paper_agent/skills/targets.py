from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional

from paper_agent.protocol import CommandError, ErrorCode, ExitCode


@dataclass(frozen=True)
class SkillTarget:
    platform: str
    scope: str
    mode: str
    root: Path

    def __post_init__(self) -> None:
        if self.platform not in {"codex", "claude"}:
            raise ValueError("Unsupported skill platform")
        if self.scope not in {"user", "project"}:
            raise ValueError("Unsupported skill scope")
        if self.mode not in {"standalone", "plugin"}:
            raise ValueError("Unsupported skill mode")
        object.__setattr__(self, "root", self.root.expanduser().resolve())

    def as_dict(self) -> dict[str, str]:
        result = asdict(self)
        result["root"] = str(self.root)
        return result


def _usage(message: str, **details: object) -> CommandError:
    return CommandError(
        code=ErrorCode.USAGE_ERROR,
        message=message,
        exit_code=ExitCode.USAGE_ERROR,
        details=details,
    )


def resolve_skill_target(
    platform: str,
    scope: str,
    *,
    mode: str = "standalone",
    project_root: Optional[Path] = None,
    home: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> SkillTarget:
    normalized_platform = platform.strip().lower()
    normalized_scope = scope.strip().lower()
    if normalized_platform not in {"codex", "claude"}:
        raise _usage("platform must be codex or claude", platform=platform)
    if normalized_scope not in {"user", "project"}:
        raise _usage("scope must be user or project", scope=scope)
    if mode != "standalone":
        raise _usage("Direct skill targets currently support standalone mode only", mode=mode)

    environment = env if env is not None else os.environ
    user_home = (home or Path.home()).expanduser().resolve()
    if normalized_scope == "project":
        if project_root is None:
            raise _usage("project scope requires --project-root")
        project = project_root.expanduser().resolve()
        relative = (
            Path(".agents") / "skills"
            if normalized_platform == "codex"
            else Path(".claude") / "skills"
        )
        root = project / relative
    elif normalized_platform == "codex":
        override = environment.get("PAPER_AGENT_CODEX_SKILLS_DIR")
        if override:
            root = Path(override)
        else:
            codex_home = Path(environment.get("CODEX_HOME", user_home / ".codex"))
            root = codex_home / "skills"
    else:
        override = environment.get("PAPER_AGENT_CLAUDE_SKILLS_DIR")
        root = Path(override) if override else user_home / ".claude" / "skills"

    return SkillTarget(
        platform=normalized_platform,
        scope=normalized_scope,
        mode=mode,
        root=root,
    )

