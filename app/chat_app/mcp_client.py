from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MODEL_BLOCKED_TOOLS = {"mock_sign_in", "open_storefront", "place_order"}


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
    def __init__(self, project_root: Path, api_url: str):
        self.project_root = project_root
        self.api_url = api_url
        self._commands: asyncio.Queue[Any] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._ready: asyncio.Future | None = None
        self.model_tools: list[dict[str, Any]] = []
        self.allowed_model_tools: set[str] = set()

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        loop = asyncio.get_running_loop()
        self._ready = loop.create_future()
        self._worker_task = asyncio.create_task(self._run(), name="stockroom-mcp-session")
        await self._ready

    async def _run(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.project_root)
        environment["STOCKROOM_API_URL"] = self.api_url
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server.server"],
            cwd=str(self.project_root),
            env=environment,
        )
        try:
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    listed = await session.list_tools()
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
                            raw = await session.call_tool(name, arguments)
                            payload = result_payload(raw)
                            if getattr(raw, "isError", False) and payload.get("status") != "error":
                                payload = {
                                    "status": "error",
                                    "error": {"code": "mcp_error", "message": str(payload)},
                                }
                            if not future.done():
                                future.set_result(payload)
                        except BaseException as exc:
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
        await task
