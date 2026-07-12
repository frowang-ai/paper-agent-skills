from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_baseline_is_python_313_without_backports() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["requires-python"] == ">=3.13"
    dependency_names = {
        dependency.split(";", 1)[0].split("[", 1)[0].split(">", 1)[0].strip()
        for dependency in project["dependencies"]
    }
    assert "tomli" not in dependency_names
    assert "typing_extensions" not in dependency_names
