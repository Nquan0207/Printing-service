# RAKSUL Product Catalog MVP

A conservative two-stage crawler that discovers a small, configurable sample of RAKSUL Apparel products, normalizes product pages, upserts them into PostgreSQL 17, and exposes database-backed retrieval through a service layer, CLI, and read-only MCP server.

## Architecture

```text
RAKSUL Apparel
      |
      v
Crawler (discovery + detail fetch)
      |
      v
Parser / Normalizer
      |
      v
PostgreSQL
      |
      v
Repository
      |
      v
Product Service
      |
      v
MCP Server
```

Python 3.11+ is recommended. The HTTP client uses a meaningful user agent, checks `robots.txt`, retries only 429/temporary server failures, and waits between product requests. The crawler has both per-category and total hard limits.

## Setup and commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
python -m app.cli init-db
python -m app.cli crawl
```

Useful scoped commands:

```bash
python -m app.cli crawl --category bib_aprons
python -m app.cli crawl --limit 20
python -m app.cli stats
python -m app.cli categories --industry food_service
python -m app.cli search --query "vest" --limit 5
python -m app.cli search --industry food_service --max-price 4000
```

Run deterministic unit tests with `pytest`. PostgreSQL integration tests (UPSERT, price history, and every search filter) are enabled with:

```bash
TEST_DATABASE_URL=postgresql+psycopg://raksul:raksul_password@localhost:5432/raksul_db pytest
```

The integration suite recreates its target schema, so use a dedicated test database outside local throwaway development.

## Configuration and data flow

The editable [categories.json](categories.json) whitelist contains industry/category labels, verified RAKSUL URL families, enable flags, and limits. To add a category, copy an entry, use the URL reached through RAKSUL's own navigation, choose unique slugs, and keep its limit small. Environment variables are documented in `.env.example`; credentials are never stored in Python.

Stage A fetches each enabled category, extracts stable `/casual-uniform/products/<id>` links, canonicalizes and deduplicates them, and associates taxonomy. Stage B fetches selected product pages and prefers Product JSON-LD, semantic metadata, stable URL IDs, and only then page text. The repository uses PostgreSQL `ON CONFLICT (product_url) DO UPDATE`, preserves existing optional values when a later parse returns `NULL`, and records price history only on creation or a price change.

Tables are `industries`, `categories`, `products`, and `product_price_history`. Colors and sizes are JSONB, with a GIN color index. Search supports text, taxonomy, brand, color, and price filters; the service prevents callers from issuing raw SQL.

## Known limitations and next steps

RAKSUL does not expose every color, size, or stock combination consistently in static semantic markup. Those fields remain `[]`/`NULL` instead of being inferred. Price is the displayed current/base price and may vary by color, size, quantity, tax, or campaign. Printing availability is only set when the page explicitly references printing. Category filters and URLs may evolve and should be smoke-tested before a production run.

The next enhancement can add a carefully scoped `get_price` refresh policy using
`is_product_stale`. MCP transport remains separate from crawler parsing.

## MCP server

The MCP adapter exposes catalog search plus an embedded, database-backed mock
storefront. The runtime shopping flow never navigates to RAKSUL or another
supplier website: product browsing uses only the PostgreSQL snapshot. The
supplier site is accessed only by the offline crawler.

The mini-app supports a 24-hour local mock session identified by name and email,
session-owned carts, and an explicit approve-or-reject simulated payment. A
checkout confirmation expires after 15 minutes. It never asks for a password,
payment credentials, or moves money.

Start it locally over stdio:

```bash
./.venv/bin/python -m app.mcp_server.server
```

Start Streamable HTTP on `http://127.0.0.1:8000/mcp`:

```bash
./.venv/bin/python -m app.mcp_server.server --transport streamable-http
```

Inspect the local server with:

```bash
npx @modelcontextprotocol/inspector@latest \
  ./.venv/bin/python -m app.mcp_server.server
```

Example Claude Desktop stdio configuration (use absolute paths):

```json
{
  "mcpServers": {
    "raksul-catalog": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "app.mcp_server.server"],
      "cwd": "/absolute/path/to/printing service"
    }
  }
}
```

## Import RAKSUL Catalog into ChatGPT

Complete the project setup first. PostgreSQL must be running and the catalog
must contain data before ChatGPT calls the MCP tools:

```bash
docker compose up -d
./.venv/bin/python -m app.cli init-db
./.venv/bin/python -m app.cli crawl
./.venv/bin/python -m app.cli stats
```

Use one of the following connection methods:

- **ChatGPT desktop on the same computer:** package the stdio server as a local
  plugin. This is the simplest development setup and keeps the server local.
- **ChatGPT web or another computer:** use OpenAI Secure MCP Tunnel. Do not
  expose this unauthenticated server directly to the public internet.

### Option A: ChatGPT desktop local plugin

1. Install the official OpenAI Codex CLI with Homebrew:

   ```bash
   brew install --cask codex
   "$(brew --prefix)/bin/codex" --version
   ```

   Do not use `pip install codex`. The PyPI package named `codex` is an
   unrelated Python application. In particular, an activated virtual
   environment may put `.venv/bin/codex` before the OpenAI CLI on `PATH`.
   The commands below use the Homebrew executable explicitly to avoid that
   name collision.

2. Get the absolute project path:

   ```bash
   pwd
   ```

3. Update `plugins/raksul-catalog/.mcp.json` so that `command` points to this
   computer's `<PROJECT_PATH>/.venv/bin/python` and `PYTHONPATH` is the same
   `<PROJECT_PATH>`.

4. Register this repository as a local plugin marketplace. Replace
   `<PROJECT_PATH>` with the output from `pwd`:

   ```bash
   "$(brew --prefix)/bin/codex" plugin marketplace add "<PROJECT_PATH>"
   "$(brew --prefix)/bin/codex" plugin marketplace list
   ```

   The expected marketplace name is `raksul-printing`.

5. Install the plugin and confirm that it is enabled:

   ```bash
   "$(brew --prefix)/bin/codex" plugin add raksul-catalog@raksul-printing
   "$(brew --prefix)/bin/codex" plugin list
   ```

   The expected status is `installed, enabled`.

6. After changing `plugin.json` or `.mcp.json`, update the manifest
   cachebuster and reinstall:

   ```bash
   python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
     "<PROJECT_PATH>/plugins/raksul-catalog"
   "$(brew --prefix)/bin/codex" plugin add raksul-catalog@raksul-printing
   ```

7. Restart the ChatGPT desktop app. Open **Plugins Directory**, choose the
   **Raksul Printing** source, and enable **RAKSUL Catalog**. Start a new chat
   after installing or updating the plugin.

8. Start a new conversation on a ChatGPT surface that supports embedded MCP
   Apps and ask:

   ```text
   Render the embedded RAKSUL database storefront here. Do not open any external website.
   ```

   The expected flow is mock sign-in, database product search, cart management,
   explicit approval or rejection, then a mock receipt or cart retry. The Codex
   built-in browser is not a storefront fallback; if a client cannot render the
   `ui://widget/raksul-storefront.html` resource, it should use structured tool
   results instead of opening the supplier website.

### Option B: ChatGPT web with Secure MCP Tunnel

Each developer needs access to an OpenAI Platform organization with
**Tunnels Read + Use** permission and a ChatGPT workspace that permits
Developer mode. Use a tunnel associated with that organization/workspace; do
not copy another developer's runtime API key into this repository.

1. Create or select a tunnel in OpenAI Platform tunnel settings. Record its
   `tunnel_id`, download `tunnel-client`, and create a runtime API key.

2. Export the runtime key in the terminal that will run the client:

   ```bash
   export CONTROL_PLANE_API_KEY="<YOUR_RUNTIME_API_KEY>"
   ```

3. Initialize a local stdio profile. Replace all placeholders with paths and
   IDs from your own machine and OpenAI organization:

   ```bash
   <PATH_TO_TUNNEL_CLIENT> init \
     --sample sample_mcp_stdio_local \
     --profile raksul-local \
     --tunnel-id <YOUR_TUNNEL_ID> \
     --mcp-command "/usr/bin/env PYTHONPATH=<PROJECT_PATH> <PROJECT_PATH>/.venv/bin/python -m app.mcp_server.server"
   ```

4. Diagnose the profile, then keep the tunnel running:

   ```bash
   <PATH_TO_TUNNEL_CLIENT> doctor --profile raksul-local --explain
   <PATH_TO_TUNNEL_CLIENT> run --profile raksul-local
   ```

5. In ChatGPT, open **Settings → Security and login** and enable
   **Developer mode**. Then open the ChatGPT **Plugins** page, select **+**, and
   enter:

   - Name: `RAKSUL Catalog`
   - Description: `Search a limited, non-real-time RAKSUL Apparel snapshot.`
   - Connection: **Tunnel**
   - Tunnel: select or enter your `tunnel_id`

6. Create the connection and confirm that ChatGPT discovers these tools:

   - `search_products`
   - `get_product`
   - `list_categories`
   - `get_catalog_info`
   - `open_storefront`
   - `mock_sign_in`
   - `get_mock_session`
   - `create_cart`, `get_cart`, `add_cart_item`, `update_cart_item`, `remove_cart_item`
   - `create_mock_checkout`, `get_mock_order`, `decide_mock_payment`

The tunnel is suitable for private development and workspace testing. A public
plugin submission requires a stable public HTTPS MCP endpoint and appropriate
authentication instead.

### Verify the connection

Start a new chat and try these prompts:

```text
Use RAKSUL Catalog to show the catalog coverage.
Use RAKSUL Catalog to list the available categories.
Use RAKSUL Catalog to find up to five apparel products.
Render the embedded RAKSUL database storefront here. Do not open any external website.
```

Expected catalog values depend on the latest crawl. Every result should state
that the catalog is an incomplete, non-real-time snapshot.

### Mock storefront flow

The `open_storefront` tool renders `ui://widget/raksul-storefront.html` inside a
compatible MCP Apps host. Mock-sign-in with a name and email, search for a
database product, select any required color and size, choose a quantity, and add
it to the session-owned cart. Continue to mock payment and explicitly select
**Approve mock payment** or **Reject mock payment**. The 15-minute confirmation
challenge is validated server-side. Approval creates a stored mock receipt;
rejection preserves the cart for editing and retry. No real checkout occurs.

After pulling storefront model changes, create the cart, order, mock-customer,
session-ownership, and confirmation tables:

```bash
./.venv/bin/python -m app.cli init-db
```

After changing MCP tools, UI resources, or plugin metadata, update and reinstall
the local plugin before starting a new chat:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
  "$(pwd)/plugins/raksul-catalog"
"$(brew --prefix)/bin/codex" plugin add raksul-catalog@raksul-printing
```

### Troubleshooting

- **`DATABASE_URL is required`:** create `.env` in the project root and set
  the PostgreSQL SQLAlchemy URL.
- **`No module named app`:** use an absolute project path for `PYTHONPATH`.
- **Database connection refused:** run `docker compose up -d`, then retry
  `./.venv/bin/python -m app.cli stats`.
- **Tunnel reports `401 Unauthorized`:** the runtime key is invalid, belongs
  to a different organization, or lacks **Tunnels Read + Use** permission.
- **ChatGPT cannot find the tunnel:** verify that the tunnel is associated with
  the target ChatGPT workspace and that `tunnel-client run` is still active.
- **Tools changed but ChatGPT shows old metadata:** restart the local plugin or
  select **Refresh** on the Developer-mode connection, then start a new chat.

Official references:

- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
