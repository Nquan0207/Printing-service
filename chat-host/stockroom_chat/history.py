"""Chat transcript persistence, over the Go API rather than SQL.

backend-ops owns every statement against Postgres (see CLAUDE.md), so the chat
service stores its transcript by calling /api/v1/chat/messages with the demo
user's id in X-Stockroom-User -- the same header the storefront sends.

Persistence is best-effort on purpose: a chat that cannot reach the history
endpoint should still answer the user, just without remembering afterwards.
Every failure is logged and swallowed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx


log = logging.getLogger(__name__)

# Roles the Go schema's CHECK constraint accepts.
ROLES = {"user", "assistant", "tool"}


class ChatHistory:
    def __init__(self, client: httpx.AsyncClient, api_url: str):
        self.client = client
        self.api_url = api_url.rstrip("/")

    def _headers(self, user_id: int) -> dict[str, str]:
        return {"X-Stockroom-User": str(user_id)}

    async def load(self, user_id: int) -> list[dict[str, Any]]:
        """Return the stored transcript, oldest first. [] on any failure."""
        try:
            response = await self.client.get(
                f"{self.api_url}/api/v1/chat/messages",
                headers=self._headers(user_id),
                timeout=10.0,
            )
            response.raise_for_status()
            messages = response.json().get("messages")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            log.warning("chat history load failed for user %s: %s", user_id, exc)
            return []
        return messages if isinstance(messages, list) else []

    async def append(
        self,
        user_id: int,
        role: str,
        content: str,
        *,
        tool_name: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if role not in ROLES:
            raise ValueError(f"unsupported chat role: {role!r}")
        body: dict[str, Any] = {"role": role, "content": content, "tool_name": tool_name}
        if payload is not None:
            body["payload"] = payload
        try:
            response = await self.client.post(
                f"{self.api_url}/api/v1/chat/messages",
                json=body,
                headers=self._headers(user_id),
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("chat history append failed for user %s: %s", user_id, exc)

    async def clear(self, user_id: int) -> None:
        try:
            response = await self.client.delete(
                f"{self.api_url}/api/v1/chat/messages",
                headers=self._headers(user_id),
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("chat history clear failed for user %s: %s", user_id, exc)


def model_messages(system_prompt: str, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rebuild an Ollama message list from a stored transcript.

    Only user and assistant prose is replayed. Tool lines are deliberately
    dropped: Ollama requires a tool message to follow an assistant message
    carrying the matching tool_calls, and those call ids do not survive a
    restart. The browser still re-renders the tool cards from `payload`, so the
    user sees the full history even though the model resumes with the prose.
    """
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for item in transcript:
        role = item.get("role")
        content = item.get("content") or ""
        if role in {"user", "assistant"} and content:
            out.append({"role": role, "content": content})
    return out
