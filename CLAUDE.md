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

Full setup instructions for a human are in [SETUP.md](SETUP.md); the
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

## The four pieces

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
- **Money is `INTEGER` in Postgres** (int32). `quote` and `place_order` refuse totals above
  2,147,483,647 rather than failing on INSERT.
- **`order_items` is a snapshot**, copying `product_name`, `size_name`, `unit_price_jpy`. A
  re-crawl must never rewrite order history.
- **Admin catalog edits are overwritten by the next crawl** (it upserts on
  `source_product_id`). `is_active` survives — the crawler never sets it.
- **The default user's id is not 1.** `BIGSERIAL` advances on conflicting inserts. Resolve it
  by email; never hard-code.

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

## Prior work — ignore for stockroom

[app/](app/) is an earlier MVP crawling **apparel.raksul.com** into a `raksul_db` database via
SQLAlchemy, with its own chat-only MCP server. Different site, schema, and product. Its
database is no longer in the compose file, so its CLI will fail. Do not extend it.
[README.md](README.md) documents only that MVP.

## What's left

The MCP server: five tools (`search_products`, `get_quote`, `add_to_cart`, `place_order`,
`get_order`), the `ui://` Views, and the **confirm-gate on `place_order`** — requirement.md
requires it to be reachable only from the confirm View, and the Go service deliberately does
not enforce that because it cannot see which View called it.
