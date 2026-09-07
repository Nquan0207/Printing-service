from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path, PurePosixPath
from typing import Any, AsyncIterator
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, Field
import uvicorn

from app.chat_app.config import ChatSettings
from app.chat_app.mcp_client import StockroomMCPConnection
from app.chat_app.ollama_agent import OllamaAgent
from app.chat_app.sessions import ChatSession, SessionStore, public_payload


COOKIE_NAME = "stockroom_chat_session"
STATIC_DIR = Path(__file__).with_name("static")


class LoginRequest(BaseModel):
    name: str = Field(default="", max_length=100)
    email: str = Field(min_length=3, max_length=320)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class AddCartItemRequest(BaseModel):
    product_id: int = Field(gt=0)
    size_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)


class PrepareOrderRequest(BaseModel):
    shipping_address: str = Field(min_length=1, max_length=500)


class DecisionRequest(BaseModel):
    decision: str


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
            project_root=config.project_root,
            api_url=config.stockroom_api_url,
            ttl_seconds=config.session_ttl_seconds,
            max_sessions=config.max_sessions,
            mcp_factory=mcp_factory,
        )
        chat_agent = agent or OllamaAgent(
            client,
            config.ollama_url,
            config.ollama_model,
            max_rounds=config.max_model_rounds,
            max_tool_calls=config.max_tool_calls,
        )
        app.state.http = client
        app.state.sessions = store
        app.state.agent = chat_agent
        try:
            yield
        finally:
            if owns_store:
                await store.close()
            if owns_http:
                await client.aclose()

    app = FastAPI(title="Stockroom Ollama Chat", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    async def current_session(request: Request) -> ChatSession:
        state = await request.app.state.sessions.get(request.cookies.get(COOKIE_NAME))
        if state is None or state.user is None:
            raise HTTPException(401, "Demo sign-in is required.")
        return state

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

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
        response.set_cookie(
            COOKIE_NAME,
            state.token,
            max_age=config.session_ttl_seconds,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )
        return {"authenticated": True, "user": state.user, "cart": state.cart}

    @app.get("/api/session")
    async def session_info(request: Request):
        state = await request.app.state.sessions.get(request.cookies.get(COOKIE_NAME))
        if state is None or state.user is None:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "user": state.user,
            "cart": state.cart,
            "confirmation": public_payload({"confirmation": state.confirmation})["confirmation"],
            "confirmation_decision": state.confirmation_decision,
            "order": state.order,
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

        async def stream() -> AsyncIterator[str]:
            try:
                async with state.lock:
                    async for event in request.app.state.agent.events(state, user_message):
                        yield _sse(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield _sse({"type": "error", "message": str(exc)})

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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
            return {"status": "ok", "quote": quote_result.get("quote"), "cart": state.cart}

    @app.delete("/api/cart/items/{item_id}")
    async def remove_cart_item(item_id: int, request: Request):
        if item_id <= 0:
            raise HTTPException(400, "item_id must be positive.")
        state = await current_session(request)
        async with state.lock:
            result = _require_success(await state.mcp.call("remove_cart_item", {"item_id": item_id}))
            state.ingest(result, "remove_cart_item")
            return result

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
            return result

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
        async def check(url: str):
            try:
                response = await request.app.state.http.get(url, timeout=3.0)
                return "ok" if response.status_code == 200 else "error"
            except httpx.RequestError:
                return "error"

        stockroom, ollama = await asyncio.gather(
            check(f"{config.stockroom_api_url}/healthz"),
            check(f"{config.ollama_url}/api/tags"),
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
