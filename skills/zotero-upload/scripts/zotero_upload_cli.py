#!/usr/bin/env python3
"""Deprecated compatibility wrapper for ``paper-agent zotero``."""
from __future__ import annotations

import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve()
_REPO_SRC = _SCRIPT.parents[3] / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))


def _translate_argv(arguments: list[str]) -> list[str]:
    translated = list(arguments)
    if translated and translated[0] == "sync-status":
        translated[0] = "status"
    return ["zotero", *translated]


def main() -> None:
    try:
        from paper_agent.cli import main as paper_agent_main
    except ImportError:
        sys.stderr.write(
            "zotero_upload_cli.py is deprecated and requires the paper-agent runtime.\n"
        )
        raise SystemExit(1) from None
    sys.stderr.write(
        "DEPRECATION: zotero_upload_cli.py is deprecated; "
        "use `paper-agent zotero ...`.\n"
    )
    sys.argv = [sys.argv[0], *_translate_argv(sys.argv[1:])]
    paper_agent_main()


if __name__ == "__main__":
    main()
