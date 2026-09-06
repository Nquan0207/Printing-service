# Setup

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
docker compose run --rm crawler crawl       # ~25 min: 70 products, 8 categories
docker compose run --rm crawler stats       # what landed
```

`crawl` commits per product, so you can stop it (Ctrl-C) and re-run it later
without losing what it already imported.

Faster for a first look:

```bash
docker compose run --rm -e CRAWL_MAX_PRODUCTS=10 crawler crawl
```

> `init-db` **drops every table**, users and orders included. To re-import only
> the catalog later, use `crawler crawl --reset`.

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

`docker compose up -d` must still be running either way — the MCP server reads
everything through the Go API.

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

Admin is granted **only at API startup from configuration** — no HTTP route can
hand it out.

---

## Troubleshooting

**`address already in use`** — something is already on that port. Find it with
`lsof -nP -iTCP:3001 -sTCP:LISTEN`, or `docker compose down` first.

**`web` is healthy but shows nothing** — check `api` is healthy too; the SPA
loads but every request 502s if the API is down.

**Crawler says the catalog is empty** — run `init-db` before `crawl`.

**Admin dashboard returns 403** — you signed in as a customer. Use
`admin@stockroom.local`, or add your address to `STOCKROOM_ADMIN_EMAILS` and
restart `api`.

**Images are broken in the shop** — MinIO is down or the crawl never ran.
`docker compose ps` and `docker compose run --rm crawler stats`.

---

## What is not containerized

[app/](app/) is an earlier, unrelated MVP that crawls apparel.raksul.com. It is
not part of this stack and its database no longer exists in the compose file.
Ignore it.
