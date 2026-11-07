from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paper_agent import cli
from paper_agent.protocol import CommandError, ErrorCode
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
    env.pop("FROWANG_API_KEY", None)
    env.pop("PAPER_API_KEY", None)
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


def test_preview_many_classifies_files_and_explains_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "notes.txt").write_text("notes", encoding="utf-8")

    result = service.preview_many(
        [Path("main.pdf"), Path("notes.txt"), Path("missing.pdf")]
    )

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
    assert result["results"][0]["path"] == str((tmp_path / "main.pdf").resolve())
    assert result["results"][1]["error_code"] == "NOT_A_PDF"
    missing = result["results"][2]
    assert missing["error_code"] == "FILE_NOT_FOUND"
    assert missing["input_path"] == "missing.pdf"
    assert missing["path"] == str((tmp_path / "missing.pdf").resolve())
    assert missing["cwd"] == str(tmp_path)
    assert "working directory" in missing["reason"]
    assert "absolute path" in missing["reason"]
    assert "same absolute paths" in result["next_action"]
    assert client.calls == []


def test_upload_many_defaults_to_preview_without_credentials(tmp_path: Path) -> None:
    files = [tmp_path / name for name in ("main.pdf", "figure.pdf")]
    for file in files:
        file.write_bytes(b"%PDF-1.4\n")

    result = _run(tmp_path, "library", "upload-many", *(str(file) for file in files))
    payload = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["confirmation_required"] is True
    assert payload["data"]["would_upload"] == 2
    assert [item["file"] for item in payload["data"]["results"]] == [
        "main.pdf",
        "figure.pdf",
    ]
    assert payload["meta"]["command"] == "library.upload-many"


@pytest.mark.parametrize("flags", [[], ["--dry-run"]])
def test_preview_never_loads_config_or_constructs_remote_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    flags: list[str],
) -> None:
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def fail(_=None):
        raise AssertionError("preview must not load config, credentials, or remote services")

    monkeypatch.setattr(cli, "_manager", fail)
    monkeypatch.setattr(cli, "_library_service", fail)
    monkeypatch.setattr(cli, "FrowangClient", fail)

    result = CliRunner().invoke(
        cli.app,
        ["library", "upload-many", str(pdf), *flags, "--json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0, result.output
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["would_upload"] == 1


def test_upload_many_yes_uploads_exact_preview_filenames(tmp_path: Path) -> None:
    uploads: list[tuple[str, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            uploads.append((self.path, self.rfile.read(length)))
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
    files = [tmp_path / name for name in ("main.pdf", "figure.pdf")]
    for file in files:
        file.write_bytes(b"%PDF-1.4\n")
    try:
        preview = _run(tmp_path, "library", "upload-many", *(str(file) for file in files))
        preview_payload = json.loads(preview.stdout)
        expected_names = [item["file"] for item in preview_payload["data"]["results"]]
        assert preview.returncode == 0, preview.stderr
        assert uploads == []

        _run(tmp_path, "config", "init")
        base_url = f"http://127.0.0.1:{server.server_port}/api/v1"
        result = _run(
            tmp_path,
            "library",
            "--base-url",
            base_url,
            "upload-many",
            *(str(file) for file in files),
            "--yes",
            FROWANG_API_KEY="pk_upload_preview_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(result.stdout)
    actual_names = [
        body.split(b'filename="', 1)[1].split(b'"', 1)[0].decode()
        for _, body in uploads
    ]
    assert result.returncode == 0, result.stderr
    assert payload["data"]["uploaded"] == 2
    assert payload["data"]["would_upload"] == 2
    assert payload["data"]["dry_run"] is False
    assert [path for path, _ in uploads] == ["/api/v1/papers", "/api/v1/papers"]
    assert actual_names == expected_names


def test_upload_many_rejects_dry_run_with_yes(tmp_path: Path) -> None:
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    result = _run(
        tmp_path,
        "library",
        "upload-many",
        str(pdf),
        "--dry-run",
        "--yes",
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["error"]["code"] == "USAGE_ERROR"
    assert "not both" in payload["error"]["message"]


def test_upload_many_rejects_all_invalid_before_remote(tmp_path: Path) -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]
    text = tmp_path / "notes.txt"
    text.write_text("notes", encoding="utf-8")

    with pytest.raises(CommandError) as caught:
        service.upload_many([text, tmp_path / "missing.pdf"])

    assert caught.value.code == ErrorCode.USAGE_ERROR
    assert "No valid PDF files to upload" in caught.value.message
    assert "No upload was performed" in caught.value.message
    assert [item["error_code"] for item in caught.value.details["results"]] == [
        "NOT_A_PDF",
        "FILE_NOT_FOUND",
    ]
    assert client.calls == []


def test_upload_many_partial_invalid_uploads_valid_and_reports_skipped(tmp_path: Path) -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    text = tmp_path / "notes.txt"
    text.write_text("notes", encoding="utf-8")

    result = service.upload_many([pdf, text])

    assert result["uploaded"] == 1
    assert result["skipped"] == 1
    assert result["results"][1]["error_code"] == "NOT_A_PDF"
    assert len(client.calls) == 1


def test_single_upload_missing_file_reports_cwd_and_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    service = LibraryService(client)  # type: ignore[arg-type]
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CommandError) as caught:
        service.upload(Path("missing.pdf"))

    assert caught.value.code == ErrorCode.USAGE_ERROR
    assert "working directory" in caught.value.message
    assert "absolute path" in caught.value.message
    assert caught.value.details["input_path"] == "missing.pdf"
    assert caught.value.details["path"] == str((tmp_path / "missing.pdf").resolve())
    assert caught.value.details["cwd"] == str(tmp_path)
    assert client.calls == []


def test_library_help_exposes_agent_contract_and_removes_upload_dir() -> None:
    runner = CliRunner()
    library_help = runner.invoke(cli.app, ["library", "--help"])
    upload_help = runner.invoke(cli.app, ["library", "upload-many", "--help"])
    normalized = " ".join(upload_help.output.split())

    assert library_help.exit_code == 0
    assert "upload-many" in library_help.output
    assert "upload-dir" not in library_help.output
    assert upload_help.exit_code == 0
    assert "never scans a directory" in normalized
    assert "working directory" in normalized
    assert "absolute paths" in normalized
    assert "--yes" in normalized
    assert "skipped or error entries" in normalized
