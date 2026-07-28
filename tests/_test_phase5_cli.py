from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from contextlib import contextmanager


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _run(
    tmp_path: Path, *args: str, **environment: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SRC_ROOT),
            "PAPER_AGENT_CONFIG_DIR": str(tmp_path / "config"),
            "PAPER_AGENT_DATA_DIR": str(tmp_path / "data"),
            "PAPER_AGENT_CACHE_DIR": str(tmp_path / "cache"),
            "PAPER_AGENT_LOG_DIR": str(tmp_path / "log"),
        }
    )
    env.update(environment)
    return subprocess.run(
        [sys.executable, "-m", "paper_agent", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@contextmanager
def _server() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/paper-api/api/v1/papers/P-1":
                payload = {
                    "success": True,
                    "data": {
                        "paper_id": "11111111-1111-1111-1111-111111111111",
                        "title": "CLI Paper",
                        "publication_year": 2024,
                        "authors": [{"family": "Smith", "given": "Alice"}],
                        "latest_task_id": "task-cli",
                    },
                }
                content = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            elif self.path == "/paper-api/api/v1/papers/P-1/assets":
                payload = {
                    "success": True,
                    "data": {
                        "paper_id": "11111111-1111-1111-1111-111111111111",
                        "assets": {
                            "ocr_markdown_url": "/outputs/task-cli/complete.md",
                            "layout_url": "/outputs/task-cli/layout.json",
                            "metadata_url": None,
                            "attribute_tree_url": None,
                        },
                    },
                }
                content = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            elif self.path == "/paper-api/api/v1/papers/P-1/metadata":
                payload = {
                    "success": True,
                    "data": {
                        "title": "CLI Paper",
                        "publication_year": 2024,
                        "authors": [{"family": "Smith", "given": "Alice"}],
                        "doi": "10.0000/cli",
                        "task_id": "task-cli",
                    },
                }
                content = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            elif self.path.endswith("/complete.md"):
                content = b"# CLI Paper\n\nLocal evidence.\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown")
            elif self.path.endswith("/layout.json"):
                content = b'{"pages": []}\n'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            else:
                self.send_response(404)
                content = b"not found"
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/paper-api/api/v1"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_workspace_cli_init_and_local_status_do_not_require_auth(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    assert _run(tmp_path, "config", "init").returncode == 0

    initialized = _run(tmp_path, "workspace", "init", str(project))
    assert initialized.returncode == 0, initialized.stderr
    assert Path(json.loads(initialized.stdout)["data"]["manifest"]).is_file()

    status = _run(tmp_path, "workspace", "status", str(project))
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["data"]["papers"] == {}


def test_workspace_cli_add_runs_remote_to_global_to_project_flow(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    assert _run(tmp_path, "config", "init").returncode == 0
    assert _run(tmp_path, "workspace", "init", str(project)).returncode == 0

    with _server() as base_url:
        added = _run(
            tmp_path,
            "workspace",
            "--base-url",
            base_url,
            "add",
            str(project),
            "P-1",
            FROWANG_API_KEY="pk_phase5_test",
        )

    assert added.returncode == 0, added.stderr
    data = json.loads(added.stdout)["data"]["added"][0]
    assert data["revision"] == "task-cli"
    assert (
        project / "papers" / "2024-Smith-CLI-Paper--P-1" / "full.md"
    ).is_file()
    assert list((tmp_path / "data" / "artifacts" / "papers").rglob("full.md"))

    plan = _run(tmp_path, "workspace", "names", "plan", str(project))
    assert plan.returncode == 0, plan.stderr
    assert json.loads(plan.stdout)["data"]["items"][0]["status"] == "current"

    apply = _run(tmp_path, "workspace", "names", "apply", str(project))
    assert apply.returncode == 0, apply.stderr
    assert json.loads(apply.stdout)["data"]["unchanged"] == ["P-1"]
