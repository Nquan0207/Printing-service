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
   ┌────┼──────────────┬───────────────┐
   │    │              │               │
frontend-ops/    mcp-ops/        mcp-shop/  ← one shared commerce MCP
 (React,nginx)  admin MCP       commerce MCP
                     │           │        │
              Claude Desktop     │   chat-host/ (Ollama host)
                / ChatGPT ───────┘        │
                                    chat-ui/ (React, nginx)
```

The crawler is an offline import step. At request time the MCP server only calls
the Go API — it never reaches the supplier's website and never runs SQL. Checkout
is simulated; no money moves.

Two MCP servers run in Docker and share the Go backend, with separate tool sets:
[mcp-ops/](mcp-ops/) is read-only admin, [mcp-shop/](mcp-shop/) is commerce with a
confirm-gated checkout. [chat-host/](chat-host/) is an MCP *host* — it runs the
local model and is an ordinary client of `mcp-shop`, the same server Claude
Desktop connects to. Its browser UI is [chat-ui/](chat-ui/), which proxies to it
the way `web` proxies to `api`.

| Where to look | For |
|---|---|
| [docs/flow.md](docs/flow.md) | What happens between a prompt and the answer |
| [docs/mcp-tools.md](docs/mcp-tools.md) | The five tool declarations in full |
| [docs/api-contract.md](docs/api-contract.md) | The Go ↔ MCP interface, and why it is shaped that way |
| [crawler/README.md](crawler/README.md) | The crawler on its own |
| [chat-ui/README.md](chat-ui/README.md) | The chat SPA, its nginx proxy and chat history |
| [mcp-shop/README.md](mcp-shop/README.md) | The commerce MCP server, its View and the confirm gate |
| [chat-host/README.md](chat-host/README.md) | The Ollama host and how it talks to the MCP server |
| [CLAUDE.md](CLAUDE.md) | Working on the code: layout, invariants, gotchas |

---

## Run it — Docker only

Install Docker Desktop (or Docker Engine with the Compose plugin), clone the
repository, and run from its root. No native Python, Node, Go or Ollama is needed:

```bash
docker compose up -d --build --wait
```

Optional settings are in `.env.example`; copy it to `.env` only to customize.
Startup uses the existing PostgreSQL database and MinIO bucket. It does not
run the crawler, initialize schemas, or validate them through a bootstrap job.
The API waits only for PostgreSQL and MinIO to be healthy.

Ollama downloads **qwen3:8b** if needed and reuses the model on later starts.
It uses CPU by default. `OLLAMA_TIMEOUT_SECONDS` defaults to 600 for CPU inference.
If you only need MCP for ChatGPT/Claude, start without chat or Ollama:

```bash
docker compose up -d --build --wait mcp shopping-mcp
```

| Service | Host URL | Purpose |
|---|---|---|
| `web` | http://127.0.0.1:3000 | Shop and admin dashboard |
| `api` | http://127.0.0.1:8080 | Go API |
| `mcp` | http://127.0.0.1:3001/mcp | Read-only admin MCP |
| `chat-ui` | http://127.0.0.1:3004 | Shopping chat UI (React) — **open this one** |
| `chat` | http://127.0.0.1:3002 | Chat backend: JSON and the SSE stream, no HTML |
| `shopping-mcp` | http://127.0.0.1:3003/mcp | Commerce MCP ([mcp-shop/](mcp-shop/)), confirm-gated checkout |
| `postgres` | 127.0.0.1:5432 | Database `stockroom`, user `raksul`, password `raksul_password` |
| `minio` | http://127.0.0.1:9001 | Console, `minioadmin` / `minioadmin` |

All published ports stay loopback-only. Containers use service DNS (`api`,
`postgres`, `minio`, `ollama`); browsers use the host URLs above. Change the
`*_HOST_PORT` variables in `.env` if a port is occupied. Do not replace internal
service URLs with localhost. The stack retains the existing `raksul_postgres_data`
and `raksul_minio_data` volume names; it does not migrate older differently named volumes.

Check service startup from another terminal:

```bash
docker compose logs -f api model-init chat
docker compose ps -a
```

`model-init` should show `Exited (0)`; long-running services should be healthy.
To remove containers left over from the former automatic bootstrap configuration,
run `docker compose up -d --build --wait --remove-orphans`. Named volumes are kept.

## 1. Load more catalog data

Crawling is manual only. For an empty installation, explicitly prepare the schema
and bucket first (existing incompatible schemas require a reviewed migration):

```bash
docker compose run --rm --build crawler bootstrap
```

To import data or inspect counts:

```bash
docker compose run --rm crawler crawl
docker compose run --rm crawler stats
# Smaller manual crawl:
docker compose run --rm -e CRAWL_MAX_PRODUCTS=3 -e CRAWL_MAX_CATEGORIES=1 crawler crawl
```

Crawling preserves size IDs referenced by carts and orders. Startup never uses
`init-db`. That manual command is destructive and reserved for an intentional
reset. `make reset-db CONFIRM_RESET=1` stops the stack, resets application tables,
and restarts the services without crawling; MinIO objects and downloaded models remain.

---

## 2. Use the web app

Open <http://127.0.0.1:3000> and sign in with an email:

| Email | Role |
|---|---|
| `alice@stockroom.local` | customer — lands on the shop |
| `admin@gmail.com` | admin — lands on the dashboard |

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
        "exec", "-i", "stockroom-admin-mcp",
        "python", "-m", "stockroom_ops.server", "--transport", "stdio"
      ]
    }
  }
}
```

Start the stack before connecting the host. The Docker CLI must be available to
the host application. No repository path or Python path is required.

For shopping tools, add a second entry:

```json
{
  "mcpServers": {
    "raksul_catalog": {
      "command": "docker",
      "args": ["exec", "-i", "stockroom-shopping-mcp", "python", "-m", "stockroom_shop.server"]
    }
  }
}
```

The repository plugin uses this shopping configuration. HTTP-capable clients can
instead use the two `/mcp` URLs above. These local URLs are for clients on the
same machine, not remotely hosted clients.

Then **fully quit Claude Desktop (⌘Q) and reopen it** — the config is read only
at launch.

Ask Claude: *"Show me the stockroom dashboard."*

Every ops tool requires the user to provide both name `admin` and email
`admin@gmail.com` in that request. If either value is missing, Claude must ask
for both. The backend reads the matching row from PostgreSQL and checks
`is_admin = true` on every tool call. For example: *"Open the stockroom
dashboard with name admin and email admin@gmail.com."* This is a demo access
gate, not real authentication—the name and email are not a password or token.

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

### Optional native development

Partner setup uses Docker, including stdio via `docker exec`. Developers who want
to run individual services natively can use the component READMEs. Keep native
virtualenv paths out of shared MCP configuration. Native chat retains loopback
validation; container mode explicitly permits only the API/Ollama service names.

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

## 4. Chat with a local model

Open <http://127.0.0.1:3004> and sign in with any name and email — the same
demo identity the storefront uses, with no password.

The page is a React app served by nginx ([chat-ui/](chat-ui/)); nginx proxies
`/api`, `/media` and `/healthz` to the `chat` backend, so the browser sees one
origin. `chat` itself serves no HTML: it answers JSON and streams the model's
reply as Server-Sent Events.

Ask for products in English, Japanese or Vietnamese. The model picks MCP tools
from `shopping-mcp`; results render as product cards you can add to the cart
directly, and the cart panel builds a mock order.

**`place_order` is never offered to the model.** Only the Approve / Reject
buttons on the confirmation card can reach it — the confirm gate
[docs/requirement.md](docs/requirement.md) asks for.

### Chat history

The transcript is stored in Postgres and restored when you sign in again, so a
`docker compose restart chat` (or a browser reload) no longer loses the
conversation:

```bash
docker exec printing-service-postgres-1 psql -U raksul -d stockroom -c \
  "SELECT role, tool_name, left(content, 60) FROM chat_messages ORDER BY id"
```

It is written through the Go API at `/api/v1/chat/messages`, not by the Python
service directly — `backend-ops` stays the only process that touches SQL.
Stored tool rows keep the structured MCP result in a `payload` column, which is
what lets product cards re-render after a reload instead of collapsing to a bare
"used a tool" note.

Two things worth knowing:

- **The model resumes with prose only.** Ollama requires a tool message to follow
  the assistant message carrying the matching `tool_calls`, and those call ids do
  not survive a restart — so replayed history gives the model the conversation,
  not the raw tool results. You may see it re-run a tool it had already run.
- **"New chat"** (`DELETE /api/chat/messages`) clears the stored transcript and
  the model's context together. Signing out does not: sign back in with the same
  email and the conversation returns.

Persistence is best-effort by design. If the history endpoint is unreachable the
chat still answers — it just logs a warning and forgets afterwards.

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

```bash
docker compose down                 # removes containers, preserves all data
# Or stop without removing containers:
docker compose stop
```

MCP stdio processes run inside existing containers, so stopping those containers
also closes their sessions. Avoid `down -v` unless you intend to delete database,
images, and the downloaded model. Fixed MCP container names allow path-free client
configuration. To run a second stack, set `SHOPPING_MCP_CONTAINER_NAME`,
`ADMIN_MCP_CONTAINER_NAME`, and all host ports separately, and use another Compose
project name. Update that stack's MCP client names accordingly.

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
docker compose exec -T postgres psql -U raksul -d stockroom -c "\dt"
docker compose exec -T postgres psql -U raksul -d stockroom -c \
  "SELECT name, base_price_jpy FROM products LIMIT 5;"
```

---

## Configuration

Defaults work with no `.env` file. Override by exporting before
`docker compose up`:

| Variable | Default | Effect |
|---|---|---|
| `SHOP_ENABLED` | `true` | `false` hides the storefront from customers |
| `STOCKROOM_ADMIN_EMAILS` | `admin@gmail.com` | Comma-separated; granted admin at startup |
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

**API reports missing tables/bucket** — confirm that Compose is using the database
and MinIO volume holding your existing data. Automatic schema initialization is
disabled. For a new empty installation, run the manual `crawler bootstrap` command
above. Do not run `init-db` against data you need to keep.

**Crawler says the catalog is empty** — crawl manually when you want to import
products; normal service startup does not run it.

**Chat is unhealthy** — inspect `docker compose logs model-init chat`. `/healthz`
checks both the API and the configured model in Ollama, not just its TCP port.

**Admin dashboard or MCP tools return 403** — either you signed in as a
customer, or `init-db` dropped `users` while `api` kept running, so nobody holds
`is_admin` any more. Sign in as `admin@gmail.com`, and run
`docker compose restart api` to re-grant admin from `STOCKROOM_ADMIN_EMAILS`.

**Images are broken in the shop** — MinIO is down or the crawl never ran.
`docker compose ps` and `docker compose run --rm crawler stats`.

---

## Working on the code

[CLAUDE.md](CLAUDE.md) is the guide for changing anything — module layout, the
ordering and pricing invariants, and the traps that have already bitten.

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
  "$(pwd)/plugins/raksul-catalog"

/opt/homebrew/bin/codex plugin add \
  raksul-catalog@raksul-printing
```

Sau đó thoát hoàn toàn ChatGPT Desktop, mở lại và tạo chat mới. Không cần chạy
hai lệnh này khi chỉ crawl thêm dữ liệu hoặc cập nhật dữ liệu PostgreSQL/MinIO.

## Docker verification

```bash
make test                 # Python unit tests and Go checks in containers
make test-e2e             # uses the running API and crawled catalog
make test-chat-e2e        # uses the running chat and installed Ollama model
docker compose run --rm --build -e DOCKER_MCP_E2E=1 test-python python -m pytest -q tests/test_docker_mcp.py
docker compose exec -T shopping-mcp python - < docker/check-mcp.py
docker compose exec -T -e MCP_CHECK_MODULE=stockroom_ops.server mcp python - < docker/check-mcp.py
# Bootstrap integration tests create/drop their own disposable databases:
docker compose run --rm --build -e BOOTSTRAP_TEST_DATABASE_URL=postgresql://raksul:raksul_password@postgres:5432/stockroom test-python python -m pytest -q tests/test_docker_bootstrap.py
```

The `Makefile` is optional convenience; every command it runs is Docker Compose.
