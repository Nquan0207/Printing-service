# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A PoC for [docs/requirement.md](docs/requirement.md): conversational commerce over MCP Apps.
The catalog is real data crawled from **stockroom.raksul.com** (RAKSUL Business Mall — office
and store supplies, *not* printing), served by a Go API behind a React storefront and admin
dashboard. A read-only **MCP Apps server** exists in `mcp-ops/` (admin ops); the
**commerce** MCP server — the actual demo bar — is still unbuilt.

```
stockroom.raksul.com
        |  crawler/ (Python, offline, run once)
        v
   Postgres + MinIO
        ^
        |  backend-ops/ (Go)  — the only process touching SQL or MinIO
        |
   +----+--------------------+
   |                         |
frontend-ops/ (React)   mcp-ops/ (Python, read-only admin)
   via nginx            commerce MCP server: NOT BUILT
                                |
                        Claude / ChatGPT / custom chat
```

## Run everything

Full setup instructions for a human are in [README.md](README.md); the
prompt-to-response path is traced in [docs/flow.md](docs/flow.md).

```bash
docker compose up -d --build     # postgres, minio, api, web, mcp
open http://127.0.0.1:3000       # shop + dashboard
```

The crawler is a one-shot tool behind a compose profile, so it does not start
with `up`: `docker compose run --rm crawler crawl`.

| Service | Port | Notes |
|---|---|---|
| `web` | 127.0.0.1:3000 | nginx serving the SPA, proxies `/api` + `/media` to `api` |
| `api` | 127.0.0.1:8080 | Go service |
| `mcp` | 127.0.0.1:3001/mcp | MCP Apps server (Python), read-only admin tools |
| `postgres` | 127.0.0.1:5432 | database `stockroom` |
| `minio` | 127.0.0.1:9000 / 9001 | private bucket `stockroom-media`, console on 9001 |

**Every port is loopback-bound and must stay that way** — see Identity below.
Sign in as `alice@stockroom.local` (customer) or `admin@stockroom.local` (admin).

## The pieces

### `backend-ops/` — Go API
Owns all SQL and MinIO access. `net/http` stdlib routing, `pgx/v5`, `minio-go/v7` — no
framework. `internal/store` holds every query and returns domain structs; `internal/httpapi`
owns JSON shapes and never builds SQL.

```bash
cd backend-ops && go build ./... && go vet ./...
go run ./cmd/api                 # 127.0.0.1:8080, defaults match docker-compose
```

**There are no Go tests** — they were written, then removed on request. Verification is by
curl and the browser check below. Nothing guards regressions in the ordering and pricing
rules listed under Gotchas.

### `frontend-ops/` — React + Vite + Mantine 9
Shop (`/shop`), order lookup (`/orders`), admin dashboard (`/admin`). `/` redirects by role:
admins land on the dashboard, customers on the shop. The dashboard route is lazy-loaded so
its ~132 KB of chart code never reaches a shopper.

```bash
cd frontend-ops && npm run dev            # 127.0.0.1:5173, proxies to :8080
node render-check.mjs                     # headless Chrome check, fails on console errors
BASE=http://127.0.0.1:3000 node render-check.mjs   # against the container
```

`render-check.mjs` is the closest thing to a test suite: it signs in as both roles, opens the
product gallery, edits a size price, and reports console errors. **Use it after UI changes** —
curl cannot execute JS, so `GET /` only ever returns an empty `<div id="root">`.

### `crawler/` — Python, standalone
Populates the catalog. Own venv, own `requirements.txt`, own `.env`; shares nothing with the
rest. Runs **once, offline** — nothing at request time depends on it.
See [crawler/README.md](crawler/README.md).

```bash
cd crawler && source .venv/bin/activate
python -m stockroom_crawler.cli crawl     # defaults: 70 products across 8 categories
```

### `mcp-ops/` — MCP Apps server (Python)
Read-only admin tools. `mcp.server.apps` provides first-class Apps support:
`Apps().tool(resource_uri=...)` stamps `_meta.ui.resourceUri`, and
`add_html_resource` serves `ui://` under `text/html;profile=mcp-app`.

**`mcp` 2.x renamed `FastMCP` to `MCPServer`** — the older `app/mcp_server/`
pins `mcp>=1.18,<2` and does not match.

`mcp-ops/views/` is **not** a second app: the View runs in the host's sandboxed
iframe, so it must be browser JS whatever the server is written in. vite +
`vite-plugin-singlefile` inlines it into one HTML file because the iframe CSP is
deny-by-default. Rebuild it (`cd views && npm run build`) after changing the UI.

Tools are read-only on purpose: product text is crawled from a live site, so a
prompt injection could otherwise trigger order cancellation or price edits.

### `chat-ui/` — React + Vite + Mantine 9
The browser UI for the Ollama chat. Same stack and theme as `frontend-ops/`, deliberately:
the two React apps should read as one product.

```bash
cd chat-ui && npm run dev     # 127.0.0.1:5174, proxies to the chat backend on :3002
npm run build                 # tsc -b && vite build
```

`src/lib/sse.ts` parses the SSE frames off the fetch body by hand — `EventSource` cannot
POST. `src/lib/transcript.ts` owns the `Entry` union the message list renders and the
stored-message → `Entry` mapping that restores a conversation after a reload.

`mediaUrl()` in `src/lib/api.ts` keeps only same-origin `/media/products/...` paths.
Product text is crawled from a live site, so an absolute URL arriving in an image field
must never become an `<img src>` pointing off this origin.

### `docs/api-contract.md` + `.yaml`
The frozen interface between the Go service and the future MCP server. The markdown holds the
**rationale**; the YAML (OpenAPI 3.1, validated) holds the **exact shapes**. If they disagree,
the markdown is the intent and the YAML is the bug. Read the markdown's six derivation rules
before adding an endpoint.

## Identity — deliberately not authentication

`POST /api/v1/login` swaps an email for a `user_id`, creating the user if new. The frontend
keeps it in `localStorage` and sends it as **`X-Stockroom-User`** on every call. Go reads it in
one function (`currentUserID` in [user.go](backend-ops/internal/httpapi/user.go)) and every
query filters on it.

There are **no sessions, tokens, JWT, OAuth, or password hashing**, and none should be added
without being asked. `password_hash` holds an unusable sentinel that nothing checks.

`requireAdmin` gates `/api/v1/admin/*` on the `is_admin` column, granted at startup from
`STOCKROOM_ADMIN_EMAILS` and **never over HTTP**. That is *authorization*, not authentication:
it stops a normal shop user reaching the dashboard, but not anyone who can forge the header —
they would simply send the admin's id.

> **This is safe only because every port is loopback-bound.** Publishing `8080` (or `3000`,
> which proxies to it) turns `X-Stockroom-User` into an open impersonation switch. Never
> change a compose ports line to `"8080:8080"`.

## Gotchas

### Data model
- **Sizes must be ordered by `price_adjustment_jpy`, never by `size_name`** — alphabetical
  gives L, M, S. There is no `display_order` column. Images order by `id`.
- **Price filters match a single size.** `min_price`+`max_price` live in **one** `EXISTS` over
  `product_sizes`. Split into two clauses, a product whose S is under max and whose L is over
  min would wrongly match.
- **`?category=` takes words, not just slugs.** `resolveCategories` in
  [categorymatch.go](backend-ops/internal/httpapi/categorymatch.go) tries an exact slug first,
  then falls back to substring matching over slug and display name with case and separators
  folded. Exact-first is load-bearing: without it a short slug drags in every longer slug that
  contains it. This is what lets a caller filter without fetching `/api/v1/categories` first —
  don't reintroduce that round trip.
- **`ProductList` carries `selected_categories`** (and `unmatched_categories` when non-empty),
  never the full category list. A consumer builds its filter chips from the groups it got.
- **Money is `INTEGER` in Postgres** (int32). `quote` and `place_order` refuse totals above
  2,147,483,647 rather than failing on INSERT.
- **`order_items` is a snapshot**, copying `product_name`, `size_name`, `unit_price_jpy`. A
  re-crawl must never rewrite order history.
- **Admin catalog edits are overwritten by the next crawl** (it upserts on
  `source_product_id`). `is_active` survives — the crawler never sets it.
- **The default user's id is not 1.** `BIGSERIAL` advances on conflicting inserts. Resolve it
  by email; never hard-code.
- **`chat_messages` is written only through the Go API.** `/api/v1/chat/messages` (GET,
  POST, DELETE) is scoped to `currentUserID`, so one rolling thread per user needs no
  thread id. The Python chat service persists over HTTP with `X-Stockroom-User` rather than
  opening its own connection — that is what keeps "backend-ops owns all SQL" true. Writes
  are best-effort: a failure warns and the chat still answers.
- **Replayed history gives the model prose, not tool results.** Ollama requires a `tool`
  message to follow the assistant message carrying the matching `tool_calls`, and those ids
  do not survive a restart, so `history.model_messages` replays user/assistant text only.
  The browser still re-renders cards from the stored `payload` column.

### Schema
[backend-ops/schema.sql](backend-ops/schema.sql) is the single source of truth — the crawler's
`init-db` reads that exact file, so schema changes need no crawler edit. `init-db` **drops
every table**, including `users` and `orders`; use `crawl --reset` to re-import only the
catalog.

### Crawler / source site
- `/products/{id}` **404s without `?sku=`**.
- **Never read prices from the Nuxt payload** — it uses index-based dereferencing, so
  `"price":181` means *element 181 of an array*, not ¥181. Only the schema.org `Product`
  JSON-LD has real numbers.
- Prices are tiered and fractional; the crawler stores `ceil(highPrice)` (minimum-order price).
- A bare L1 category page lists no products — discovery must walk depth ≥ 2.

### Frontend / infra
- **nginx `try_files ... /index.html` is load-bearing.** `/shop`, `/admin`, `/orders` are React
  routes; without it a hard refresh 404s.
- The API container binds `0.0.0.0` **inside** the container (Docker cannot route to
  `127.0.0.1` there); the *published* port is what keeps it loopback-only.
- `SHOP_ENABLED=false docker compose up -d api` turns the storefront into Page-not-found for
  customers while admins keep the dashboard. Server-side, so no frontend rebuild.
- Build the crawler venv with `python3.13` (Homebrew). macOS's `/usr/bin/python3` is 3.9 on
  LibreSSL and makes urllib3 warn on every command.

## `app/` — the local Ollama chat, now live

[app/](app/) began as the apparel MVP but is now wired into compose and runs against
stockroom: `app/mcp_server/` is the **shopping** MCP server (`shopping-mcp`, the commerce
tools with the confirm-gated `place_order`), and `app/chat_app/` is the chat backend
(`chat`) that hosts a local Ollama model and drives that MCP server over stdio.

`app/chat_app/` serves **no HTML** — its browser UI is [chat-ui/](chat-ui/), a separate
React service behind nginx, same shape as `frontend-ops/` → `api`. `proxy_buffering off`
in [chat-ui/nginx.conf](chat-ui/nginx.conf) is load-bearing: `POST /api/chat` is an SSE
stream and buffering would deliver the whole reply in one lump.

Chat history is persisted through the Go API, never by Python directly — see the
`chat_messages` note under Data model.

`legacy/`, `plugins/` and the root `Makefile` are still dead weight from the apparel MVP;
the Makefile's targets invoke `stockroom_crawler.cli` from the repository root, where the
package no longer lives. `tests/` is **not** dead — it is the Python suite for `app/` and
the crawler, run with `docker compose --profile test run --rm test-python`.

## What's left

The commerce tools and the confirm-gate now exist in `app/mcp_server/`, enforced by the chat
UI: `place_order` is withheld from the model (`MODEL_BLOCKED_TOOLS` in
[mcp_client.py](app/chat_app/mcp_client.py)) and reachable only from the Approve / Reject
buttons on the confirmation card. The Go service still does not enforce it and cannot — it
cannot see which caller invoked the endpoint.

Not built: `ui://` Views for the commerce tools, so the flow renders in an MCP host
(Claude Desktop) rather than only in `chat-ui/`. `mcp-ops/` shows the pattern.
