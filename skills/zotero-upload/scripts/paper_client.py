"""Deprecated compatibility name backed by the Paper Agent runtime."""
from typing import Any, Optional

from paper_agent.clients import FrowangClient


class PaperClient(FrowangClient):
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Any = None,
        files: Any = None,
        data: Any = None,
        timeout: float = 300.0,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        del max_retries
        return self.request_json(
            method,
            path,
            params=params,
            json_body=json_body,
            files=files,
            data=data,
            timeout_seconds=timeout,
        )

__all__ = ["FrowangClient", "PaperClient"]
