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

## Ops and MCP apps

Each browser session owns independent `shop` and `ops` MCP connections. Model
names are `shop__<tool>` and `ops__<tool>`; original names are used on the wire.
`OPS_MCP_URL` is a complete endpoint URL (default
`http://127.0.0.1:3001/mcp`, Compose `http://mcp:3001/mcp`). An ops outage does
not prevent shopping. Sign out and in to rediscover a recovered server.

The host retains tool metadata and MCP results, exposing sanitized results to
the browser and data-only results to Ollama. Session-bound app IDs authorize
resource retrieval and callbacks to the originating server. HTML and identity
fields are not saved in app metadata; confirmation tokens never leave the host.

New authenticated interfaces:

- `GET /api/apps/{id}/resource`: read the bound MCP HTML resource.
- `GET /api/apps/{id}/sandbox`: sandbox document with resource-specific CSP.
- `POST /api/apps/{id}/tools`: `{name, arguments, identity?: {name, email}}`.
  Ops callbacks require fresh identity; sign-in and order placement are excluded.
- `POST /api/apps/identity/{pending_id}`: `{name, email}` executes a pending ops
  request. Incorrect identity can be retried; successful requests are consumed.

SSE `tool_result.result` and persisted tool payloads may include `_mcp_result`,
`_mcp_app` (session ID, server, tool, URI, sanitized input), or `_ops_request`.
Old payloads still render as cards. History loading rebinds saved app descriptors
without rerunning tools. New chat and logout clear live app capabilities.

The storefront shares the host's shopping identity. Switching accounts uses
chat logout/login. Its order action opens a host confirmation dialog and then
uses `/api/order/decision`; generic tool forwarding cannot place orders.
The optional `review_id` field on that endpoint rejects a changed checkout review.

```bash
PYTHONPATH=chat-host python -m pytest chat-host/tests
```
