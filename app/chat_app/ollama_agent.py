from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.chat_app.sessions import ChatSession, public_payload


class AgentLimitError(RuntimeError):
    pass


class OllamaAgent:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        *,
        max_rounds: int = 6,
        max_tool_calls: int = 8,
    ):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_rounds = max_rounds
        self.max_tool_calls = max_tool_calls

    async def _round(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": True,
            "think": False,
        }
        try:
            async with self.client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode(errors="replace")[:500]
                    raise RuntimeError(
                        f"Ollama returned HTTP {response.status_code}: {detail}"
                    )
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    yield json.loads(line)
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Ollama is unavailable at {self.base_url}. Start Ollama and pull {self.model}."
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned an invalid streaming response.") from exc

    async def events(
        self, state: ChatSession, user_message: str
    ) -> AsyncIterator[dict[str, Any]]:
        state.messages.append({"role": "user", "content": user_message})
        self._trim_history(state)
        tool_count = 0

        for _ in range(self.max_rounds):
            content = ""
            tool_calls: list[dict[str, Any]] = []
            async for chunk in self._round(state.messages, state.mcp.model_tools):
                message = chunk.get("message") or {}
                delta = message.get("content") or ""
                if delta:
                    content += delta
                    yield {"type": "assistant_delta", "text": delta}
                calls = message.get("tool_calls") or []
                if isinstance(calls, list):
                    tool_calls.extend(call for call in calls if isinstance(call, dict))

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": content,
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            state.messages.append(assistant_message)

            if not tool_calls:
                if not content:
                    fallback = "I could not produce a response. Please try again."
                    state.messages[-1]["content"] = fallback
                    yield {"type": "assistant_delta", "text": fallback}
                yield {"type": "done"}
                return

            for call in tool_calls:
                tool_count += 1
                if tool_count > self.max_tool_calls:
                    raise AgentLimitError("The request exceeded the maximum number of tool calls.")

                function = call.get("function") or {}
                name = function.get("name")
                arguments = function.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                yield {"type": "tool_started", "tool": name or "unknown"}
                if name not in state.mcp.allowed_model_tools:
                    result = {
                        "status": "error",
                        "error": {
                            "code": "tool_not_allowed",
                            "message": f"Tool {name!r} is not available to the model.",
                        },
                    }
                elif not isinstance(arguments, dict):
                    result = {
                        "status": "error",
                        "error": {
                            "code": "invalid_tool_arguments",
                            "message": "Tool arguments must be an object.",
                        },
                    }
                else:
                    result = await state.mcp.call(name, arguments)
                    state.ingest(result, name)

                visible_result = public_payload(result)
                yield {"type": "tool_result", "tool": name, "result": visible_result}
                state.messages.append(
                    {
                        "role": "tool",
                        "tool_name": name or "unknown",
                        "content": json.dumps(visible_result, ensure_ascii=False),
                    }
                )

        raise AgentLimitError("The request exceeded the maximum number of model rounds.")

    @staticmethod
    def _trim_history(state: ChatSession) -> None:
        if len(state.messages) <= 51:
            return
        state.messages[:] = [state.messages[0], *state.messages[-50:]]
