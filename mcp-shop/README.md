# mcp-shop

The **commerce** MCP server: search, quote, cart, and the confirm-gated mock
checkout. Sibling of [mcp-ops/](../mcp-ops/), which is the read-only admin
server — the boundary between "read the shop" and "change the shop" is
deliberate and stays.

It was `app/mcp_server/`, welded to the chat host by `PYTHONPATH` and spawned
as a subprocess per browser session. It is now one shared service that every
host connects to: the local chat, Claude Desktop, ChatGPT.

```bash
docker compose up -d shopping-mcp      # 127.0.0.1:3003/mcp
docker compose --profile test run --rm test-mcp-shop
```

## Per-session identity

Carts, quotes and confirmations are keyed on `owner(ctx)` in
[server.py](stockroom_shop/server.py), one key per MCP session.

That used to be `str(id(ctx.session))`. A memory address is recycled once a
session is collected, so a new session could land on a dead one's key and
inherit its signed-in user and pending confirmations. A subprocess per session
hid it; one shared server does not. It is now a `secrets` token held in a
`WeakKeyDictionary`, with a finalizer that drops the session's commerce state
when the session goes.

## The View

`views/` is not a second app: the View runs in the host's sandboxed iframe, so
it is browser code whatever the server is written in. React + Mantine, matching
`frontend-ops`, `chat-ui` and the `mcp-ops` Views.

```bash
cd views && npm ci && npm run build     # -> views/dist/storefront.html
```

`vite-plugin-singlefile` inlines everything into one HTML file because the
iframe CSP is deny-by-default — there is no origin to fetch a second file from.
The build keeps `cssCodeSplit: true`: the plugin's recommended config turns it
off, which makes vite inject the stylesheet from JavaScript at runtime, and a
real `<style>` tag needs no script to have run first.

`storefront_widget.py` only locates the built file. It used to be a 457-line
raw string — no highlighting, no typecheck, no bundler.

```
src/
  lib/       mcp.ts (App bridge + tool calls), theme.ts
  views/     Storefront.tsx
  entries/   storefront.tsx
```

The MCP Apps protocol is the official `@modelcontextprotocol/ext-apps` `App`
client's job, not ours: the ui/initialize handshake, capability negotiation,
JSON-RPC framing, auto-resize, teardown. That was ~120 hand-written lines whose
capability negotiation had already been wrong once.

## The confirm gate

`place_order` is withheld from the model — `MODEL_BLOCKED_TOOLS` in
[chat-host](../chat-host/stockroom_chat/mcp_client.py) — and reachable only
from the Approve / Reject buttons on the confirmation card. The Go service does
not enforce this and cannot: it cannot see which caller invoked the endpoint.
