from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


<<<<<<< Updated upstream
MODEL_BLOCKED_TOOLS = {"mock_sign_in", "sign_out", "open_storefront", "place_order"}
=======
MODEL_BLOCKED_TOOLS = {"mock_sign_in", "place_order"}
>>>>>>> Stashed changes


def ollama_tools(tools: list[Any]) -> list[dict[str, Any]]:
    """Translate MCP tool definitions to Ollama function-tool schemas."""
    output: list[dict[str, Any]] = []
    for tool in tools:
        if tool.name in MODEL_BLOCKED_TOOLS:
            continue
        output.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or tool.title or tool.name,
                    "parameters": tool.inputSchema,
                },
            }
        )
    return output


def result_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {"status": "error", "error": {"code": "invalid_tool_result", "message": "MCP tool returned no structured object."}}


class StockroomMCPConnection:
    """One MCP session against the shared commerce server (`mcp-shop`).

    This used to spawn `python -m stockroom_shop.server` over stdio, one
    subprocess per browser session. It now connects over streamable-http to the
    same running server Claude Desktop and ChatGPT use, so there is one MCP
    server rather than one per chat session plus a service nobody called.

    Commands are still funnelled through a single worker task: the MCP client
    session is not safe to drive from several tasks at once, and the async
    context managers must be entered and exited on the same task.
    """

    def __init__(self, mcp_url: str):
        self.mcp_url = mcp_url
        self._commands: asyncio.Queue[Any] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._ready: asyncio.Future | None = None
        self.model_tools: list[dict[str, Any]] = []
        self.allowed_model_tools: set[str] = set()
        self.tools: dict[str, Any] = {}

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        loop = asyncio.get_running_loop()
        self._ready = loop.create_future()
        self._worker_task = asyncio.create_task(self._run(), name="stockroom-mcp-session")
        await self._ready

    async def _run(self) -> None:
        try:
            # The third yielded value is a session-id callback we do not need.
            async with streamablehttp_client(self.mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self.tools = {tool.name: tool for tool in listed.tools}
                    self.model_tools = ollama_tools(listed.tools)
                    self.allowed_model_tools = {
                        item["function"]["name"] for item in self.model_tools
                    }
                    if self._ready and not self._ready.done():
                        self._ready.set_result(None)

                    while True:
                        command = await self._commands.get()
                        if command is None:
                            break
                        name, arguments, future = command
                        try:
                            if name == "__read_resource":
                                raw = await session.read_resource(arguments["uri"])
                                payload = raw.model_dump(by_alias=True, mode="json", exclude_none=True)
                            else:
                                raw = await session.call_tool(name, arguments)
                                payload = result_payload(raw)
                                payload = dict(payload)
                                payload["_mcp_result"] = raw.model_dump(by_alias=True, mode="json", exclude_none=True)
                            if getattr(raw, "isError", False) and payload.get("status") != "error":
                                payload = {
                                    "status": "error",
                                    "error": {"code": "mcp_error", "message": "MCP server reported a tool error."},
                                }
                            if not future.done():
                                future.set_result(payload)
                        except asyncio.CancelledError:
                            future.cancel()
                            raise
                        except Exception as exc:
                            if not future.done():
                                future.set_exception(exc)
        except BaseException as exc:
            if self._ready and not self._ready.done():
                self._ready.set_exception(exc)
            while not self._commands.empty():
                command = self._commands.get_nowait()
                if command is not None and not command[2].done():
                    command[2].set_exception(exc)
            if isinstance(exc, asyncio.CancelledError):
                raise

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        task = self._worker_task
        if task is None or task.done():
            raise RuntimeError("MCP connection is not started")
        future = asyncio.get_running_loop().create_future()
        await self._commands.put((name, arguments or {}, future))
        done, _ = await asyncio.wait({future, task}, return_when=asyncio.FIRST_COMPLETED)
        if future in done:
            return future.result()
        raise RuntimeError("MCP connection stopped unexpectedly")

    async def close(self) -> None:
        task = self._worker_task
        self._worker_task = None
        if task is None:
            return
        if not task.done():
            await self._commands.put(None)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except asyncio.TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
