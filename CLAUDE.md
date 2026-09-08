# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A PoC for [docs/requirement.md](docs/requirement.md): conversational commerce over MCP Apps —
interactive UI rendered *inside* the chat, not a chat-only MCP server. The catalog is real data
crawled from **stockroom.raksul.com** (RAKSUL Business Mall — office and store supplies, *not*
printing), served by a Go API behind a React storefront, an admin dashboard, two MCP servers and
a local-model chat.

```
stockroom.raksul.com
        │  crawler/ (Python, offline, run once)
        ▼
   Postgres + MinIO
        ▲
        │  backend-ops/ (Go) — the ONLY process touching SQL or MinIO
        │
   ┌────┴──────────────┬──────────────────┬─────────────────┐
   │                   │                  │                 │
frontend-ops/      mcp-ops/           mcp-shop/         chat-host/
(React, via        (Python, MCP       (Python, MCP      (Python, MCP *host*)
 nginx `web`)       Apps, read-only    Apps, commerce         │
                    admin ops)         + write)          chat-ui/ (React)
                         │                  │                 │
                    Claude Desktop      Claude / ChatGPT ──────┘
```

Three diagrams — ERD, admin read flow, architecture — live in
[docs/diagrams/](docs/diagrams/) as mermaid source plus rendered PNGs.

## Run everything

Full human-facing setup is in [README.md](README.md); the prompt-to-response path is traced in
[docs/flow.md](docs/flow.md).

```bash
docker compose up -d --build     # 8 services
open http://127.0.0.1:3000       # shop + dashboard
open http://127.0.0.1:3004       # Ollama chat
```

The crawler is one-shot behind a profile, so it does not start with `up`:
`docker compose run --rm crawler crawl`.

| Service | Port | Notes |
|---|---|---|
| `web` | 3000 | nginx serving `frontend-ops`, proxies `/api` + `/media` to `api` |
| `api` | 8080 | Go service |
| `mcp` | 3001/mcp | `mcp-ops` — read-only **admin** MCP Apps server |
| `chat` | 3002 | `chat-host` — MCP host + SSE, serves no HTML |
| `shopping-mcp` | 3003/mcp | `mcp-shop` — **commerce** MCP Apps server |
| `chat-ui` | 3004 | nginx serving the chat SPA, proxies to `chat` |
| `postgres` | 5432 | database `stockroom` |
| `minio` | 9000 / 9001 | private bucket `stockroom-media` |

`ollama` + `model-init` exist under `--profile docker-ollama`; by default `chat` talks to a
**host** Ollama at `host.docker.internal:11434`.

**Every port is loopback-bound and must stay that way** — see Identity below.
Sign in as `alice@stockroom.local` (customer) or `admin@stockroom.local` (admin).

## Tests

There is **no Makefile**, despite `make test` appearing in README.md — that section is stale.
Everything runs through compose profiles:

```bash
docker compose --profile test run --rm --build test-mcp-shop    # mcp-shop/tests
docker compose --profile test run --rm --build test-chat-host   # chat-host/tests
docker compose --profile test run --rm --build test-crawler     # crawler/tests
docker compose --profile test run --rm --build test-go          # go test ./...
docker compose --profile test run --rm --build test-python      # root tests/ — e2e, needs a live stack
```

**`test-go` passes vacuously — there are no `*_test.go` files.** They were written, then removed
on request. Nothing guards the ordering and pricing rules under Gotchas; verification is by curl
and by the browser check below.

Python unit suites live with their service; root `tests/` holds only cross-service e2e.

## The pieces

### `backend-ops/` — Go API
Owns all SQL and MinIO access. `net/http` stdlib routing, `pgx/v5`, `minio-go/v7` — no framework.
`internal/store` holds every query and returns domain structs; `internal/httpapi` owns JSON shapes
and never builds SQL.

```bash
cd backend-ops && go build ./... && go vet ./...
go run ./cmd/api                 # 127.0.0.1:8080, defaults match docker-compose
```

### `frontend-ops/` — React + Vite + Mantine 9
Shop (`/shop`), order lookup (`/orders`), admin dashboard (`/admin`). `/` redirects by role. The
dashboard route is lazy-loaded so its chart code never reaches a shopper.

```bash
cd frontend-ops && npm run dev            # 127.0.0.1:5173, proxies to :8080
node render-check.mjs                     # headless Chrome check, fails on console errors
BASE=http://127.0.0.1:3000 node render-check.mjs   # against the container
node render-mermaid.mjs                   # re-renders docs/diagrams/*.mmd to PNG
```

`render-check.mjs` is the closest thing to a test suite: it signs in as both roles, opens the
gallery, edits a size price, and reports console errors. **Use it after UI changes** — curl cannot
execute JS, so `GET /` only ever returns an empty `<div id="root">`. It is occasionally flaky on
the sign-in navigation; re-run before believing a failure.

### `crawler/` — Python, standalone
Populates the catalog. Own venv, own `requirements.txt`, own `.env`; shares nothing.
Runs **once, offline** — nothing at request time depends on it.

```bash
cd crawler && source .venv/bin/activate
python -m stockroom_crawler.cli crawl     # defaults: 70 products across 8 categories
```

### `mcp-ops/` — read-only admin MCP Apps server (Python)
Five tools, five `ui://` Views. `mcp.server.apps` provides first-class Apps support:
`Apps().tool(resource_uri=...)` stamps `_meta.ui.resourceUri`, and `add_html_resource` serves
`ui://` under `text/html;profile=mcp-app`. Declared in [docs/mcp-tools.md](docs/mcp-tools.md).

**`mcp` 2.x renamed `FastMCP` to `MCPServer`.**

Tools are read-only on purpose: product text is crawled from a live site, so a prompt injection
could otherwise trigger order cancellation or price edits.

### `mcp-shop/` — commerce MCP Apps server (Python)
The actual demo bar: `open_storefront`, `search_products`, `get_product`, `list_categories`,
`get_quote`, `get_cart`, `add_to_cart`, `remove_cart_item`, `prepare_order`, `place_order`,
`get_order`. One shared instance every host connects to — the local chat, Claude Desktop, ChatGPT.

Sibling of `mcp-ops/`; read-only admin vs. write commerce stays a real boundary.

### `chat-host/` + `chat-ui/` — the local-model lane
`chat-host` is the MCP *host*: model loop, browser session, SSE stream, an ordinary
streamable-http client of `shopping-mcp` via `SHOPPING_MCP_URL`. It serves no HTML — its UI is
`chat-ui/`, a React SPA behind nginx.

```
Prompt → Ollama → chat-host → shopping-mcp → Go API → Postgres
```

`chat-ui/src/lib/sse.ts` parses SSE frames off the fetch body by hand (`EventSource` cannot POST).
`mediaUrl()` in `src/lib/api.ts` keeps only same-origin `/media/products/...` paths — product text
is crawled, so an absolute URL in an image field must never become an `<img src>` off this origin.

### Views — `mcp-ops/views/`, `mcp-shop/views/`
React + Mantine, built by vite into **one self-contained HTML file per View** because the iframe
CSP is deny-by-default. Rebuild after changing UI:

```bash
cd mcp-ops/views && npm run build      # build.mjs: one vite build per View
cd mcp-shop/views && npm run build
npm run typecheck                      # both
```

- **Keep `cssCodeSplit: true`.** `vite-plugin-singlefile`'s recommended config turns it off, which
  makes vite inject the stylesheet from JavaScript at runtime; a real `<style>` tag needs no
  script to have run first.
- **`vite-plugin-singlefile` sets `inlineDynamicImports`**, which rollup rejects alongside multiple
  inputs — hence one build per View, driven by `build.mjs`.
- **The protocol is `@modelcontextprotocol/ext-apps`, not hand-written.** `App` owns
  ui/initialize, capability negotiation, JSON-RPC framing, auto-resize and teardown.
- **Charts stay hand-rolled SVG** (`mcp-ops/views/src/components/Charts.tsx`). Recharts would add
  ~500 KB per View to draw a handful of simple shapes. A native `<title>` per shape is the tooltip
  — no JS, no positioning maths, nothing that can escape the iframe.
- Mantine costs about 2× — a View is ~950 KB rather than ~440 KB, and every `resources/read` ships
  the whole document inline.
- Entry files live in `entries/` and views in `views/`: on a case-insensitive filesystem
  `product.tsx` and `Product.tsx` are the same file.
- **Chart colours are validated, not chosen.** [mcp-ops/views/src/lib/palette.ts](mcp-ops/views/src/lib/palette.ts)
  records the validator output and the command to re-run. The previous palette had a series outside
  the lightness band at 1.81:1 contrast — those bars were nearly invisible. Light and dark have
  *different* bands (0.43–0.77 vs 0.48–0.67), so a palette that passes one can fail the other;
  re-run both modes before changing a value.

### `docs/api-contract.md` + `.yaml`
The frozen interface between the Go service and the MCP servers. The markdown holds the
**rationale**; the YAML (OpenAPI 3.1, validated) holds the **exact shapes**. If they disagree, the
markdown is the intent and the YAML is the bug.

`npx @redocly/cli lint docs/api-contract.yaml` reports **21 `security-defined` errors that are
expected** — this API has no auth scheme by design. Only new rule violations matter.

## Identity — deliberately not authentication

`POST /api/v1/login` swaps an email for a `user_id`, creating the user if new. The frontend keeps
it in `localStorage` and sends it as **`X-Stockroom-User`** on every call. Go reads it in one
function (`currentUserID` in [user.go](backend-ops/internal/httpapi/user.go)) and every query
filters on it.

There are **no sessions, tokens, JWT, OAuth, or password hashing**, and none should be added
without being asked. `password_hash` holds an unusable sentinel that nothing checks.

`requireAdmin` gates `/api/v1/admin/*` on the `is_admin` column, granted at startup from
`STOCKROOM_ADMIN_EMAILS` and **never over HTTP**. That is *authorization*, not authentication: it
stops a normal shop user reaching the dashboard, but not anyone who can forge the header.

> **This is safe only because every port is loopback-bound.** Publishing `8080` (or `3000`, which
> proxies to it) turns `X-Stockroom-User` into an open impersonation switch. Never change a compose
> ports line to `"8080:8080"`.

**`mcp-ops` has no sign-in: it resolves `STOCKROOM_ADMIN_EMAIL` once at startup and sends that
id on every call** (`_ensure_admin` in [api.py](mcp-ops/stockroom_ops/api.py)). So the access rule
is "whoever can reach port 3001 is admin" — there is no per-connection identity and no credential.
A per-connection sign-in with a passcode was built on the `hotfix` branch and then removed on
request; `git log main..hotfix` has it if it is ever wanted back. This is the single biggest reason
3001 must stay loopback-bound.

**`owner(ctx)` in `mcp-shop` must not be `id(ctx.session)`.** Carts and confirmations are keyed on
it, and a memory address is recycled once a session is collected, so a new session could inherit a
dead one's signed-in user. It is a `secrets` token in a `WeakKeyDictionary` with a finalizer.

**The confirm gate is enforced by the client, not the server.** `MODEL_BLOCKED_TOOLS` in
[chat-host/stockroom_chat/mcp_client.py](chat-host/stockroom_chat/mcp_client.py) withholds
`place_order`, `mock_sign_in` and `open_storefront` from the model; `place_order` is reachable only
from the Approve / Reject buttons on the confirmation card. The Go service does not enforce it and
cannot — it cannot see which caller invoked the endpoint.

**That gate therefore does not exist for any other host.** `mcp-shop` advertises `place_order` with
`visibility: ["model", "app"]`, and `prepare_order` returns the confirmation token in its result —
so a host wired straight to `shopping-mcp` (Claude Desktop is, as `raksul_catalog`) can call
`prepare_order`, read the token out of the response and `place_order` it with no human ever
clicking Approve. The fix is the mechanism already in the file: mark `place_order`
`visibility: ["app"]` so a compliant host keeps it out of the model's tool list. Still open.

## Gotchas

### Data model
- **Sizes must be ordered by `price_adjustment_jpy`, never by `size_name`** — alphabetical gives
  L, M, S. There is no `display_order` column. Images order by `id`.
- **Price filters match a single size.** `min_price`+`max_price` live in **one** `EXISTS` over
  `product_sizes`. Split into two clauses, a product whose S is under max and whose L is over min
  would wrongly match.
- **`?category=` takes words, not just slugs.** `resolveCategories` in
  [categorymatch.go](backend-ops/internal/httpapi/categorymatch.go) tries an exact slug first, then
  falls back to substring matching over slug and display name with case and separators folded.
  Exact-first is load-bearing: without it a short slug drags in every longer slug that contains it.
  This is what lets a caller filter without fetching `/api/v1/categories` first — don't reintroduce
  that round trip.
- **`limit` caps the TOTAL across groups, and whole groups are trimmed once it is spent**
  ([catalog.go](backend-ops/internal/httpapi/catalog.go), `groupByCategory`). Groups sort largest
  first, so `?limit=20` returns 20 products from the biggest category and **drops the other nine
  entirely** — which reads as a broken shop. `per_category=N` is what spreads a response across
  the catalog; `maxLimit` is 100, so no single call can return all 141 products.
- **A group's `count` is how many that response returned, not how many the category holds.**
  `groupByCategory` sets `g.Count = len(g.Products)` *after* trimming, so it can never tell you a
  category's real size — `/api/v1/categories` carries `product_count` for that. Rendering `count`
  as a category size under-reports whenever a response was trimmed.
- **List endpoints echo an `applied` block** — the filter *as the server understood it*. Views
  render their controls from that, never from what they believe they sent; that is what makes a
  panel arrive pre-filled from a prompt and never disagree with the rows beneath it.
- **`0` is not "unset".** `max_orders=0` means "customers who never ordered" and `max_quantity=0`
  is meaningful too, so `_params` in [api.py](mcp-ops/stockroom_ops/api.py) drops only `None` and
  `""`. Each sentinel is applied in the tool, where its meaning is known — `max_orders` uses `-1`
  for "no maximum". A falsy check here silently discarded a whole filter.
- **Order quantity means UNITS**, the sum of item quantities, not the number of lines. Rows carry
  both `total_quantity` and `item_count` so the number a filter used is visible beside the row.
- **Money is `INTEGER` in Postgres** (int32). `quote` and `place_order` refuse totals above
  2,147,483,647 rather than failing on INSERT.
- **`order_items` is a snapshot**, copying `product_name`, `size_name`, `unit_price_jpy`. A
  re-crawl must never rewrite order history.
- **Admin catalog edits are overwritten by the next crawl** (it upserts on `source_product_id`).
  `is_active` survives — the crawler never sets it.
- **The default user's id is not 1.** `BIGSERIAL` advances on conflicting inserts. Resolve it by
  email; never hard-code.
- **`chat_messages` is written only through the Go API.** The Python chat service persists over
  HTTP with `X-Stockroom-User` rather than opening its own connection — that is what keeps
  "backend-ops owns all SQL" true. Writes are best-effort.
- **Replayed history gives the model prose, not tool results.** Ollama requires a `tool` message to
  follow the assistant message carrying the matching `tool_calls`, and those ids do not survive a
  restart, so `history.model_messages` replays user/assistant text only. The browser still
  re-renders cards from the stored `payload` column.

### MCP tool schemas
- **A union schema makes models omit the argument entirely.** `anyOf: [array, string, null]` on
  `categories` presented exactly as "the category filter is broken". Every loose argument is a
  **plain string** with a `BeforeValidator` that still accepts a list, because some hosts send one.
- **Descriptions are suggestions; visibility is enforcement.** When the model fanned out one
  `get_product` call per row, sharpening descriptions did not stop it — `visibility=["app"]` did.
  It is model-visible again now (so "show me this product" works), with the guardrail back in
  wording. If fan-out returns, restore `visibility=["app"]`.

### Schema
[backend-ops/schema.sql](backend-ops/schema.sql) is the single source of truth — the crawler's
`init-db` reads that exact file, so schema changes need no crawler edit. `init-db` **drops every
table**, including `users` and `orders`; use `crawl --reset` to re-import only the catalog.

**`init-db` against a running `api` leaves you with no administrator.** `is_admin` is granted only
during API startup from `STOCKROOM_ADMIN_EMAILS`, so dropping `users` while `api` keeps running
means every `/api/v1/admin/*` call — and every `mcp-ops` tool — returns 403 until you restart it.
The order is always:

```bash
docker compose run --rm crawler init-db
docker compose restart api          # re-grants is_admin
docker compose run --rm crawler crawl
```

### Crawler / source site
- `/products/{id}` **404s without `?sku=`**.
- **Never read prices from the Nuxt payload** — it uses index-based dereferencing, so
  `"price":181` means *element 181 of an array*, not ¥181. Only the schema.org `Product` JSON-LD
  has real numbers.
- Prices are tiered and fractional; the crawler stores `ceil(highPrice)` (minimum-order price).
- A bare L1 category page lists no products — discovery must walk depth ≥ 2.

### Frontend / infra / docs
- **nginx `try_files ... /index.html` is load-bearing.** `/shop`, `/admin`, `/orders` are React
  routes; without it a hard refresh 404s.
- **A literal hostname in `proxy_pass` is resolved once, at config load, and cached for the life of
  the process.** Recreate the upstream (`docker compose up -d --build api`) and it gets a new IP
  while nginx keeps dialling the old one — every proxied request 502s until nginx restarts too.
  [chat-ui/nginx.conf](chat-ui/nginx.conf) resolves per request via Docker DNS (`resolver
  127.0.0.11` + the upstream in a variable); **[frontend-ops/nginx.conf](frontend-ops/nginx.conf)
  still has the literal form**, so `web` is exposed to this.
- **The root `.env` shadows compose's `${VAR:-default}`.** Compose auto-loads it for interpolation,
  so a variable set there wins and the `:-` fallback in `docker-compose.yml` never fires — editing
  the compose default appears to do nothing. Precedence: shell env > `.env` > compose `:-` default >
  the Python default in `config.py`. Check with `docker compose --profile tools config`.
- The API container binds `0.0.0.0` **inside** the container (Docker cannot route to `127.0.0.1`
  there); the *published* port is what keeps it loopback-only.
- `SHOP_ENABLED=false docker compose up -d api` turns the storefront into Page-not-found for
  customers while admins keep the dashboard. Server-side, so no frontend rebuild.
- Build the crawler venv with `python3.13` (Homebrew). macOS's `/usr/bin/python3` is 3.9 on
  LibreSSL and makes urllib3 warn on every command.
- **`;` is a statement separator in mermaid.** A label containing one — `text/html;profile=mcp-app`
  is the obvious candidate — fails to parse with an error pointing at the *next* line. It has
  bitten this repo twice. See [docs/diagrams/README.md](docs/diagrams/README.md).
- `docker compose down` leaves one-off `docker compose run` containers holding the network open
  (a stdio MCP server waits on stdin forever, so `--rm` never fires). Use
  `docker compose down --remove-orphans`.
