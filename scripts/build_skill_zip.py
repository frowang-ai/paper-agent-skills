#!/usr/bin/env python3
"""Build a thin Skill zip from the canonical Skill source manifest."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from paper_agent.skills import SkillSource  # noqa: E402


def build(skill_name: str) -> Path:
    source = SkillSource(REPO_ROOT / "skills")
    snapshot = source.snapshot(skill_name)
    dist = REPO_ROOT / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    destination = dist / f"{skill_name}-skill.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in snapshot.files:
            archive.write(
                snapshot.root / relative,
                arcname=(Path(skill_name) / relative).as_posix(),
            )
    print(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a thin Paper Agent Skill zip")
    parser.add_argument(
        "--skill",
        default="paper-library",
        help="Skill name from the skills/ source directory (default: paper-library).",
    )
    args = parser.parse_args()
    build(args.skill)


if __name__ == "__main__":
    main()
