#!/usr/bin/env python3
"""Deprecated wrapper for ``paper-agent skills``.

The historical script only targeted Claude user Skills and deleted existing directories.
This wrapper preserves the common command shape while delegating to the conflict-safe installer.
"""
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _translate(arguments: list[str]) -> list[str]:
    if "--list" in arguments:
        return ["skills", "list"]
    dry_run = "--dry-run" in arguments
    names = [argument for argument in arguments if argument not in {"--dry-run"}]
    action = "diff" if dry_run else "install"
    return ["skills", action, "--platform", "claude", *names]


def main() -> None:
    from paper_agent.cli import main as paper_agent_main

    sys.stderr.write(
        "DEPRECATION: scripts/sync_skills.py is deprecated; "
        "use `paper-agent skills ...`.\n"
    )
    sys.argv = [sys.argv[0], *_translate(sys.argv[1:])]
    paper_agent_main()


if __name__ == "__main__":
    main()
