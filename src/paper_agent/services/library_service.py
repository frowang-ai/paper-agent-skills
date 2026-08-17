from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote

from paper_agent.clients import FrowangClient
from paper_agent.protocol import CommandError, ErrorCode, ExitCode


_VALID_LAYERS = {"L1", "L2", "L3"}


def _segment(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="Resource identifier cannot be empty",
            exit_code=ExitCode.USAGE_ERROR,
        )
    return quote(cleaned, safe="")


def _unwrap(response: dict[str, Any]) -> Any:
    if response.get("success") is True and "data" in response:
        return response["data"]
    return response


def _usage(message: str, **details: object) -> CommandError:
    return CommandError(
        code=ErrorCode.USAGE_ERROR,
        message=message,
        exit_code=ExitCode.USAGE_ERROR,
        details=details,
    )


class LibraryService:
    def __init__(self, client: FrowangClient) -> None:
        self.client = client

    def list_papers(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        tag: Optional[str] = None,
        sort_by: str = "created_at",
        order: str = "DESC",
    ) -> Any:
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "order": order,
        }
        if tag:
            params["tag"] = tag
        return _unwrap(self.client.request_json("GET", "/papers", params=params))

    def search(self, query: str, *, scope: str = "discovery", limit: int = 10) -> Any:
        if scope not in {"discovery", "metadata", "title"}:
            raise _usage("scope must be discovery, metadata, or title", scope=scope)
        return _unwrap(
            self.client.request_json(
                "GET",
                "/papers/search",
                params={"q": query, "scope": scope, "limit": limit},
            )
        )

    def search_layered(
        self,
        query: str,
        *,
        layer: str = "all",
        layers: Optional[str] = None,
        limit: int = 20,
    ) -> Any:
        normalized = layer.strip().lower()
        if normalized not in {"l1", "l2", "l3", "all"}:
            raise _usage("layer must be L1, L2, L3, or all", layer=layer)
        params: dict[str, Any] = {"q": query, "limit": limit}
        if normalized == "all" and layers:
            subset = [item.strip().upper() for item in layers.split(",") if item.strip()]
            invalid = [item for item in subset if item not in _VALID_LAYERS]
            if invalid:
                raise _usage("layers contains unsupported values", invalid=invalid)
            params["layers"] = ",".join(subset)
        return _unwrap(
            self.client.request_json(
                "GET",
                f"/papers/search/{normalized}",
                params=params,
            )
        )

    def show(self, paper_id: str) -> Any:
        return _unwrap(self.client.request_json("GET", f"/papers/{_segment(paper_id)}"))

    def get_content(self, paper_id: str, kind: str) -> str:
        if kind not in {"fulltext", "summary", "deep"}:
            raise _usage("Unsupported paper content kind", kind=kind)
        result = _unwrap(
            self.client.request_json("GET", f"/papers/{_segment(paper_id)}/{kind}")
        )
        content = result.get("content") if isinstance(result, dict) else None
        if not isinstance(content, str):
            raise CommandError(
                code=ErrorCode.REMOTE_ERROR,
                message="Frowang content response did not include text content",
                exit_code=ExitCode.NETWORK_OR_REMOTE,
                details={"paper_id": paper_id, "kind": kind},
            )
        return content

    def assets(self, paper_id: str) -> Any:
        return _unwrap(
            self.client.request_json("GET", f"/papers/{_segment(paper_id)}/assets")
        )

    def metadata(self, paper_id: str) -> Any:
        return _unwrap(self.client.get_paper_metadata(paper_id))

    def attribute_tree(self, paper_id: str) -> Any:
        return _unwrap(self.client.get_paper_attribute_tree(paper_id))

    def screenshots(self, paper_id: str, *, job_id: Optional[str] = None) -> Any:
        return _unwrap(self.client.get_paper_screenshots(paper_id, job_id=job_id))

    def create_screenshots(
        self,
        paper_id: str,
        *,
        capture_pdf: bool = True,
        capture_html: bool = True,
        force_rescreenshot: bool = False,
    ) -> Any:
        if not capture_pdf and not capture_html:
            raise _usage("capture_pdf and capture_html cannot both be disabled")
        return _unwrap(
            self.client.create_paper_screenshots(
                paper_id,
                capture_pdf=capture_pdf,
                capture_html=capture_html,
                force_rescreenshot=force_rescreenshot,
            )
        )

    def download_asset(self, asset_url: str, destination: Path) -> dict[str, object]:
        return self.client.download_asset(asset_url, destination).as_dict()

    def reprocess(self, paper_id: str) -> Any:
        return _unwrap(
            self.client.request_json("POST", f"/papers/{_segment(paper_id)}/reprocess")
        )

    def update_metadata(self, paper_id: str, fields: dict[str, Any]) -> Any:
        body = {key: value for key, value in fields.items() if value is not None}
        if not body:
            raise _usage("At least one metadata field must be provided")
        return _unwrap(
            self.client.request_json(
                "PATCH",
                f"/papers/{_segment(paper_id)}/metadata",
                json_body=body,
            )
        )

    def delete(self, paper_id: str) -> Any:
        return _unwrap(
            self.client.request_json("DELETE", f"/papers/{_segment(paper_id)}")
        )

    def upload(self, file: Path, *, filename: Optional[str] = None) -> Any:
        path = file.expanduser().resolve()
        if not path.is_file():
            raise _usage("PDF file does not exist", path=str(path))
        if path.suffix.lower() != ".pdf":
            raise _usage("Upload file must be a PDF", path=str(path))
        upload_name = filename or path.name
        if Path(upload_name).name != upload_name or not upload_name.lower().endswith(".pdf"):
            raise _usage("Upload filename must be a plain PDF filename", filename=upload_name)
        try:
            with path.open("rb") as handle:
                response = self.client.request_json(
                    "POST",
                    "/papers",
                    files={"file": (upload_name, handle, "application/pdf")},
                    timeout_seconds=300.0,
                )
        except OSError as exc:
            raise CommandError(
                code=ErrorCode.LOCAL_IO_ERROR,
                message="Paper Agent could not read the PDF",
                exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
                details={"path": str(path), "error_type": type(exc).__name__},
            ) from exc
        return _unwrap(response)

    def upload_many(self, files: Iterable[Path]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for file in files:
            path = file.expanduser().resolve()
            entry: dict[str, Any] = {"file": path.name, "path": str(path)}
            if not path.is_file():
                entry.update(status="skipped", reason="file not found")
            elif path.suffix.lower() != ".pdf":
                entry.update(status="skipped", reason="not a PDF")
            else:
                try:
                    data = self.upload(path)
                    remote = data if isinstance(data, dict) else {}
                    is_new = remote.get("is_new", True)
                    entry.update(
                        status="uploaded" if is_new else "duplicate",
                        paper_id=remote.get("paper_id"),
                        short_id=remote.get("short_id"),
                        task_id=remote.get("task_id"),
                        is_new=is_new,
                    )
                except CommandError as exc:
                    entry.update(status="error", reason=exc.message, error_code=exc.code.value)
            results.append(entry)
        return {
            "results": results,
            "total": len(results),
            "uploaded": sum(item["status"] == "uploaded" for item in results),
            "duplicates": sum(item["status"] == "duplicate" for item in results),
            "skipped": sum(item["status"] == "skipped" for item in results),
            "errors": sum(item["status"] == "error" for item in results),
        }

    def add_tags(self, paper_id: str, tags: list[str]) -> Any:
        return _unwrap(
            self.client.request_json(
                "POST", f"/papers/{_segment(paper_id)}/tags", json_body=tags
            )
        )

    def set_tags(self, paper_id: str, tags: list[str]) -> Any:
        return _unwrap(
            self.client.request_json(
                "PUT", f"/papers/{_segment(paper_id)}/tags", json_body=tags
            )
        )

    def remove_tag(self, paper_id: str, tag: str) -> Any:
        return _unwrap(
            self.client.request_json(
                "DELETE", f"/papers/{_segment(paper_id)}/tags/{_segment(tag)}"
            )
        )

    def list_notes(self, paper_id: str) -> Any:
        return _unwrap(
            self.client.request_json("GET", f"/papers/{_segment(paper_id)}/notes")
        )

    def add_note(self, paper_id: str, content: str) -> Any:
        return _unwrap(
            self.client.request_json(
                "POST",
                f"/papers/{_segment(paper_id)}/notes",
                params={"content": content},
            )
        )

    def list_annotations(self, paper_id: str, *, since: Optional[str] = None) -> Any:
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        return _unwrap(
            self.client.request_json(
                "GET", f"/papers/{_segment(paper_id)}/annotations", params=params
            )
        )

    def append_annotation_comment(
        self, paper_id: str, annotation_id: str, comment: str
    ) -> Any:
        """向已有批注追加 comment（换行拼接），LWW 靠服务器时钟取胜。"""
        if not comment.strip():
            raise _usage("Comment text cannot be empty")
        data = _unwrap(
            self.client.request_json(
                "GET", f"/papers/{_segment(paper_id)}/annotations"
            )
        )
        annotations = data.get("annotations", []) if isinstance(data, dict) else []
        target = next(
            (a for a in annotations if a.get("id") == annotation_id), None
        )
        if target is None:
            raise CommandError(
                code=ErrorCode.NOT_FOUND,
                message=f"Annotation {annotation_id} not found on paper {paper_id}",
                exit_code=ExitCode.RESOURCE_STATE,
            )
        existing = (target.get("comment") or "").rstrip()
        merged = f"{existing}\n{comment.strip()}" if existing else comment.strip()
        # updatedAt 用服务器时钟 +1s，确保 LWW 覆盖本地未同步的旧值
        server_time = str(data.get("serverTime") or "")
        if server_time:
            from datetime import datetime, timedelta

            try:
                stamp = datetime.fromisoformat(server_time) + timedelta(seconds=1)
                target["updatedAt"] = stamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                pass
        target["comment"] = merged
        target.pop("isDeleted", None)
        target.pop("sortKey", None)
        return _unwrap(
            self.client.request_json(
                "POST",
                f"/papers/{_segment(paper_id)}/annotations/sync",
                json_body={"upserts": [target], "deletions": []},
            )
        )

    def list_collections(self) -> Any:
        return _unwrap(self.client.request_json("GET", "/collections"))

    def create_collection(self, name: str, parent_key: Optional[str] = None) -> Any:
        body: dict[str, Any] = {"name": name}
        if parent_key:
            body["parent_key"] = parent_key
        return _unwrap(
            self.client.request_json("POST", "/collections", json_body=body)
        )

    def update_collection(self, key: str, fields: dict[str, Any]) -> Any:
        body = dict(fields)
        if not body:
            raise _usage("At least one collection field must be provided")
        return _unwrap(
            self.client.request_json(
                "PATCH", f"/collections/{_segment(key)}", json_body=body
            )
        )

    def delete_collection(self, key: str) -> Any:
        return _unwrap(
            self.client.request_json("DELETE", f"/collections/{_segment(key)}")
        )

    def collection_items(self, key: str) -> Any:
        return _unwrap(
            self.client.request_json("GET", f"/collections/{_segment(key)}/items")
        )

    def add_collection_items(self, key: str, task_ids: list[str]) -> Any:
        return _unwrap(
            self.client.request_json(
                "POST",
                f"/collections/{_segment(key)}/items",
                json_body={"task_ids": task_ids},
            )
        )

    def remove_collection_items(self, key: str, task_ids: list[str]) -> Any:
        return _unwrap(
            self.client.request_json(
                "DELETE",
                f"/collections/{_segment(key)}/items",
                json_body={"task_ids": task_ids},
            )
        )

    def create_api_key(self, jwt_token: str, name: str = "default") -> Any:
        return _unwrap(
            self.client.request_jwt(
                "POST", "/api-keys", jwt_token, params={"name": name}
            )
        )

    def list_api_keys(self, jwt_token: str) -> Any:
        return _unwrap(self.client.request_jwt("GET", "/api-keys", jwt_token))

    def revoke_api_key(self, key_id: str, jwt_token: str) -> Any:
        return _unwrap(
            self.client.request_jwt(
                "DELETE", f"/api-keys/{_segment(key_id)}", jwt_token
            )
        )
