from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
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
    return env


def _run(tmp_path: Path, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "paper_agent", *args],
        cwd=REPO_ROOT,
        env=_env(tmp_path, **extra),
        text=True,
        capture_output=True,
        check=False,
    )


def test_library_without_credentials_returns_public_auth_error(tmp_path: Path) -> None:
    _run(tmp_path, "config", "init")
    result = _run(tmp_path, "library", "list")
    payload = json.loads(result.stdout)

    assert result.returncode == 3
    assert payload["error"]["code"] == "AUTH_MISSING"
    assert payload["meta"]["command"] == "library.list"


def test_library_list_returns_one_cli_envelope(tmp_path: Path) -> None:
    received_api_key = ""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            nonlocal received_api_key
            received_api_key = self.headers.get("X-API-Key", "")
            body = json.dumps({"success": True, "data": {"papers": [], "total": 0}}).encode()
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
    try:
        _run(tmp_path, "config", "init")
        base_url = f"http://127.0.0.1:{server.server_port}/api/v1"
        result = _run(
            tmp_path,
            "library",
            "--base-url",
            base_url,
            "list",
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["success"] is True
    assert payload["data"] == {"papers": [], "total": 0}
    assert payload["meta"]["command"] == "library.list"
    assert received_api_key == "pk_cli_test"


def test_doctor_checks_remote_connection_without_exposing_secret(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps({"success": True, "data": {"papers": [], "total": 0}}).encode()
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
    secret = "pk_doctor_secret"
    try:
        _run(tmp_path, "config", "init")
        config_file = tmp_path / "config" / "config.toml"
        original = config_file.read_text(encoding="utf-8")
        config_file.write_text(
            original.replace(
                "https://frowang.com/paper-api/api/v1",
                f"http://127.0.0.1:{server.server_port}/api/v1",
            ),
            encoding="utf-8",
        )
        result = _run(tmp_path, "doctor", "--no-zotero", FROWANG_API_KEY=secret)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["data"]["checks"]["remote"]["status"] == "ok"
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_fulltext_is_saved_atomically_and_not_emitted_to_stdout(tmp_path: Path) -> None:
    content = "# Paper\n\nA long result that belongs in a file."

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps({"success": True, "data": {"content": content}}).encode()
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
    destination = tmp_path / "papers" / "P-1" / "full.md"
    try:
        _run(tmp_path, "config", "init")
        base_url = f"http://127.0.0.1:{server.server_port}/api/v1"
        result = _run(
            tmp_path,
            "library",
            "--base-url",
            base_url,
            "fulltext",
            "P-1",
            "--save",
            str(destination),
            FROWANG_API_KEY="pk_content_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert destination.read_text(encoding="utf-8") == content
    assert payload["data"]["path"] == str(destination.resolve())
    assert content not in result.stdout
