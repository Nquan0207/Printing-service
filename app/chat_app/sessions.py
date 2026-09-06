from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Callable

from app.chat_app.mcp_client import StockroomMCPConnection


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove server-held capabilities before returning data to a model/browser."""
    output = deepcopy(payload)
    confirmation = output.get("confirmation")
    if isinstance(confirmation, dict):
        confirmation.pop("token", None)
    return output


SYSTEM_PROMPT = """You are the local Stockroom shopping assistant.
Use the supplied tools for every catalog fact, product ID, size ID, price, cart total, and order number.
Never invent catalog data. Ask for a size or quantity when it is missing.
Only modify the cart when the user clearly asks. You may prepare an order, but you cannot place it;
the user must approve or reject the confirmation card in the interface. Checkout is a mock and moves no money.
Keep answers concise and reply in the user's language.
"""


@dataclass
class ChatSession:
    token: str
    mcp: Any
    created_at: datetime
    last_seen: datetime
    user: dict[str, Any] | None = None
    cart: dict[str, Any] | None = None
    confirmation: dict[str, Any] | None = None
    confirmation_decision: str | None = None
    order: dict[str, Any] | None = None
    messages: list[dict[str, Any]] = field(
        default_factory=lambda: [{"role": "system", "content": SYSTEM_PROMPT}]
    )
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        self.last_seen = utcnow()

    def ingest(self, payload: dict[str, Any], tool_name: str | None = None) -> None:
        if isinstance(payload.get("user"), dict):
            self.user = payload["user"]
        if isinstance(payload.get("cart"), dict):
            self.cart = payload["cart"]
        if isinstance(payload.get("confirmation"), dict):
            self.confirmation = payload["confirmation"]
            self.confirmation_decision = None
        if isinstance(payload.get("order"), dict):
            self.order = payload["order"]
        if tool_name in {"add_to_cart", "remove_cart_item"}:
            self.confirmation = None
            self.confirmation_decision = None
            self.order = None


class SessionStore:
    def __init__(
        self,
        *,
        project_root,
        api_url: str,
        ttl_seconds: int,
        max_sessions: int = 20,
        mcp_factory: Callable[..., Any] = StockroomMCPConnection,
    ):
        self.project_root = project_root
        self.api_url = api_url
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_sessions = max_sessions
        self.mcp_factory = mcp_factory
        self._sessions: dict[str, ChatSession] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> ChatSession:
        await self.cleanup_expired()
        async with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeError("Too many active chat sessions. Log out an old session and retry.")
        mcp = self.mcp_factory(self.project_root, self.api_url)
        await mcp.start()
        now = utcnow()
        state = ChatSession(secrets.token_urlsafe(32), mcp, now, now)
        async with self._lock:
            self._sessions[state.token] = state
        return state

    async def get(self, token: str | None) -> ChatSession | None:
        if not token:
            return None
        async with self._lock:
            state = self._sessions.get(token)
            if state and utcnow() - state.last_seen <= self.ttl:
                state.touch()
                return state
            if state:
                self._sessions.pop(token, None)
        if state:
            await state.mcp.close()
        return None

    async def delete(self, token: str | None) -> None:
        if not token:
            return
        async with self._lock:
            state = self._sessions.pop(token, None)
        if state:
            await state.mcp.close()

    async def cleanup_expired(self) -> None:
        deadline = utcnow() - self.ttl
        async with self._lock:
            expired = [key for key, value in self._sessions.items() if value.last_seen < deadline]
            states = [self._sessions.pop(key) for key in expired]
        for state in states:
            await state.mcp.close()

    async def close(self) -> None:
        async with self._lock:
            states = list(self._sessions.values())
            self._sessions.clear()
        for state in states:
            await state.mcp.close()
