"""Session-local routing and capabilities for the two configured MCP servers."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import hashlib
import secrets
from typing import Any

from stockroom_chat.mcp_client import StockroomMCPConnection, MODEL_BLOCKED_TOOLS


def clean(value: Any) -> Any:
    """Private commerce capabilities never cross the host boundary."""
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()
                if key not in {"token", "confirmation_token", "admin_name", "admin_email"}}
    return value


def browser_result(payload: dict) -> dict:
    result = clean(payload)
    confirmation = payload.get("confirmation")
    if isinstance(confirmation, dict) and confirmation.get("token"):
        result["confirmation"]["review_id"] = hashlib.sha256(confirmation["token"].encode()).hexdigest()
    raw = result.get("_mcp_result")
    if raw:
        # JSON text blocks can duplicate structured content, including tokens.
        raw["content"] = [{"type": "text", "text": json.dumps(clean({k: v for k, v in payload.items() if not k.startswith('_')}))}]
        if "structuredContent" in raw:
            raw["structuredContent"] = clean(raw["structuredContent"])
    return result


def error(message: str, code: str = "mcp_unavailable") -> dict:
    return {"status": "error", "error": {"code": code, "message": message}}


class MCPRouter:
    def __init__(self, shopping_url: str, ops_url: str, factory=StockroomMCPConnection):
        self.connections = {"shop": factory(shopping_url), "ops": factory(ops_url)}
        self.available: set[str] = set()
        self.model_tools: list[dict] = []
        self.allowed_model_tools: set[str] = set()
        self.bindings: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}

    async def start(self):
        results = await asyncio.gather(*(asyncio.wait_for(c.start(), 15) for c in self.connections.values()), return_exceptions=True)
        for server, result in zip(self.connections, results):
            if isinstance(result, BaseException):
                await self.connections[server].close()
                continue
            self.available.add(server)
            for tool in self.connections[server].model_tools:
                item = deepcopy(tool)
                name = item["function"]["name"]
                item["function"]["name"] = f"{server}__{name}"
                self.model_tools.append(item)
                self.allowed_model_tools.add(f"{server}__{name}")
        if "shop" not in self.available:
            await self.close()
            raise RuntimeError("Shopping MCP is unavailable. Check shopping-mcp.")

    async def close(self):
        await asyncio.gather(*(c.close() for c in self.connections.values()), return_exceptions=True)
        self.bindings.clear()
        self.pending.clear()

    def resource_uri(self, server: str, name: str) -> str | None:
        tool = getattr(self.connections[server], "tools", {}).get(name)
        meta = getattr(tool, "meta", None) or getattr(tool, "_meta", None) or {}
        return (meta.get("ui") or {}).get("resourceUri") or meta.get("openai/outputTemplate")

    def decorate(self, server: str, name: str, arguments: dict, payload: dict) -> dict:
        uri = self.resource_uri(server, name)
        if uri and not payload.get("error") and payload.get("status") != "error":
            binding = {"server": server, "tool": name, "uri": uri, "input": clean(arguments)}
            ident = secrets.token_urlsafe(24)
            self.bindings[ident] = binding
            payload["_mcp_app"] = {"id": ident, **binding}
        return payload

    def restore(self, payload: dict):
        app = payload.get("_mcp_app")
        if not isinstance(app, dict):
            return
        server, name = app.get("server"), app.get("tool")
        if server not in self.available or self.resource_uri(server, name) != app.get("uri"):
            payload.pop("_mcp_app", None)
            return
        self.decorate(server, name, app.get("input", {}), payload)

    async def call(self, name: str, arguments: dict | None = None):
        server, tool = name.split("__", 1) if "__" in name else ("shop", name)
        if server not in self.available:
            return error(f"{server} MCP is unavailable. Check its Docker service.")
        arguments = dict(arguments or {})
        if server == "ops":
            # The model cannot supply or reuse an identity. The user fills a
            # fresh host-owned form for this particular invocation.
            ident = secrets.token_urlsafe(24)
            self.pending[ident] = {"server": server, "tool": tool, "arguments": clean(arguments)}
            return {"status": "identity_required", "_ops_request": {"id": ident, "tool": tool},
                    "message": "Enter your admin name and email in the form to run this request."}
        return await self.execute(server, tool, arguments)

    async def execute(self, server: str, tool: str, arguments: dict):
        try:
            payload = await self.connections[server].call(tool, arguments)
        except Exception as exc:
            return error(f"{server} MCP call failed: {exc}")
        return self.decorate(server, tool, arguments, payload)

    async def resource(self, ident: str):
        binding = self.bindings[ident]
        return await self.connections[binding["server"]].call("__read_resource", {"uri": binding["uri"]})

    async def app_call(self, ident: str, name: str, arguments: dict, identity: dict | None):
        binding = self.bindings[ident]
        server = binding["server"]
        connection = self.connections[server]
        if "__" in name or name in MODEL_BLOCKED_TOOLS or name not in getattr(connection, "tools", {}):
            return error("This tool is not available to this app.", "tool_not_allowed")
        args = clean(arguments)
        if server == "ops":
            if not identity or not identity.get("name", "").strip() or not identity.get("email", "").strip():
                return error("Enter admin name and email for this action.", "identity_required")
            args.update(admin_name=identity["name"].strip(), admin_email=identity["email"].strip())
        return await self.execute(server, name, args)
