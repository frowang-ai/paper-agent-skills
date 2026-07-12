#!/usr/bin/env python3
"""Build the dual-platform Paper Agent Plugin bundle."""
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from paper_agent import __version__  # noqa: E402
from paper_agent.plugins import PluginBundleBuilder  # noqa: E402
from paper_agent.skills import SkillSource  # noqa: E402


def main() -> None:
    destination = REPO_ROOT / "dist" / "paper-agent-plugin"
    result = PluginBundleBuilder(SkillSource(REPO_ROOT / "skills")).build(
        destination,
        version=__version__,
        force=True,
    )
    print(result["path"])


if __name__ == "__main__":
    main()
