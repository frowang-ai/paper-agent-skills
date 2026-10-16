from __future__ import annotations

from typing import Any, Iterator, Mapping, Optional

from paper_agent.clients import FrowangClient


def _unwrap(response: dict[str, Any]) -> Any:
    if response.get("success") is True and "data" in response:
        return response["data"]
    return response


class AssistantService:
    """Application service for the unified personal assistant API."""

    def __init__(self, client: FrowangClient) -> None:
        self.client = client

    def ask(
        self,
        message: str,
        *,
        conversation_id: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Iterator[dict[str, Any]]:
        return self.client.stream_agentic_chat(
            message,
            conversation_id=conversation_id,
            context=context,
        )

    def retry(self, conversation_id: str, message_id: str) -> Iterator[dict[str, Any]]:
        return self.client.retry_agentic_chat(conversation_id, message_id)

    def list_conversations(self, *, limit: Optional[int] = None) -> Any:
        return _unwrap(self.client.list_chat_conversations(limit=limit))

    def history(self, conversation_id: str) -> Any:
        return _unwrap(self.client.get_chat_history(conversation_id))

    def stop(self, run_id: str) -> Any:
        return _unwrap(self.client.stop_chat_run(run_id))

    def delete_conversation(self, conversation_id: str) -> Any:
        return _unwrap(self.client.delete_chat_conversation(conversation_id))

    def delete_message(self, conversation_id: str, message_id: str) -> Any:
        return _unwrap(self.client.delete_chat_message(conversation_id, message_id))
