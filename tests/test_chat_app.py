from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.chat_app.config import ChatSettings
from app.chat_app.main import COOKIE_NAME, _valid_media_path, create_app
from app.chat_app.mcp_client import MODEL_BLOCKED_TOOLS, ollama_tools
from app.chat_app.ollama_agent import OllamaAgent
<<<<<<< Updated upstream
from app.chat_app.sessions import ChatSession, SessionStore, utcnow
=======
from app.chat_app.sessions import ChatSession, SessionStore, model_payload, utcnow
>>>>>>> Stashed changes


EMPTY_CART = {"items": [], "item_count": 0, "total_jpy": 0}


class FakeMCP:
    instances = []

    def __init__(self, project_root, api_url):
        self.project_root = project_root
        self.api_url = api_url
        self.calls = []
        self.closed = False
        self.model_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_products",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        self.allowed_model_tools = {"search_products"}
        self.cart = dict(EMPTY_CART)
        FakeMCP.instances.append(self)

    async def start(self):
        return None

    async def close(self):
        self.closed = True

    async def call(self, name, arguments=None):
        arguments = arguments or {}
        self.calls.append((name, arguments))
        if name == "mock_sign_in":
            return {
                "status": "ok",
                "user": {"user_id": len(FakeMCP.instances), "name": arguments["name"], "email": arguments["email"]},
            }
        if name == "get_cart":
            return {"status": "ok", "cart": self.cart}
        if name == "search_products":
            return {"status": "ok", "count": 0, "groups": []}
        if name == "get_quote":
            return {"status": "ok", "quote": {"product_name": "Paper", "subtotal_jpy": 200}}
        if name == "add_to_cart":
            self.cart = {
                "items": [{"id": 9, "product_name": "Paper", "size_name": "A4", "quantity": 2, "subtotal_jpy": 200}],
                "item_count": 1,
                "total_jpy": 200,
            }
            return {"status": "ok", "cart": self.cart}
        if name == "remove_cart_item":
            self.cart = dict(EMPTY_CART)
            return {"status": "ok", "cart": self.cart}
        if name == "prepare_order":
            if not self.cart["items"]:
                return {"status": "error", "error": {"code": "cart_empty", "message": "Cart empty"}}
            return {
                "status": "confirmation_required",
                "cart": self.cart,
                "confirmation": {"token": "confirm-token", "shipping_address": arguments["shipping_address"], "expires_at": "2099-01-01T00:00:00Z"},
            }
        if name == "place_order":
            if arguments["confirmation_token"] != "confirm-token":
                return {"status": "error", "error": {"code": "invalid_confirmation", "message": "Invalid"}}
            if arguments["decision"] == "reject":
                return {"status": "ok", "decision": "reject", "order": None}
            return {
                "status": "ok",
                "decision": "approve",
                "order": {"order_number": "RKS-1", "total_jpy": 200},
            }
        raise AssertionError(f"Unexpected tool {name}")


class ScriptedAgent(OllamaAgent):
    def __init__(self, rounds):
        super().__init__(None, "http://ollama", "test", max_rounds=6, max_tool_calls=8)
        self.rounds = iter(rounds)

    async def _round(self, messages, tools):
        for chunk in next(self.rounds):
            yield chunk


class EchoAgent:
    async def events(self, state, message):
        yield {"type": "assistant_delta", "text": f"Echo: {message}"}
        yield {"type": "done"}


class FakeHTTPResponse:
    def __init__(self, status_code=200, content=b"image", content_type="image/jpeg"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type, "cache-control": "public, max-age=60"}


class FakeHTTP:
    async def get(self, url, **kwargs):
        if url.endswith("missing.jpg"):
            return FakeHTTPResponse(404)
        if url.endswith("/healthz") or url.endswith("/api/tags"):
            return FakeHTTPResponse(200, b"{}", "application/json")
        return FakeHTTPResponse()


def settings():
    return ChatSettings(
        project_root=Path.cwd(),
        stockroom_api_url="http://127.0.0.1:8080",
        ollama_url="http://127.0.0.1:11434",
        ollama_model="qwen3:8b",
        host="127.0.0.1",
        port=3000,
        session_ttl_seconds=86400,
    )


def test_mcp_tool_conversion_hides_identity_ui_and_order_decision():
    tools = [
        SimpleNamespace(name=name, description=f"{name} description", title=name, inputSchema={"type": "object"})
        for name in [*MODEL_BLOCKED_TOOLS, "search_products", "add_to_cart"]
    ]
    converted = ollama_tools(tools)
    names = {item["function"]["name"] for item in converted}
    assert names == {"search_products", "add_to_cart"}
    assert converted[0]["function"]["parameters"] == {"type": "object"}


<<<<<<< Updated upstream
=======
def test_model_payload_keeps_product_facts_but_removes_ui_images_and_token():
    payload = {
        "status": "ok",
        "groups": [{"products": [{"id": 9, "name": "Paper", "images": ["http://127.0.0.1/image.jpg"]}]}],
        "confirmation": {"token": "secret", "shipping_address": "Tokyo"},
    }

    compact = model_payload(payload)

    assert compact["groups"][0]["products"][0] == {"id": 9, "name": "Paper"}
    assert compact["confirmation"] == {"shipping_address": "Tokyo"}


>>>>>>> Stashed changes
def test_ollama_agent_runs_mcp_tool_loop_and_returns_text():
    async def scenario():
        mcp = FakeMCP(Path.cwd(), "http://127.0.0.1:8080")
        now = utcnow()
        state = ChatSession("token", mcp, now, now)
        agent = ScriptedAgent(
            [
                [{"message": {"tool_calls": [{"function": {"name": "search_products", "arguments": {"q": "paper"}}}]}}],
                [{"message": {"content": "I found the current catalog results."}}],
            ]
        )
        events = [event async for event in agent.events(state, "Find paper")]
        assert mcp.calls == [("search_products", {"q": "paper"})]
        assert any(event["type"] == "tool_result" for event in events)
        assert "I found" in "".join(event.get("text", "") for event in events)
        assert state.messages[-1]["role"] == "assistant"

    asyncio.run(scenario())


def test_ollama_agent_rejects_unknown_tool_without_calling_mcp():
    async def scenario():
        mcp = FakeMCP(Path.cwd(), "http://127.0.0.1:8080")
        now = utcnow()
        state = ChatSession("token", mcp, now, now)
        agent = ScriptedAgent(
            [
                [{"message": {"tool_calls": [{"function": {"name": "place_order", "arguments": {}}}]}}],
                [{"message": {"content": "Please use the confirmation buttons."}}],
            ]
        )
        events = [event async for event in agent.events(state, "Buy now")]
        denied = next(event for event in events if event["type"] == "tool_result")
        assert denied["result"]["error"]["code"] == "tool_not_allowed"
        assert mcp.calls == []

    asyncio.run(scenario())


def test_ollama_agent_enforces_tool_call_limit():
    async def scenario():
        mcp = FakeMCP(Path.cwd(), "http://127.0.0.1:8080")
        now = utcnow()
        state = ChatSession("token", mcp, now, now)
        agent = ScriptedAgent(
            [[{"message": {"tool_calls": [
                {"function": {"name": "search_products", "arguments": {}}},
                {"function": {"name": "search_products", "arguments": {}}},
            ]}}]]
        )
        agent.max_tool_calls = 1
        with pytest.raises(RuntimeError, match="maximum number of tool calls"):
            _ = [event async for event in agent.events(state, "Search repeatedly")]
        assert len(mcp.calls) == 1

    asyncio.run(scenario())


def test_session_store_isolates_mcp_connections_and_closes_them():
    async def scenario():
        FakeMCP.instances.clear()
        store = SessionStore(
            project_root=Path.cwd(),
            api_url="http://127.0.0.1:8080",
            ttl_seconds=86400,
            mcp_factory=FakeMCP,
        )
        first, second = await store.create(), await store.create()
        first.user = {"user_id": 1}
        second.user = {"user_id": 2}
        assert first.token != second.token
        assert first.mcp is not second.mcp
        await store.delete(first.token)
        assert first.mcp.closed is True
        assert await store.get(second.token) is second
        await store.close()
        assert second.mcp.closed is True

    asyncio.run(scenario())


def test_http_login_cart_confirmation_gate_and_session_isolation():
    from fastapi.testclient import TestClient

    FakeMCP.instances.clear()
    app = create_app(settings(), mcp_factory=FakeMCP, http_client=FakeHTTP(), agent=EchoAgent())
    with TestClient(app) as client:
        first = client.post("/api/session/login", json={"name": "Alice", "email": "alice@example.com"})
        assert first.status_code == 200
        token_one = client.cookies.get(COOKIE_NAME)

        client.cookies.clear()
        second = client.post("/api/session/login", json={"name": "Bob", "email": "bob@example.com"})
        assert second.status_code == 200
        token_two = client.cookies.get(COOKIE_NAME)
        assert token_one != token_two

        own = client.get("/api/session").json()
        assert own["user"]["email"] == "bob@example.com"
        other = client.get("/api/session", cookies={COOKIE_NAME: token_one}).json()
        assert other["user"]["email"] == "alice@example.com"

        chat = client.post("/api/chat", json={"message": "hello"})
        assert chat.status_code == 200
        assert "event: assistant_delta" in chat.text
        assert "Echo: hello" in chat.text

        missing_review = client.post("/api/order/decision", json={"decision": "approve"})
        assert missing_review.status_code == 409

        added = client.post("/api/cart/items", json={"product_id": 1, "size_id": 2, "quantity": 2})
        assert added.status_code == 200
        prepared = client.post("/api/order/prepare", json={"shipping_address": "Tokyo"})
        assert prepared.status_code == 200
        assert "token" not in prepared.json()["confirmation"]
        approved = client.post("/api/order/decision", json={"decision": "approve"})
        assert approved.json()["order"]["order_number"] == "RKS-1"
        assert FakeMCP.instances[-1].calls[-1] == (
            "place_order", {"confirmation_token": "confirm-token", "decision": "approve"}
        )


def test_media_path_validation_and_proxy():
    from fastapi.testclient import TestClient

    assert _valid_media_path("products/1/image.jpg") is True
    assert _valid_media_path("products/../secret") is False
    assert _valid_media_path("other/image.jpg") is False

    app = create_app(settings(), mcp_factory=FakeMCP, http_client=FakeHTTP(), agent=EchoAgent())
    with TestClient(app) as client:
        image = client.get("/media/products/1/image.jpg")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/jpeg"
        assert image.content == b"image"
        assert client.get("/media/products/1/missing.jpg").status_code == 404
        assert client.get("/media/other/image.jpg").status_code == 404
