#!/usr/bin/env python3
"""Deprecated compatibility wrapper for the unified ``paper-agent`` CLI."""
from __future__ import annotations

import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve()
_REPO_SRC = _SCRIPT.parents[3] / "src"
if _REPO_SRC.is_dir() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))


_GROUPS = {
    "paper": (),
    "tag": ("tag",),
    "note": ("note",),
    "collection": ("collection",),
    "key": ("key",),
}
_VALUE_OPTIONS = {"--api-key", "--base-url"}


def _translate_argv(arguments: list[str]) -> list[str]:
    """Translate the legacy command tree to ``paper-agent library``."""
    library_options: list[str] = []
    output_options: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in _VALUE_OPTIONS:
            library_options.append(argument)
            if index + 1 < len(arguments):
                library_options.append(arguments[index + 1])
                index += 2
                continue
        elif any(argument.startswith(f"{option}=") for option in _VALUE_OPTIONS):
            library_options.append(argument)
            index += 1
            continue
        elif argument == "--human":
            output_options.append(argument)
            index += 1
            continue
        remaining.append(argument)
        index += 1

    if not remaining:
        return ["library", *library_options]
    group = remaining[0]
    if group not in _GROUPS:
        return ["library", *library_options, *remaining, *output_options]
    return [
        "library",
        *library_options,
        *_GROUPS[group],
        *remaining[1:],
        *output_options,
    ]


def main() -> None:
    try:
        from paper_agent.cli import main as paper_agent_main
    except ImportError:
        sys.stderr.write(
            "paper-cli is deprecated and now requires the paper-agent runtime. "
            "Install it with: uv tool install paper-agent-skills\n"
        )
        raise SystemExit(1) from None

    sys.stderr.write(
        "DEPRECATION: paper_cli.py is deprecated; use `paper-agent library ...`.\n"
    )
    sys.argv = [sys.argv[0], *_translate_argv(sys.argv[1:])]
    paper_agent_main()


if __name__ == "__main__":
    main()

