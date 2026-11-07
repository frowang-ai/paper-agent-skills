from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from paper_agent.services import LibraryService


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def request_json(self, method: str, path: str, **kwargs):
        self.calls.append({"method": method, "path": path, **kwargs})
        return {"success": True, "data": {"is_new": True}}


def _run(tmp_path: Path, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
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
    env.update(extra)
    return subprocess.run(
        [sys.executable, "-m", "paper_agent", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_preview_many_classifies_files_without_network(tmp_path: Path) -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    text = tmp_path / "notes.txt"
    text.write_text("notes", encoding="utf-8")

    result = service.preview_many([pdf, text, tmp_path / "missing.pdf"])

    assert result["dry_run"] is True
    assert result["confirmation_required"] is True
    assert result["total"] == 3
    assert result["would_upload"] == 1
    assert result["uploaded"] == 0
    assert [item["status"] for item in result["results"]] == [
        "pending",
        "skipped",
        "skipped",
    ]
    assert client.calls == []


def test_upload_dir_defaults_to_preview_without_credentials(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    for name in ("main.pdf", "fig1_policy.pdf"):
        (documents / name).write_bytes(b"%PDF-1.4\n")
    (documents / "notes.txt").write_text("notes", encoding="utf-8")
    nested = documents / "nested"
    nested.mkdir()
    (nested / "nested.pdf").write_bytes(b"%PDF-1.4\n")

    result = _run(tmp_path, "library", "upload-dir", str(documents))
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["confirmation_required"] is True
    assert payload["data"]["would_upload"] == 2
    assert [item["file"] for item in payload["data"]["results"]] == [
        "fig1_policy.pdf",
        "main.pdf",
    ]
    assert all(item["status"] == "pending" for item in payload["data"]["results"])
    assert payload["meta"]["command"] == "library.upload-dir"


def test_upload_many_defaults_to_preview_without_credentials(tmp_path: Path) -> None:
    files = [tmp_path / name for name in ("main.pdf", "figure.pdf")]
    for file in files:
        file.write_bytes(b"%PDF-1.4\n")

    result = _run(tmp_path, "library", "upload-many", *(str(file) for file in files))
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload["data"]["would_upload"] == 2
    assert [item["file"] for item in payload["data"]["results"]] == [
        "main.pdf",
        "figure.pdf",
    ]
    assert payload["meta"]["command"] == "library.upload-many"


def test_upload_dir_yes_uploads_previewed_files(tmp_path: Path) -> None:
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            paths.append(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = json.dumps(
                {
                    "success": True,
                    "data": {
                        "paper_id": "paper-1",
                        "short_id": "P-1",
                        "task_id": "task-1",
                        "is_new": True,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    documents = tmp_path / "documents"
    documents.mkdir()
    for name in ("main.pdf", "figure.pdf"):
        (documents / name).write_bytes(b"%PDF-1.4\n")
    try:
        _run(tmp_path, "config", "init")
        base_url = f"http://127.0.0.1:{server.server_port}/api/v1"
        result = _run(
            tmp_path,
            "library",
            "--base-url",
            base_url,
            "upload-dir",
            str(documents),
            "--yes",
            FROWANG_API_KEY="pk_upload_preview_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["data"]["uploaded"] == 2
    assert payload["data"]["would_upload"] == 2
    assert payload["data"]["dry_run"] is False
    assert paths == ["/api/v1/papers", "/api/v1/papers"]


def test_upload_dir_rejects_dry_run_with_yes(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "main.pdf").write_bytes(b"%PDF-1.4\n")

    result = _run(
        tmp_path,
        "library",
        "upload-dir",
        str(documents),
        "--dry-run",
        "--yes",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["error"]["code"] == "USAGE_ERROR"
