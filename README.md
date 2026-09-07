# Stockroom

A proof of concept for [docs/requirement.md](docs/requirement.md): conversational
commerce over **MCP Apps** — tools that render an interactive panel *inside* the
conversation rather than returning a wall of text.

The catalog is real data crawled from **stockroom.raksul.com** (RAKSUL Business
Mall — office and store supplies), served by a Go API behind a React storefront
and admin dashboard, and exposed to AI hosts by a Python MCP server.

```text
stockroom.raksul.com
        │  crawler/ (Python, offline, run once)
        ▼
   Postgres + MinIO
        ▲
        │  backend-ops/ (Go)  — the only process touching SQL or MinIO
        │
   ┌────┴────────────────────┐
   │                         │
frontend-ops/ (React)   mcp-ops/ (Python, read-only admin)
   via nginx                 │
                      Claude Desktop / other MCP hosts
```

The crawler is an offline import step. At request time the MCP server only calls
the Go API — it never reaches the supplier's website and never runs SQL. Checkout
is simulated; no money moves.

**Status:** the admin-ops MCP server is built and working. The *commerce* MCP
server (`search_products`, `get_quote`, `add_to_cart`, `place_order`, `get_order`)
is not — see [What's left](#whats-left).

| Where to look | For |
|---|---|
| [docs/flow.md](docs/flow.md) | What happens between a prompt and the answer |
| [docs/mcp-tools.md](docs/mcp-tools.md) | The five tool declarations in full |
| [docs/api-contract.md](docs/api-contract.md) | The Go ↔ MCP interface, and why it is shaped that way |
| [crawler/README.md](crawler/README.md) | The crawler on its own |
| [CLAUDE.md](CLAUDE.md) | Working on the code: layout, invariants, gotchas |

---

## Run it

Everything runs in Docker. You need **Docker Desktop** and nothing else — no
Python, Node, or Go on your machine.

```bash
git clone <this repo> && cd Printing-service
docker compose up -d --build
```

That builds and starts five services. First build takes a few minutes; after
that it is seconds.

| Service | URL | What it is |
|---|---|---|
| `web` | <http://127.0.0.1:3000> | Shop + admin dashboard (React, served by nginx) |
| `api` | <http://127.0.0.1:8080> | Go JSON API — the only process touching SQL or MinIO |
| `mcp` | <http://127.0.0.1:3001/mcp> | MCP Apps server (Python) for AI hosts |
| `postgres` | 127.0.0.1:5432 | database `stockroom` |
| `minio` | <http://127.0.0.1:9001> | product images, console login `minioadmin` / `minioadmin` |

Check they came up healthy:

```bash
docker compose ps          # all five should say (healthy)
curl -s 127.0.0.1:8080/healthz
# {"status":"ok","database":"ok","minio":"ok"}
```

> **Every port binds `127.0.0.1` deliberately.** The API trusts an identity
> header without verifying it, so exposing these ports would let anyone act as
> any user. Never change a ports line to `"8080:8080"`.

---

## 1. Load the catalog

A fresh database is empty. The crawler fetches real products from
stockroom.raksul.com and stores images in MinIO. It is a one-shot tool, so it
does not start with `docker compose up`:

```bash
docker compose run --rm crawler init-db     # create the tables
docker compose restart api                  # re-grant admin, see the warning below
docker compose run --rm crawler crawl       # ~25 min: 70 products, 8 categories
docker compose run --rm crawler stats       # what landed
```

`crawl` commits per product, so you can stop it (Ctrl-C) and re-run it later
without losing what it already imported.

Faster for a first look:

```bash
docker compose run --rm -e CRAWL_MAX_PRODUCTS=10 crawler crawl
```

> `init-db` **drops every table**, users and orders included. Because `is_admin`
> is granted only at API startup, running it against a live `api` leaves you with
> no administrator and every `/api/v1/admin/*` call returning 403 — hence the
> `docker compose restart api` above. To re-import only the catalog later, use
> `crawler crawl --reset`, which leaves `users` and `orders` alone.

---

## 2. Use the web app

Open <http://127.0.0.1:3000> and sign in with an email:

| Email | Role |
|---|---|
| `alice@stockroom.local` | customer — lands on the shop |
| `admin@stockroom.local` | admin — lands on the dashboard |

Any other address creates a new customer account.

**There is no password and nothing is verified.** Sign-in is a demo user
picker, not authentication. It is safe only because the ports are loopback-only.

Customers browse, filter, add to cart and check out. Admins get charts, order
management, catalog editing and a user list.

### Turning the shop off

```bash
SHOP_ENABLED=false docker compose up -d api
```

Customers then get **Page not found**; admins keep the dashboard. This is
server-side, so the frontend is never rebuilt. Turn it back on with
`docker compose up -d api`.

---

## 3. Connect Claude Desktop

The `mcp` service exposes the catalog to AI hosts as an **MCP App** — a tool
that renders an interactive dashboard *inside the conversation*, not just text.
[docs/flow.md](docs/flow.md) traces what happens between your prompt and the
answer.

Claude Desktop launches MCP servers itself over stdio, so point it at the
container. Edit:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Add an `mcpServers` block, keeping anything already in the file:

```json
{
  "mcpServers": {
    "stockroom-ops": {
      "command": "docker",
      "args": [
        "compose",
        "-f", "/ABSOLUTE/PATH/TO/Printing-service/docker-compose.yml",
        "run", "--rm", "-i",
        "mcp", "--transport", "stdio"
      ]
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO/` with the real path — `pwd` in the repo prints it.
Paths must be absolute: Claude Desktop does not inherit your shell's working
directory or `PATH`.

Then **fully quit Claude Desktop (⌘Q) and reopen it** — the config is read only
at launch.

Ask Claude: *"Show me the stockroom dashboard."*

You should see the `get_dashboard` tool run and a panel render inline with six
tiles — products, categories, orders, revenue. The 7d/14d/30d/90d buttons inside
it call the tool again directly, without the model being involved.

### Prompts to try

Five read-only tools are available — `get_dashboard`, `list_orders`,
`list_products`, `get_product`, `list_users` — each with its own panel. See
[docs/mcp-tools.md](docs/mcp-tools.md) for the full declaration.

**Open the panel**

- "Show me the stockroom dashboard."
- "Open the ops view for the last 7 days."
- "How is the shop doing this quarter?" *(picks a 90-day range)*

**Ask about the numbers** — the panel renders and Claude reads the same data:

- "What is our revenue, and how much of it is at risk from cancelled orders?"
- "How many products are inactive right now?"
- "How many carts are open but not checked out?"
- "Which category has the most products, and which the fewest?"
- "Are our products mostly cheap or expensive? Show the price spread."
- "What are the best selling products by revenue?"
- "Which day had the most orders in the last two weeks?"
- "Give me a one-paragraph summary of the catalog for a stand-up."

**Compare across ranges** — each is a separate tool call:

- "Compare the last 7 days with the last 30. Is order volume growing?"
- "Show me 90 days, then tell me how many days had no orders at all."

**Sanity checks worth asking**

- "Does the number of sizes match three per product? If not, how many are missing?"
- "Every product should have images. How many images per product on average?"

> Data is a **fixed crawled snapshot**, not live inventory, and orders are mock
> checkouts from testing. Claude will happily reason over it — just do not read
> the revenue as real.

**Browse orders, catalog and users**

- "Show me all the orders."
- "Any cancelled orders?"
- "Search the catalog for paper."
- "Tell me about product 34." *(shows its photos)*
- "Who has been ordering, and how much have they spent?"

### What it cannot do

All five tools are **read-only**. Asking to cancel an order, change a price or
deactivate a product will not work — no such tool is exposed. That is
deliberate: product text is crawled from a live website, so a prompt injection
could otherwise talk the model into a destructive call. The write endpoints
exist on the Go API and are reachable from the admin web UI at
<http://127.0.0.1:3000>.

### If Docker startup is too slow

`docker compose run` starts a container per launch. To run the server directly
on your machine instead:

```bash
cd mcp-ops
python3.13 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cd views && npm install && npm run build     # builds the UI the server serves
```

```json
{
  "mcpServers": {
    "stockroom-ops": {
      "command": "/ABSOLUTE/PATH/TO/Printing-service/mcp-ops/.venv/bin/python",
      "args": ["-m", "stockroom_ops.server", "--transport", "stdio"],
      "cwd": "/ABSOLUTE/PATH/TO/Printing-service/mcp-ops"
    }
  }
}
```

The `npm run build` step is not optional: the server reads each View out of
`mcp-ops/views/dist/` at startup and exits if one is missing. `docker compose
up -d` must still be running either way — the MCP server reads everything
through the Go API.

### If the tool runs but shows text instead of a UI

That means the host is not rendering `ui://` resources. Verify the server is
offering them correctly:

```bash
docker compose logs mcp
curl -s -X POST 127.0.0.1:3001/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

The tool must carry `_meta.ui.resourceUri` and the resource must be served as
`text/html;profile=mcp-app`. Both are verified working — if they are correct and
the UI still does not render, it is a host-side limitation, not a server bug.

---

## Common tasks

```bash
docker compose logs -f api            # follow a service's logs
docker compose restart api
docker compose up -d --build web      # rebuild one service after a change
docker compose down --remove-orphans  # stop everything, keep data
docker compose down -v                # stop and DELETE the database + images
```

### Stopping cleanly

Use `--remove-orphans`. Plain `docker compose down` leaves behind one-off
containers created by `docker compose run` — including the stdio container
Claude Desktop launches — and you get:

```
! Network printing-service_default   Resource is still in use
```

Those containers hold the network open. A stdio MCP server waits on stdin
forever, so it never exits and `--rm` never fires. If one is stuck:

```bash
docker ps -a --filter "label=com.docker.compose.project=printing-service"
docker rm -f <name>
```

| Command | Containers | Network | Data |
|---|---|---|---|
| `docker compose stop` | paused | kept | kept |
| `docker compose down --remove-orphans` | removed | removed | **kept** |
| `docker compose down -v` | removed | removed | **DELETED — re-crawl needed** |

### Seeing which API is called

Every request the Go service handles is logged as one line:

```bash
docker compose logs -f api | grep msg=request
```

```
level=INFO msg=request method=GET  path=/api/v1/products     status=200 dur_ms=4 query="limit=2" bytes=1497
level=INFO msg=request method=GET  path=/api/v1/admin/stats  status=200 dur_ms=4 user=31 bytes=1722
level=WARN msg=request method=GET  path=/api/v1/admin/stats  status=403 dur_ms=0 user=6
level=WARN msg=request method=GET  path=/api/v1/products/999 status=404 dur_ms=0
```

The level reflects the outcome, so failures are easy to isolate:

```bash
docker compose logs api | grep -E 'level=(WARN|ERROR)'   # only 4xx and 5xx
```

`user=` is the `X-Stockroom-User` header — absent means the request fell back
to the default user, which is how a `403` on an admin route usually happens.

`/healthz` and `/media` are filtered out at `info`: Docker probes health every
15 seconds and a single page loads dozens of images, so both would bury real
traffic. To see them:

```bash
STOCKROOM_LOG_LEVEL=debug docker compose up -d api
```

Inspect the database directly:

```bash
docker exec printing-service-postgres-1 psql -U raksul -d stockroom -c "\dt"
docker exec printing-service-postgres-1 psql -U raksul -d stockroom -c \
  "SELECT name, base_price_jpy FROM products LIMIT 5;"
```

---

## Configuration

Defaults work with no `.env` file. Override by exporting before
`docker compose up`:

| Variable | Default | Effect |
|---|---|---|
| `SHOP_ENABLED` | `true` | `false` hides the storefront from customers |
| `STOCKROOM_ADMIN_EMAILS` | `admin@stockroom.local` | Comma-separated; granted admin at startup |
| `CRAWL_MAX_PRODUCTS` | `70` | Products to fetch |
| `CRAWL_MAX_CATEGORIES` | `8` | Categories to draw from (of 16) |
| `STOCKROOM_LOG_LEVEL` | `info` | `debug` also logs `/healthz` and `/media` |
| `STOCKROOM_CORS_ORIGIN` | `*` | Allowed browser origin; `*` means any |

Admin is granted **only at API startup from configuration** — no HTTP route can
hand it out.

> **`STOCKROOM_CORS_ORIGIN=*` is a real exposure if the port ever leaves
> localhost.** Identity is an unverified `X-Stockroom-User` header, so a
> wildcard origin lets any page a user visits call the API from their browser
> and act as any user, admin included. Narrow it to a specific origin before
> exposing the port:
>
> ```bash
> STOCKROOM_CORS_ORIGIN=http://localhost:5173 docker compose up -d api
> ```
>
> The web app at `:3000` does not need CORS at all — nginx proxies `/api`, so
> the browser sees one origin.

Docker Compose reaches Postgres and MinIO by the internal hostnames `postgres`
and `minio`. Do not replace those with host addresses.

---

## Troubleshooting

**`address already in use`** — something is already on that port. Find it with
`lsof -nP -iTCP:3001 -sTCP:LISTEN`, or `docker compose down` first.

**`web` is healthy but shows nothing** — check `api` is healthy too; the SPA
loads but every request 502s if the API is down.

**`api` is unhealthy, logs say `relation "users" does not exist`** — the schema
was never created. Run `docker compose run --rm crawler init-db`.

**Crawler says the catalog is empty** — run `init-db` before `crawl`.

**Admin dashboard or MCP tools return 403** — either you signed in as a
customer, or `init-db` dropped `users` while `api` kept running, so nobody holds
`is_admin` any more. Sign in as `admin@stockroom.local`, and run
`docker compose restart api` to re-grant admin from `STOCKROOM_ADMIN_EMAILS`.

**Images are broken in the shop** — MinIO is down or the crawl never ran.
`docker compose ps` and `docker compose run --rm crawler stats`.

---

## Working on the code

[CLAUDE.md](CLAUDE.md) is the guide for changing anything — module layout, the
ordering and pricing invariants, and the traps that have already bitten.

```bash
cd backend-ops  && go build ./... && go vet ./...   # there are no Go tests
cd frontend-ops && npm run dev                      # 127.0.0.1:5173, proxies to :8080
cd frontend-ops && node render-check.mjs            # headless Chrome, fails on console errors
cd mcp-ops/views && npm run build                   # rebuild the Views after a UI change
```

`render-check.mjs` is the closest thing to a test suite: it signs in as both
roles, opens the product gallery, edits a size price, and reports console
errors. Use it after UI changes — `curl` cannot execute JS, so `GET /` only ever
returns an empty `<div id="root">`.

[backend-ops/schema.sql](backend-ops/schema.sql) is the single source of truth
for the schema; the crawler's `init-db` reads that exact file, so schema changes
need no crawler edit.

### What's left

The commerce MCP server: five tools (`search_products`, `get_quote`,
`add_to_cart`, `place_order`, `get_order`), their `ui://` Views, and the
**confirm-gate on `place_order`** — [docs/requirement.md](docs/requirement.md)
requires it to be reachable only from the confirm View, and the Go service
deliberately does not enforce that because it cannot see which View called it.

---

## Prior work — ignore

[app/](app/) is an earlier MVP that crawls **apparel.raksul.com** into a
`raksul_db` database via SQLAlchemy, with its own chat-only MCP server and a
local Ollama chat host. Different site, schema and product. Its database is no
longer in the compose file, so its CLI will fail. [legacy/](legacy/),
[plugins/](plugins/), [tests/](tests/) and the root [Makefile](Makefile) belong
to that MVP too — the Makefile's targets still invoke `stockroom_crawler.cli`
from the repository root, where the package no longer lives. Do not extend any
of it.
