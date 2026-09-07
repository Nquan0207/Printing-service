from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import secrets
from typing import Any, Callable

from stockroom_chat.mcp_client import StockroomMCPConnection


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove server-held capabilities before returning data to a model/browser."""
    output = deepcopy(payload)
    confirmation = output.get("confirmation")
    if isinstance(confirmation, dict):
        confirmation.pop("token", None)
    return output


def model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep useful commerce facts but hide UI-only image fields from the model."""

    def without_images(value: Any) -> Any:
        if isinstance(value, list):
            return [without_images(item) for item in value]
        if isinstance(value, dict):
            return {
                key: without_images(item)
                for key, item in value.items()
                if key not in {"image", "images"}
            }
        return value

    return without_images(public_payload(payload))


SYSTEM_PROMPT = """You are the local Stockroom shopping assistant. Reply in the user's language.

MCP-first policy:
- For every request about products, categories, availability, product details, prices, sizes, quotes,
  recommendations, comparisons, the cart, or orders, call the most relevant supplied MCP tool before answering.
- Treat MCP tool results as the only source of truth. Never invent or infer product IDs, size IDs, prices,
  stock, cart totals, or order numbers. If required information is missing, ask one short question.
- The catalog is written in Japanese. search_products `query` is a literal substring match over the
  product text, so an English word finds nothing; `category` is the argument that accepts English,
  slugs and Japanese alike. For an English request put the user's words in `category`. An empty result
  means the search missed, not that the shop is empty -- retry through `category` before saying there
  is nothing.
- Use conversation context to reuse IDs only when those IDs originally came from an MCP result.
- Only modify the cart when the user clearly asks. You may prepare an order, but you cannot place it;
  the user must approve or reject the confirmation card in the interface. Checkout is a mock and moves no money.

UI response policy:
- Structured MCP results are rendered automatically by the browser as product cards, clickable category
  chips, and cart, confirmation and receipt panels.
- You cannot draw anything yourself. Calling the right tool IS how something appears on screen: if the
  user asks to see products, call search_products -- do not describe what they could click instead.
- After a successful tool result, respond with at most two short sentences describing the outcome or the next action.
- Do not repeat the full tool result in prose. Do not enumerate every product or size.
- Never print image URLs, raw URLs, JSON, internal IDs, markdown image syntax, tables, or long bullet lists.
- For search results, say only how many matches were found and invite the user to use the displayed cards.
- For cart results, state only the item count and total when useful; let the cart panel show line details.
- A greeting or a general non-shopping question may be answered directly, briefly, without a tool.
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

    @property
    def user_id(self) -> int | None:
        """The Stockroom user id from mock_sign_in, or None before sign-in.

        This is what X-Stockroom-User carries when the chat service persists a
        transcript through the Go API.
        """
        if isinstance(self.user, dict):
            value = self.user.get("user_id")
            if isinstance(value, int) and value > 0:
                return value
        return None

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
        mcp_url: str,
        ttl_seconds: int,
        max_sessions: int = 20,
        mcp_factory: Callable[..., Any] = StockroomMCPConnection,
    ):
        self.mcp_url = mcp_url
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
        mcp = self.mcp_factory(self.mcp_url)
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
