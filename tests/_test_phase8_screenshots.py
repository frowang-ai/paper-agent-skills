from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from paper_agent.clients import FrowangClient
from paper_agent.protocol import CommandError, ErrorCode, ExitCode


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

SCREENSHOTS = {
    "base_url": "https://frowang.com/paper-api/outputs/task-1/screenshots",
    "html_images": ["https://frowang.com/paper-api/outputs/task-1/screenshots/deep-1.png"],
    "pdf_images": ["https://frowang.com/paper-api/outputs/task-1/screenshots/pdf-1.png"],
}


def _client(handler) -> FrowangClient:
    return FrowangClient(
        api_key="pk_test_secret",
        base_url="https://example.test/paper-api/api/v1",
        transport=httpx.MockTransport(handler),
        max_get_retries=0,
    )


def test_client_create_screenshots_posts_query_params() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen.update({k: v for k, v in request.url.params.items()})
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {"paper_id": "uuid-1", "job_id": "job-1", "status": "queued"},
            },
        )

    with _client(handler) as client:
        payload = client.create_paper_screenshots(
            "P-3a", capture_pdf=False, capture_html=True, force_rescreenshot=True
        )

    assert seen["path"] == "/paper-api/api/v1/papers/P-3a/screenshots"
    assert seen["capture_pdf"] == "false"
    assert seen["capture_html"] == "true"
    assert seen["force_rescreenshot"] == "true"
    assert payload["data"]["job_id"] == "job-1"


def test_client_get_screenshots_with_and_without_job_id() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.query.decode())
        return httpx.Response(200, json={"success": True, "data": {"status": "completed"}})

    with _client(handler) as client:
        client.get_paper_screenshots("P-3a")
        client.get_paper_screenshots("P-3a", job_id="job-1")

    assert seen[0] == ""
    assert seen[1] == "job_id=job-1"


@pytest.mark.parametrize("remote_code", ["NOT_FOUND", "TASK_NOT_FOUND"])
def test_client_maps_screenshots_failures(remote_code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"detail": {"code": remote_code, "message": "missing"}}
        )

    with _client(handler) as client, pytest.raises(CommandError) as caught:
        client.get_paper_screenshots("P-3a")

    assert caught.value.code == ErrorCode.NOT_FOUND
    assert caught.value.exit_code == ExitCode.RESOURCE_STATE
    assert caught.value.details["remote_code"] == remote_code


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


class _State:
    def __init__(self) -> None:
        self.posts: list[dict[str, list[str]]] = []
        self.job_polls = 0
        self.plain_gets = 0


def _server(state: _State):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            split = urlsplit(self.path)
            if split.path.endswith("/papers/P-1/screenshots"):
                state.posts.append(parse_qs(split.query))
                self._send(
                    200,
                    {
                        "success": True,
                        "data": {
                            "paper_id": "uuid-1",
                            "job_id": "job-1",
                            "status": "queued",
                        },
                        "message": "queued",
                    },
                )
            else:
                self._send(404, {"detail": {"code": "NOT_FOUND", "message": "missing"}})

        def do_GET(self) -> None:  # noqa: N802
            split = urlsplit(self.path)
            if split.path.endswith("/papers/P-1/screenshots"):
                query = parse_qs(split.query)
                if query.get("job_id"):
                    state.job_polls += 1
                    if state.job_polls == 1:
                        data = {
                            "paper_id": "uuid-1",
                            "job_id": "job-1",
                            "status": "processing",
                            "progress": 50,
                            "message": "working",
                            "screenshots": None,
                        }
                    else:
                        data = {
                            "paper_id": "uuid-1",
                            "job_id": "job-1",
                            "status": "completed",
                            "progress": 100,
                            "message": "done",
                            "screenshots": SCREENSHOTS,
                        }
                    self._send(200, {"success": True, "data": data})
                else:
                    state.plain_gets += 1
                    self._send(
                        200,
                        {
                            "success": True,
                            "data": {
                                "paper_id": "uuid-1",
                                "status": "completed",
                                "message": "ready",
                                "screenshots": SCREENSHOTS,
                            },
                        },
                    )
            else:
                self._send(404, {"detail": {"code": "NOT_FOUND", "message": "missing"}})

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/api/v1"


def _library_args(base_url: str, *args: str) -> tuple[str, ...]:
    return ("library", "--base-url", base_url, *args, "--json")


def test_screenshots_cli_queries_current_and_job_progress(tmp_path: Path) -> None:
    state = _State()
    server, thread, base_url = _server(state)
    try:
        _run(tmp_path, "config", "init")
        current = _run(
            tmp_path, *_library_args(base_url, "screenshots", "P-1"),
            FROWANG_API_KEY="pk_cli_test",
        )
        progress = _run(
            tmp_path, *_library_args(base_url, "screenshots", "P-1", "--job-id", "job-1"),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(current.stdout)
    assert current.returncode == 0, current.stderr
    assert payload["meta"]["command"] == "library.screenshots"
    assert payload["data"]["status"] == "completed"
    assert payload["data"]["screenshots"]["pdf_images"][0].startswith("https://")

    payload = json.loads(progress.stdout)
    assert progress.returncode == 0, progress.stderr
    assert payload["data"]["job_id"] == "job-1"
    assert payload["data"]["status"] == "processing"
    assert state.job_polls == 1
    assert state.plain_gets == 1


def test_screenshots_cli_generate_returns_job_id_without_polling(tmp_path: Path) -> None:
    state = _State()
    server, thread, base_url = _server(state)
    try:
        _run(tmp_path, "config", "init")
        result = _run(
            tmp_path,
            *_library_args(base_url, "screenshots", "P-1", "--generate", "--no-html", "--force"),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["data"]["job_id"] == "job-1"
    assert payload["data"]["status"] == "queued"
    assert state.posts == [
        {"capture_pdf": ["true"], "capture_html": ["false"], "force_rescreenshot": ["true"]}
    ]
    assert state.job_polls == 0


def test_screenshots_cli_generate_wait_polls_until_completed(tmp_path: Path) -> None:
    state = _State()
    server, thread, base_url = _server(state)
    try:
        _run(tmp_path, "config", "init")
        result = _run(
            tmp_path,
            *_library_args(base_url, "screenshots", "P-1", "--generate", "--wait"),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert state.job_polls == 2
    assert payload["data"]["status"] == "completed"
    assert payload["data"]["screenshots"]["html_images"]


def test_screenshots_cli_wait_times_out(tmp_path: Path) -> None:
    state = _State()
    server, thread, base_url = _server(state)
    try:
        _run(tmp_path, "config", "init")
        result = _run(
            tmp_path,
            *_library_args(
                base_url, "screenshots", "P-1", "--generate", "--wait", "--timeout", "0"
            ),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == ExitCode.NETWORK_OR_REMOTE
    assert payload["error"]["code"] == "REMOTE_ERROR"
    assert payload["error"]["details"]["last_status"] == "processing"


def test_screenshots_cli_rejects_no_pdf_and_no_html(tmp_path: Path) -> None:
    state = _State()
    server, thread, base_url = _server(state)
    try:
        _run(tmp_path, "config", "init")
        result = _run(
            tmp_path,
            *_library_args(
                base_url, "screenshots", "P-1", "--generate", "--no-pdf", "--no-html"
            ),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == ExitCode.USAGE_ERROR
    assert payload["error"]["code"] == "USAGE_ERROR"
    assert state.posts == []


def test_screenshots_cli_maps_not_found(tmp_path: Path) -> None:
    state = _State()
    server, thread, base_url = _server(state)
    try:
        _run(tmp_path, "config", "init")
        result = _run(
            tmp_path, *_library_args(base_url, "screenshots", "P-missing"),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    assert result.returncode == ExitCode.RESOURCE_STATE
    assert payload["error"]["code"] == "NOT_FOUND"
