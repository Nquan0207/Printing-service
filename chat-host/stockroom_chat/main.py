from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import PurePosixPath
from typing import Any, AsyncIterator
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from pydantic import BaseModel, Field
import uvicorn

from stockroom_chat.config import ChatSettings
from stockroom_chat.apps import MCPRouter
from stockroom_chat.history import ChatHistory, model_messages
from stockroom_chat.mcp_client import StockroomMCPConnection
from stockroom_chat.ollama_agent import OllamaAgent
from stockroom_chat.sessions import SYSTEM_PROMPT, ChatSession, SessionStore, public_payload, model_payload


COOKIE_NAME = "stockroom_chat_session"


class LoginRequest(BaseModel):
    name: str = Field(default="", max_length=100)
    email: str = Field(min_length=3, max_length=320)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AppToolRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    identity: dict[str, str] | None = None


class AddCartItemRequest(BaseModel):
    product_id: int = Field(gt=0)
    size_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)


class PrepareOrderRequest(BaseModel):
    shipping_address: str = Field(min_length=1, max_length=500)


class DecisionRequest(BaseModel):
    decision: str
    review_id: str | None = None


def _error_status(payload: dict[str, Any]) -> int:
    code = (payload.get("error") or {}).get("code")
    if code in {"invalid_request", "invalid_decision"}:
        return 400
    if code in {"invalid_confirmation"}:
        return 403
    if code in {"product_not_found", "order_not_found"}:
        return 404
    if code in {"cart_empty", "cart_changed", "confirmation_expired", "decision_conflict"}:
        return 409
    if code == "backend_unavailable":
        return 503
    return 502


def _require_success(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") == "error":
        error = payload.get("error") or {}
        raise HTTPException(_error_status(payload), error.get("message", "Stockroom operation failed."))
    return payload


def _sse(event: dict[str, Any]) -> str:
    kind = event.get("type", "message")
    body = {key: value for key, value in event.items() if key != "type"}
    return f"event: {kind}\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"


def _valid_media_path(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/"):
        return False
    path = PurePosixPath(value)
    return path.parts[0] == "products" and all(part not in {"", ".", ".."} for part in path.parts)


def create_app(
    settings: ChatSettings | None = None,
    *,
    mcp_factory=StockroomMCPConnection,
    session_store: SessionStore | None = None,
    http_client: httpx.AsyncClient | None = None,
    agent: OllamaAgent | None = None,
) -> FastAPI:
    config = settings or ChatSettings.from_env()
    owns_http = http_client is None
    owns_store = session_store is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False
        )
        store = session_store or SessionStore(
            mcp_url=config.shopping_mcp_url,
            ttl_seconds=config.session_ttl_seconds,
            max_sessions=config.max_sessions,
            mcp_factory=(lambda url: MCPRouter(url, config.ops_mcp_url)) if mcp_factory is StockroomMCPConnection else mcp_factory,
        )
        chat_agent = agent or OllamaAgent(
            client,
            config.ollama_url,
            config.ollama_model,
            max_rounds=config.max_model_rounds,
            max_tool_calls=config.max_tool_calls,
            timeout_seconds=config.ollama_timeout_seconds,
        )
        app.state.http = client
        app.state.sessions = store
        app.state.agent = chat_agent
        app.state.history = ChatHistory(client, config.stockroom_api_url)
        try:
            yield
        finally:
            if owns_store:
                await store.close()
            if owns_http:
                await client.aclose()

    # No static files: the UI is a separate React service (chat-ui/) that
    # proxies here, so this process serves JSON and the SSE stream only.
    app = FastAPI(title="Stockroom Ollama Chat", lifespan=lifespan)

    async def current_session(request: Request) -> ChatSession:
        state = await request.app.state.sessions.get(request.cookies.get(COOKIE_NAME))
        if state is None or state.user is None:
            raise HTTPException(401, "Demo sign-in is required.")
        return state

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        # The sandbox shares a hostname but not an origin. Cookies must not
        # let embedded code call host mutation endpoints directly.
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
                return JSONResponse({"detail": "Cross-origin writes are not allowed."}, status_code=403)
        return await call_next(request)

    @app.post("/api/session/login")
    async def login(body: LoginRequest, request: Request, response: Response):
        previous = request.cookies.get(COOKIE_NAME)
        if previous:
            await request.app.state.sessions.delete(previous)
        try:
            state = await request.app.state.sessions.create()
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        try:
            async with state.lock:
                signed_in = _require_success(
                    await state.mcp.call(
                        "mock_sign_in", {"name": body.name.strip(), "email": body.email.strip()}
                    )
                )
                state.ingest(signed_in, "mock_sign_in")
                cart = _require_success(await state.mcp.call("get_cart"))
                state.ingest(cart, "get_cart")
        except BaseException:
            await request.app.state.sessions.delete(state.token)
            raise
        # Resume: the browser re-renders the whole transcript, while the model
        # gets only the prose (see history.model_messages for why).
        transcript = []
        if state.user_id is not None:
            transcript = await request.app.state.history.load(state.user_id)
            if isinstance(state.mcp, MCPRouter):
                for row in transcript:
                    if isinstance(row.get("payload"), dict):
                        state.mcp.restore(row["payload"])
            state.messages = model_messages(SYSTEM_PROMPT, transcript)
        response.set_cookie(
            COOKIE_NAME,
            state.token,
            max_age=config.session_ttl_seconds,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )
        return {
            "authenticated": True,
            "user": state.user,
            "cart": state.cart,
            "transcript": transcript,
        }

    @app.get("/api/session")
    async def session_info(request: Request):
        state = await request.app.state.sessions.get(request.cookies.get(COOKIE_NAME))
        if state is None or state.user is None:
            return {"authenticated": False}
        transcript = []
        if state.user_id is not None:
            transcript = await request.app.state.history.load(state.user_id)
            if isinstance(state.mcp, MCPRouter):
                for row in transcript:
                    if isinstance(row.get("payload"), dict):
                        state.mcp.restore(row["payload"])
        return {
            "authenticated": True,
            "user": state.user,
            "cart": state.cart,
            "confirmation": public_payload({"confirmation": state.confirmation})["confirmation"],
            "confirmation_decision": state.confirmation_decision,
            "order": state.order,
            "transcript": transcript,
        }

    @app.delete("/api/session")
    async def logout(request: Request, response: Response):
        await request.app.state.sessions.delete(request.cookies.get(COOKIE_NAME))
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"status": "ok"}

    @app.post("/api/chat")
    async def chat(body: ChatRequest, request: Request):
        state = await current_session(request)
        user_message = body.message.strip()
        if not user_message:
            raise HTTPException(400, "message cannot be blank.")

        history = request.app.state.history
        user_id = state.user_id

        async def stream() -> AsyncIterator[str]:
            # Written as the conversation happens, not at the end: if the model
            # stalls or the browser disconnects, whatever the user already saw
            # is still in Postgres.
            if user_id is not None:
                await history.append(user_id, "user", user_message)
            pending: list[str] = []

            async def flush_assistant() -> None:
                text = "".join(pending).strip()
                pending.clear()
                if text and user_id is not None:
                    await history.append(user_id, "assistant", text)

            try:
                async with state.lock:
                    async for event in request.app.state.agent.events(state, user_message):
                        kind = event.get("type")
                        if kind == "assistant_delta":
                            pending.append(event.get("text") or "")
                        elif kind == "tool_started":
                            # An assistant turn ends when it calls a tool.
                            await flush_assistant()
                        elif kind == "tool_result" and user_id is not None:
                            tool = event.get("tool") or "unknown"
                            await history.append(
                                user_id,
                                "tool",
                                f"Using MCP tool: {tool}",
                                tool_name=tool,
                                payload=event.get("result"),
                            )
                        elif kind == "done":
                            await flush_assistant()
                        yield _sse(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await flush_assistant()
                message = str(exc)
                if user_id is not None:
                    await history.append(user_id, "assistant", message)
                yield _sse({"type": "error", "message": message})

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.delete("/api/chat/messages")
    async def clear_chat(request: Request):
        """Start a new conversation: forget it in Postgres and in the model."""
        state = await current_session(request)
        async with state.lock:
            if state.user_id is not None:
                await request.app.state.history.clear(state.user_id)
            state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if isinstance(state.mcp, MCPRouter):
                state.mcp.bindings.clear()
                state.mcp.pending.clear()
        return {"status": "ok"}

    @app.post("/api/cart/items")
    async def add_cart_item(body: AddCartItemRequest, request: Request):
        state = await current_session(request)
        async with state.lock:
            quote_result = _require_success(
                await state.mcp.call(
                    "get_quote",
                    {"product_id": body.product_id, "size_id": body.size_id, "quantity": body.quantity},
                )
            )
            cart_result = _require_success(
                await state.mcp.call(
                    "add_to_cart",
                    {"product_id": body.product_id, "size_id": body.size_id, "quantity": body.quantity},
                )
            )
            state.ingest(cart_result, "add_to_cart")
            quote = quote_result.get("quote") or {}
            if state.user_id is not None and quote:
                await request.app.state.history.append(
                    state.user_id,
                    "assistant",
                    f"{quote.get('product_name')} added — ¥{quote.get('subtotal_jpy'):,}.",
                )
            return {"status": "ok", "quote": quote_result.get("quote"), "cart": state.cart}

    @app.delete("/api/cart/items/{item_id}")
    async def remove_cart_item(item_id: int, request: Request):
        if item_id <= 0:
            raise HTTPException(400, "item_id must be positive.")
        state = await current_session(request)
        async with state.lock:
            result = _require_success(await state.mcp.call("remove_cart_item", {"item_id": item_id}))
            state.ingest(result, "remove_cart_item")
            return public_payload(result)

    @app.post("/api/order/prepare")
    async def prepare_order(body: PrepareOrderRequest, request: Request):
        state = await current_session(request)
        async with state.lock:
            result = _require_success(
                await state.mcp.call(
                    "prepare_order", {"shipping_address": body.shipping_address.strip()}
                )
            )
            state.ingest(result, "prepare_order")
            return public_payload(result)

    @app.post("/api/order/decision")
    async def decide_order(body: DecisionRequest, request: Request):
        state = await current_session(request)
        decision = body.decision.strip().lower()
        if decision not in {"approve", "reject"}:
            raise HTTPException(400, "decision must be approve or reject.")
        async with state.lock:
            if not state.confirmation:
                raise HTTPException(409, "Prepare and review the cart before deciding.")
            if body.review_id is not None and body.review_id != public_payload({"confirmation": state.confirmation})["confirmation"].get("review_id"):
                raise HTTPException(409, "The checkout review changed. Review the current order again.")
            result = _require_success(
                await state.mcp.call(
                    "place_order",
                    {"confirmation_token": state.confirmation["token"], "decision": decision},
                )
            )
            state.ingest(result, "place_order")
            state.confirmation_decision = decision
            if decision == "approve":
                state.cart = {"items": [], "item_count": 0, "total_jpy": 0}
            if state.user_id is not None:
                order = result.get("order") or {}
                note = (
                    f"Mock order {order.get('order_number')} confirmed. No money moved."
                    if decision == "approve"
                    else "Mock order rejected. Your cart was preserved."
                )
                await request.app.state.history.append(state.user_id, "assistant", note)
            return public_payload(result)

    async def app_session(request: Request):
        state = await current_session(request)
        if not isinstance(state.mcp, MCPRouter):
            raise HTTPException(503, "MCP apps are unavailable.")
        return state

    async def publish_app_result(state, result, tool):
        if tool.startswith("shop__"):
            state.ingest(result, tool)
        visible = public_payload(result)
        state.messages.append({"role": "assistant", "content": f"The user ran {tool} in the app. Result: " + json.dumps(model_payload(result), ensure_ascii=False)})
        if state.user_id is not None:
            await app.state.history.append(state.user_id, "tool", f"Using MCP tool: {tool}", tool_name=tool, payload=visible)
        return visible

    @app.post("/api/apps/identity/{pending_id}")
    async def run_ops(pending_id: str, body: LoginRequest, request: Request):
        state = await app_session(request)
        async with state.lock:
            pending = state.mcp.pending.get(pending_id)
            if pending is None:
                raise HTTPException(410, "This request expired. Ask the assistant again.")
            if not body.name.strip() or not body.email.strip():
                raise HTTPException(400, "Enter both admin name and email.")
            args = {**pending["arguments"], "admin_name": body.name.strip(), "admin_email": body.email.strip()}
            result = await state.mcp.execute("ops", pending["tool"], args)
            if not result.get("error") and result.get("status") != "error":
                state.mcp.pending.pop(pending_id, None)
            return await publish_app_result(state, result, "ops__" + pending["tool"])

    @app.get("/api/apps/{app_id}/resource")
    async def app_resource(app_id: str, request: Request):
        state = await app_session(request)
        if app_id not in state.mcp.bindings:
            raise HTTPException(404, "App expired. Reload the conversation.")
        try:
            return await state.mcp.resource(app_id)
        except Exception as exc:
            raise HTTPException(502, "Unable to load MCP app resource.") from exc

    @app.post("/api/apps/{app_id}/tools")
    async def app_tool(app_id: str, body: AppToolRequest, request: Request):
        state = await app_session(request)
        async with state.lock:
            binding = state.mcp.bindings.get(app_id)
            if binding is None:
                raise HTTPException(404, "App expired. Reload the conversation.")
            result = await state.mcp.app_call(app_id, body.name, body.arguments, body.identity)
            return await publish_app_result(state, result, binding["server"] + "__" + body.name)

    @app.get("/api/apps/{app_id}/sandbox")
    async def app_sandbox(app_id: str, request: Request):
        resource = await app_resource(app_id, request)
        contents = resource.get("contents", [])
        if not contents:
            raise HTTPException(502, "MCP app resource is empty.")
        meta = contents[0].get("_meta", {})
        csp = (meta.get("ui") or {}).get("csp", {})
        def domains(key):
            from urllib.parse import urlsplit
            values = csp.get(key, [])
            return " ".join(value for value in values if isinstance(value, str)
                            and urlsplit(value).scheme in {"http", "https"}
                            and not any(ch.isspace() or ch in ";'\"\\" for ch in value))
        resources = domains("resourceDomains")
        connections = domains("connectDomains")
        policy = ("default-src 'none'; script-src 'self' 'unsafe-inline'; "
                  "style-src 'unsafe-inline'; frame-src 'self'; "
                  f"img-src data: blob: {resources}; font-src data: {resources}; "
                  f"connect-src {connections or chr(39) + 'none' + chr(39)}; "
                  "base-uri 'none'; form-action 'none'")
        return Response('<!doctype html><html><head><meta charset="utf-8"></head>'
                        '<body style="margin:0;height:100vh"><script src="/sandbox.js"></script></body></html>',
                        media_type="text/html", headers={"Content-Security-Policy": policy, "Cache-Control": "no-store"})

    @app.get("/media/{media_path:path}")
    async def media(media_path: str, request: Request):
        if not _valid_media_path(media_path):
            raise HTTPException(404, "Image not found.")
        upstream_url = f"{config.stockroom_api_url}/media/{quote(media_path, safe='/')}"
        try:
            upstream = await request.app.state.http.get(upstream_url)
        except httpx.RequestError as exc:
            raise HTTPException(502, "Stockroom media service is unavailable.") from exc
        if upstream.status_code == 404:
            raise HTTPException(404, "Image not found.")
        if upstream.status_code != 200:
            raise HTTPException(502, "Stockroom media service returned an error.")
        headers = {}
        for name in ("cache-control", "etag"):
            if value := upstream.headers.get(name):
                headers[name] = value
        return Response(
            content=upstream.content,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )

    @app.get("/healthz")
    async def health(request: Request):
        async def check(url: str, model: str | None = None):
            try:
                response = await request.app.state.http.get(url, timeout=3.0)
                if response.status_code != 200:
                    return "error"
                if model is not None:
                    models = response.json().get("models", [])
                    expected = model if ":" in model else model + ":latest"
                    if not any(item.get("name") == expected for item in models):
                        return "model_missing"
                return "ok"
            except (httpx.RequestError, ValueError, TypeError, AttributeError):
                return "error"

        stockroom, ollama = await asyncio.gather(
            check(f"{config.stockroom_api_url}/healthz"),
            check(f"{config.ollama_url}/api/tags", config.ollama_model),
        )
        status = "ok" if stockroom == ollama == "ok" else "degraded"
        return JSONResponse(
            {"status": status, "stockroom_api": stockroom, "ollama": ollama, "model": config.ollama_model},
            status_code=200 if status == "ok" else 503,
        )

    return app


app = create_app()


def main() -> None:
    settings = ChatSettings.from_env()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
