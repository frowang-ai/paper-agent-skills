from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from paper_agent.clients import FrowangClient
from paper_agent.protocol import CommandError, ErrorCode, ExitCode
from paper_agent.services import ArtifactSyncService, LibraryService
from paper_agent.storage import StateStore


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

PAPER_ID = "11111111-1111-1111-1111-111111111111"

ACADEMIC_METADATA = {
    "title": "Test Paper",
    "authors": [{"family": "Smith", "given": "Alice"}],
    "doi": "10.0000/test",
    "journal": "Journal of Tests",
    "publication_year": 2024,
    "publication_date": "2024-05-01",
    "citations": {"apa": "Smith, A. (2024). Test Paper."},
    "task_id": "task-1",
    "paper_fingerprint": "fp-1",
    "generated_at": "2026-07-28T00:00:00Z",
}

ATTRIBUTE_TREE = {"root": {"children": [{"name": "method"}]}}


def _client(handler) -> FrowangClient:
    return FrowangClient(
        api_key="pk_test_secret",
        base_url="https://example.test/paper-api/api/v1",
        transport=httpx.MockTransport(handler),
        max_get_retries=0,
    )


def test_client_get_paper_metadata_uses_metadata_route_and_returns_envelope() -> None:
    seen_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.path
        return httpx.Response(200, json={"success": True, "data": ACADEMIC_METADATA})

    with _client(handler) as client:
        payload = client.get_paper_metadata("P-3a")

    assert seen_path == "/paper-api/api/v1/papers/P-3a/metadata"
    assert payload["success"] is True
    assert payload["data"]["doi"] == "10.0000/test"


def test_client_get_paper_attribute_tree_uses_attribute_tree_route() -> None:
    seen_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.path
        return httpx.Response(200, json={"success": True, "data": ATTRIBUTE_TREE})

    with _client(handler) as client:
        payload = client.get_paper_attribute_tree("P-3a")

    assert seen_path == "/paper-api/api/v1/papers/P-3a/attribute-tree"
    assert payload["data"] == ATTRIBUTE_TREE


@pytest.mark.parametrize(
    ("remote_code", "code"),
    [("NOT_READY", ErrorCode.NOT_READY), ("NOT_FOUND", ErrorCode.NOT_FOUND)],
)
def test_client_maps_metadata_failures(remote_code: str, code: ErrorCode) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"detail": {"code": remote_code, "message": "not available"}}
        )

    with _client(handler) as client, pytest.raises(CommandError) as caught:
        client.get_paper_metadata("P-3a")

    assert caught.value.code == code
    assert caught.value.exit_code == ExitCode.RESOURCE_STATE
    assert caught.value.details["remote_code"] == remote_code


def test_client_maps_attribute_tree_not_ready() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"detail": {"code": "NOT_READY", "message": "processing"}}
        )

    with _client(handler) as client, pytest.raises(CommandError) as caught:
        client.get_paper_attribute_tree("P-3a")

    assert caught.value.code == ErrorCode.NOT_READY


def test_library_service_unwraps_metadata_and_attribute_tree_envelopes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/metadata"):
            return httpx.Response(200, json={"success": True, "data": ACADEMIC_METADATA})
        return httpx.Response(200, json={"success": True, "data": ATTRIBUTE_TREE})

    with _client(handler) as client:
        service = LibraryService(client)
        metadata = service.metadata("P-3a")
        tree = service.attribute_tree("P-3a")

    assert metadata == ACADEMIC_METADATA
    assert tree == ATTRIBUTE_TREE


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


def _cli_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.endswith("/papers/P-1/metadata"):
                body = json.dumps({"success": True, "data": ACADEMIC_METADATA}).encode()
                self.send_response(200)
            elif self.path.endswith("/papers/P-1/attribute-tree"):
                body = json.dumps({"success": True, "data": ATTRIBUTE_TREE}).encode()
                self.send_response(200)
            else:
                body = json.dumps(
                    {"detail": {"code": "NOT_FOUND", "message": "missing"}}
                ).encode()
                self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/api/v1"


def test_library_metadata_cli_emits_envelope_and_saves_json(tmp_path: Path) -> None:
    server, thread, base_url = _cli_server()
    destination = tmp_path / "out" / "metadata.json"
    try:
        _run(tmp_path, "config", "init")
        plain = _run(
            tmp_path,
            "library", "--base-url", base_url, "metadata", "P-1", "--json",
            FROWANG_API_KEY="pk_cli_test",
        )
        saved = _run(
            tmp_path,
            "library", "--base-url", base_url, "metadata", "P-1",
            "--save", str(destination),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(plain.stdout)
    assert plain.returncode == 0, plain.stderr
    assert payload["success"] is True
    assert payload["meta"]["command"] == "library.metadata"
    assert payload["data"]["doi"] == "10.0000/test"

    payload = json.loads(saved.stdout)
    assert saved.returncode == 0, saved.stderr
    assert payload["data"]["path"] == str(destination.resolve())
    assert payload["data"]["bytes"] == destination.stat().st_size
    assert payload["data"]["kind"] == "metadata"
    saved_doc = json.loads(destination.read_text(encoding="utf-8"))
    assert saved_doc == ACADEMIC_METADATA


def test_library_attribute_tree_cli_emits_envelope_and_saves_json(tmp_path: Path) -> None:
    server, thread, base_url = _cli_server()
    destination = tmp_path / "out" / "tree.json"
    try:
        _run(tmp_path, "config", "init")
        plain = _run(
            tmp_path,
            "library", "--base-url", base_url, "attribute-tree", "P-1", "--json",
            FROWANG_API_KEY="pk_cli_test",
        )
        saved = _run(
            tmp_path,
            "library", "--base-url", base_url, "attribute-tree", "P-1",
            "--save", str(destination),
            FROWANG_API_KEY="pk_cli_test",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    payload = json.loads(plain.stdout)
    assert plain.returncode == 0, plain.stderr
    assert payload["meta"]["command"] == "library.attribute-tree"
    assert payload["data"] == ATTRIBUTE_TREE

    payload = json.loads(saved.stdout)
    assert saved.returncode == 0, saved.stderr
    assert payload["data"]["path"] == str(destination.resolve())
    assert payload["data"]["kind"] == "attribute_tree"
    assert json.loads(destination.read_text(encoding="utf-8")) == ATTRIBUTE_TREE


class FakeSyncLibrary:
    def __init__(self, *, tree_url: object = "/outputs/task-1/attribute_tree.json") -> None:
        self.tree_url = tree_url
        self.downloads: list[str] = []

    def show(self, paper_ref: str) -> dict[str, object]:
        return {
            "paper_id": PAPER_ID,
            "title": "Test Paper",
            "publication_year": 2024,
            "authors": [{"family": "Smith", "given": "Alice"}],
            "latest_task_id": "task-1",
        }

    def metadata(self, paper_ref: str) -> dict[str, object]:
        return dict(ACADEMIC_METADATA)

    def assets(self, paper_ref: str) -> dict[str, object]:
        return {
            "paper_id": PAPER_ID,
            "assets": {
                "ocr_markdown_url": "/outputs/task-1/complete.md",
                "layout_url": "/outputs/task-1/layout.json",
                "metadata_url": None,
                "attribute_tree_url": self.tree_url,
            },
        }

    def download_asset(self, asset_url: str, destination: Path) -> dict[str, object]:
        if asset_url.endswith("layout.json"):
            content = b'{"pages": []}\n'
        elif asset_url.endswith("attribute_tree.json"):
            content = json.dumps(ATTRIBUTE_TREE).encode()
        else:
            content = b"# Test\n\nEvidence.\n"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        self.downloads.append(asset_url)
        return {
            "path": str(destination),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "source_url": asset_url,
        }


def _sync_service(tmp_path: Path, library: FakeSyncLibrary) -> ArtifactSyncService:
    return ArtifactSyncService(
        library=library,  # type: ignore[arg-type]
        state_store=StateStore(tmp_path / "state.sqlite3"),
        data_dir=tmp_path / "data",
        profile="default",
        base_url="https://frowang.test/paper-api/api/v1",
        clock=lambda: "2026-07-28T12:00:00Z",
    )


def test_sync_writes_academic_metadata_and_optional_attribute_tree(tmp_path: Path) -> None:
    library = FakeSyncLibrary()
    service = _sync_service(tmp_path, library)

    result = service.sync("P-1")
    revision_root = Path(result["revision_root"])
    manifest = json.loads((revision_root / "artifact-manifest.json").read_text())

    stored = json.loads((revision_root / "metadata.json").read_text(encoding="utf-8"))
    assert stored == ACADEMIC_METADATA
    assert "user_id" not in stored

    tree_entry = manifest["artifacts"]["attribute_tree"]
    assert tree_entry["required"] is False
    assert tree_entry["path"] == "attribute_tree.json"
    assert tree_entry["source_url"] == "/outputs/task-1/attribute_tree.json"
    tree_path = revision_root / "attribute_tree.json"
    assert tree_entry["bytes"] == tree_path.stat().st_size
    assert tree_entry["sha256"] == hashlib.sha256(tree_path.read_bytes()).hexdigest()
    assert json.loads(tree_path.read_text(encoding="utf-8")) == ATTRIBUTE_TREE
    assert manifest["artifacts"]["metadata"]["required"] is True
    assert set(manifest["artifacts"]) == {"metadata", "fulltext", "layout", "attribute_tree"}

    second = service.sync("P-1")
    assert second["cache_hit"] is True
    assert len(library.downloads) == 3


def test_sync_skips_attribute_tree_when_url_missing(tmp_path: Path) -> None:
    library = FakeSyncLibrary(tree_url=None)
    service = _sync_service(tmp_path, library)

    result = service.sync("P-1")
    revision_root = Path(result["revision_root"])
    manifest = json.loads((revision_root / "artifact-manifest.json").read_text())

    assert result["cache_hit"] is False
    assert set(manifest["artifacts"]) == {"metadata", "fulltext", "layout"}
    assert not (revision_root / "attribute_tree.json").exists()
    stored = json.loads((revision_root / "metadata.json").read_text(encoding="utf-8"))
    assert stored["doi"] == "10.0000/test"
