from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from uuid import uuid4

import httpx

from paper_agent import __version__
from paper_agent.protocol import CommandError, ErrorCode, ExitCode


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    bytes_written: int
    sha256: str
    source_url: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "bytes": self.bytes_written,
            "sha256": self.sha256,
            "source_url": self.source_url,
        }


def _quoted_segment(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="Resource identifier cannot be empty",
            exit_code=ExitCode.USAGE_ERROR,
        )
    return quote(cleaned, safe="")


def _network_error(method: str, path: str, exc: Exception) -> CommandError:
    return CommandError(
        code=ErrorCode.NETWORK_ERROR,
        message="Could not connect to the Frowang service",
        exit_code=ExitCode.NETWORK_OR_REMOTE,
        details={
            "method": method.upper(),
            "path": path,
            "error_type": type(exc).__name__,
        },
        retryable=True,
    )


def _local_io_error(operation: str, path: Path, exc: OSError) -> CommandError:
    return CommandError(
        code=ErrorCode.LOCAL_IO_ERROR,
        message="Paper Agent could not write a downloaded asset",
        exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        details={
            "operation": operation,
            "path": str(path),
            "error_type": type(exc).__name__,
        },
    )


class FrowangClient:
    """Synchronous Frowang HTTP adapter with public error mapping."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        timeout_seconds: float = 120.0,
        connect_timeout_seconds: float = 15.0,
        read_timeout_seconds: Optional[float] = None,
        write_timeout_seconds: Optional[float] = None,
        max_get_retries: int = 2,
        retry_backoff_seconds: float = 0.1,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise CommandError(
                code=ErrorCode.AUTH_MISSING,
                message="Frowang API key is not configured",
                exit_code=ExitCode.CONFIG_OR_AUTH,
            )
        if max_get_retries < 0:
            raise ValueError("max_get_retries cannot be negative")
        parsed = urlsplit(base_url.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CommandError(
                code=ErrorCode.CONFIG_INVALID,
                message="Frowang base URL must be an HTTP(S) URL",
                exit_code=ExitCode.CONFIG_OR_AUTH,
            )

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_get_retries = max_get_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._sleep = sleep
        self._owns_client = client is None
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=connect_timeout_seconds,
            read=read_timeout_seconds or timeout_seconds,
            write=write_timeout_seconds or timeout_seconds,
        )
        self._client = client or httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
            headers={"User-Agent": f"paper-agent/{__version__}"},
        )

        self._origin = (parsed.scheme.lower(), parsed.netloc.lower())
        api_path = parsed.path.rstrip("/")
        self._api_asset_prefix = (
            api_path.split("/api/", 1)[0] + "/"
            if "/api/" in api_path
            else "/"
        )
        self._asset_prefixes = tuple(
            dict.fromkeys((self._api_asset_prefix, "/outputs/", "/uploads/"))
        )

    def __enter__(self) -> FrowangClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self, *, bearer_token: Optional[str] = None) -> dict[str, str]:
        if bearer_token:
            return {"Authorization": f"Bearer {bearer_token}"}
        return {"X-API-Key": self.api_key}

    def _api_url(self, path: str) -> str:
        if not path.startswith("/") or ".." in path.split("/"):
            raise CommandError(
                code=ErrorCode.USAGE_ERROR,
                message="Frowang API path must be an absolute route without traversal",
                exit_code=ExitCode.USAGE_ERROR,
                details={"path": path},
            )
        return f"{self.base_url}{path}"

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
        files: Any = None,
        data: Any = None,
        timeout_seconds: Optional[float] = None,
        bearer_token: Optional[str] = None,
    ) -> dict[str, Any]:
        method = method.upper()
        url = self._api_url(path)
        retryable_method = method in {"GET", "HEAD"}
        attempts = self.max_get_retries + 1 if retryable_method else 1

        for attempt in range(attempts):
            try:
                request_options: dict[str, Any] = {
                    "headers": self._headers(bearer_token=bearer_token),
                    "params": params,
                    "json": json_body,
                    "files": files,
                    "data": data,
                }
                if timeout_seconds is not None:
                    request_options["timeout"] = timeout_seconds
                response = self._client.request(
                    method,
                    url,
                    **request_options,
                )
            except httpx.RequestError as exc:
                if attempt + 1 < attempts:
                    self._backoff(attempt)
                    continue
                raise _network_error(method, path, exc) from exc

            if response.status_code >= 400:
                if response.status_code >= 500 and attempt + 1 < attempts:
                    self._backoff(attempt)
                    continue
                raise self._http_error(response, method=method, path=path)

            try:
                payload = response.json()
            except ValueError as exc:
                raise CommandError(
                    code=ErrorCode.REMOTE_ERROR,
                    message="Frowang returned an invalid JSON response",
                    exit_code=ExitCode.NETWORK_OR_REMOTE,
                    details={
                        "status_code": response.status_code,
                        "method": method,
                        "path": path,
                    },
                ) from exc
            if not isinstance(payload, dict):
                raise CommandError(
                    code=ErrorCode.REMOTE_ERROR,
                    message="Frowang returned an unexpected JSON document",
                    exit_code=ExitCode.NETWORK_OR_REMOTE,
                    details={"method": method, "path": path},
                )
            return payload

        raise AssertionError("request loop exhausted")

    def request_jwt(
        self,
        method: str,
        path: str,
        jwt_token: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not jwt_token.strip():
            raise CommandError(
                code=ErrorCode.AUTH_MISSING,
                message="JWT token is required for API key management",
                exit_code=ExitCode.CONFIG_OR_AUTH,
            )
        return self.request_json(
            method,
            path,
            bearer_token=jwt_token,
            **kwargs,
        )

    def _backoff(self, attempt: int) -> None:
        delay = self.retry_backoff_seconds * (2**attempt)
        if delay > 0:
            self._sleep(delay)

    def _http_error(
        self,
        response: httpx.Response,
        *,
        method: str,
        path: str,
    ) -> CommandError:
        detail: Any
        try:
            payload = response.json()
            detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        except ValueError:
            detail = response.text

        remote_code: Optional[str] = None
        message = "Frowang request failed"
        if isinstance(detail, dict):
            raw_code = detail.get("code")
            if isinstance(raw_code, str):
                remote_code = raw_code.upper()
            raw_message = detail.get("message") or detail.get("detail")
            if isinstance(raw_message, str) and raw_message.strip():
                message = raw_message.strip()
        elif isinstance(detail, str) and detail.strip():
            message = detail.strip()

        status = response.status_code
        if status in {401, 403} or remote_code in {
            "INVALID_API_KEY",
            "REVOKED_API_KEY",
            "EXPIRED_API_KEY",
        }:
            code = ErrorCode.AUTH_INVALID
            exit_code = ExitCode.CONFIG_OR_AUTH
        elif remote_code == "NOT_READY":
            code = ErrorCode.NOT_READY
            exit_code = ExitCode.RESOURCE_STATE
        elif status == 404 or remote_code == "NOT_FOUND":
            code = ErrorCode.NOT_FOUND
            exit_code = ExitCode.RESOURCE_STATE
        elif status == 409:
            code = ErrorCode.CONFLICT
            exit_code = ExitCode.CONFLICT
        else:
            code = ErrorCode.REMOTE_ERROR
            exit_code = ExitCode.NETWORK_OR_REMOTE

        return CommandError(
            code=code,
            message=message,
            exit_code=exit_code,
            details={
                "status_code": status,
                "method": method,
                "path": path,
                "remote_code": remote_code,
            },
            retryable=status == 429 or status >= 500,
        )

    def _asset_url(self, asset_url: str) -> str:
        parsed = urlsplit(asset_url)
        if parsed.scheme or parsed.netloc:
            origin = (parsed.scheme.lower(), parsed.netloc.lower())
            if origin != self._origin:
                raise CommandError(
                    code=ErrorCode.PERMISSION_DENIED,
                    message="Asset URL does not belong to the configured Frowang origin",
                    exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
                )
            path = parsed.path
            query = parsed.query
        else:
            path = parsed.path
            query = parsed.query

        if not path.startswith(self._asset_prefixes) or ".." in path.split("/"):
            raise CommandError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Asset URL is outside the allowed Frowang path",
                exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
                details={"allowed_prefixes": list(self._asset_prefixes)},
            )
        encoded_path = quote(unquote(path), safe="/:%@")
        base = urlsplit(self.base_url)
        # 如果路径以 /outputs/ 或 /uploads/ 开头，需要添加 API 前缀
        if path.startswith(("/outputs/", "/uploads/")) and self._api_asset_prefix != "/":
            encoded_path = self._api_asset_prefix.rstrip("/") + encoded_path
        return urlunsplit((base.scheme, base.netloc, encoded_path, query, ""))

    def get_paper_metadata(self, paper_id_or_ref: str) -> dict[str, Any]:
        """Fetch the academic metadata envelope for a paper."""
        return self.request_json(
            "GET", f"/papers/{_quoted_segment(paper_id_or_ref)}/metadata"
        )

    def get_paper_attribute_tree(self, paper_id_or_ref: str) -> dict[str, Any]:
        """Fetch the attribute tree envelope for a paper."""
        return self.request_json(
            "GET", f"/papers/{_quoted_segment(paper_id_or_ref)}/attribute-tree"
        )

    def create_paper_screenshots(
        self,
        paper_id_or_ref: str,
        *,
        capture_pdf: bool = True,
        capture_html: bool = True,
        force_rescreenshot: bool = False,
    ) -> dict[str, Any]:
        """Trigger asynchronous screenshot generation for a paper."""
        return self.request_json(
            "POST",
            f"/papers/{_quoted_segment(paper_id_or_ref)}/screenshots",
            params={
                "capture_pdf": capture_pdf,
                "capture_html": capture_html,
                "force_rescreenshot": force_rescreenshot,
            },
        )

    def get_paper_screenshots(
        self, paper_id_or_ref: str, *, job_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Fetch existing screenshots, or a generation job progress with job_id."""
        params = {"job_id": job_id} if job_id else None
        return self.request_json(
            "GET",
            f"/papers/{_quoted_segment(paper_id_or_ref)}/screenshots",
            params=params,
        )

    def download_asset(self, asset_url: str, destination: Path) -> DownloadResult:
        url = self._asset_url(asset_url)
        target = destination.expanduser().resolve()
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        digest = hashlib.sha256()
        bytes_written = 0
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with self._client.stream("GET", url, headers=self._headers()) as response:
                if response.status_code >= 400:
                    raise self._http_error(response, method="GET", path=urlsplit(url).path)
                with temporary.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
                        digest.update(chunk)
                        bytes_written += len(chunk)
            os.replace(temporary, target)
        except httpx.RequestError as exc:
            raise _network_error("GET", urlsplit(url).path, exc) from exc
        except OSError as exc:
            raise _local_io_error("download_asset", target, exc) from exc
        finally:
            if temporary.exists():
                temporary.unlink()

        return DownloadResult(
            path=target,
            bytes_written=bytes_written,
            sha256=digest.hexdigest(),
            source_url=asset_url,
        )
