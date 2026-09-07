# chat-host

The MCP **host** for the local Ollama chat: it owns the model loop, the browser
session and the SSE stream. It was `app/chat_app/`.

```bash
docker compose up -d chat              # 127.0.0.1:3002
docker compose --profile test run --rm test-chat-host
```

It serves **no HTML**. The browser UI is [chat-ui/](../chat-ui/), a separate
React service behind nginx — the same shape as `frontend-ops` → `api`.

## It is a client, not a parent

This used to spawn `python -m app.mcp_server.server` over stdio, one subprocess
per browser session, while a `shopping-mcp` service ran alongside serving
nobody. It now connects to that service over streamable-http:

```
Prompt → Ollama → chat-host → shopping-mcp → Go API → Postgres
```

`SHOPPING_MCP_URL` points at it (`http://shopping-mcp:3003` in compose). One
MCP server, many hosts.

Commands still funnel through a single worker task in
[mcp_client.py](stockroom_chat/mcp_client.py): the MCP client session is not
safe to drive from several tasks at once, and its async context managers must
be entered and exited on the same task.

## Chat history

Persisted per demo user and restored on sign-in, so restarting this service no
longer loses the conversation. It is written through the **Go API**
(`/api/v1/chat/messages`), never by this process directly — `backend-ops` stays
the only thing that touches SQL.

Writes are best-effort by design: if the endpoint is unreachable the chat still
answers and logs a warning.

Replayed history gives the model prose only. Ollama requires a `tool` message
to follow the assistant message carrying the matching `tool_calls`, and those
ids do not survive a restart — see `model_messages` in
[history.py](stockroom_chat/history.py). The browser still re-renders cards
from the stored `payload` column.
