# chat-ui

React SPA for the local Ollama shopping chat. Replaces the three hand-written
files (`index.html`, `app.js`, `styles.css`) that the Python chat service used
to serve from `app/chat_app/static/`.

```bash
npm install
npm run dev      # 127.0.0.1:5174, proxies to the chat service on :3002
npm run build    # tsc -b && vite build -> dist/
```

`docker compose up -d chat-ui` serves the built bundle from nginx on
<http://127.0.0.1:3004>.

## Why it is its own service

The chat service is now JSON and SSE only. nginx holds the single origin the
browser sees and proxies `/api`, `/media` and `/healthz` to `chat:3002`, the
same shape `web` → `api` already has. One origin matters twice here: the
session cookie is host-only, and product images arrive as relative `/media/...`
paths inside MCP tool results.

**`proxy_buffering off` in [nginx.conf](nginx.conf) is load-bearing.** `POST
/api/chat` is a Server-Sent Events stream; with buffering on, nginx would hold
the whole model response and the answer would land in one lump instead of
streaming token by token. `proxy_read_timeout` is 900s for the same reason — a
local model on CPU is slow.

## Layout

| Path | What |
|---|---|
| `src/App.tsx` | All session and conversation state; owns the SSE event handler |
| `src/lib/api.ts` | Typed calls to the chat service, plus `yen()` and `mediaUrl()` |
| `src/lib/sse.ts` | Frame parser — `EventSource` cannot POST, so the body stream is read by hand |
| `src/lib/transcript.ts` | The `Entry` union the message list renders, and the stored-message → `Entry` mapping |
| `src/components/` | Login, message list, product grid, cart, checkout |

`mediaUrl()` keeps only same-origin `/media/products/...` paths. Product text is
crawled from a live site, so an absolute URL arriving in an image field must
never become an `<img src>` pointing off this origin.

## Chat history

The transcript is persisted per demo user and restored on sign-in, so a
`docker compose restart chat` no longer loses the conversation. It is stored in
Postgres through the Go API (`/api/v1/chat/messages`) — `backend-ops` remains
the only process that touches SQL.

Stored `tool` rows keep the structured MCP result in a `payload` column, which
is what lets `entriesFromStored` re-render product cards after a reload rather
than showing a bare "used a tool" note.

**New chat** (`DELETE /api/chat/messages`) clears both the stored transcript and
the model's context.
