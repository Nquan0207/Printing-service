# RAKSUL Product Catalog MVP

> **Note:** this documents the earlier *apparel* MVP in [app/](app/), which targets
> apparel.raksul.com and its own `raksul_db`. The active work is the stockroom
> PoC — see [crawler/README.md](crawler/README.md) for the crawler and
> [docs/requirement.md](docs/requirement.md) for the spec. `docker compose up -d`
> now provisions the **`stockroom`** database and MinIO, not `raksul_db`.

A conservative two-stage crawler that discovers a small, configurable sample of RAKSUL Apparel products, normalizes product pages, upserts them into PostgreSQL 17, and exposes database-backed retrieval through a service layer and CLI. It intentionally does not include an MCP server yet.

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
Future MCP Server
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

## Known limitations and MCP next step

RAKSUL does not expose every color, size, or stock combination consistently in static semantic markup. Those fields remain `[]`/`NULL` instead of being inferred. Price is the displayed current/base price and may vary by color, size, quantity, tax, or campaign. Printing availability is only set when the page explicitly references printing. Category filters and URLs may evolve and should be smoke-tested before a production run.

The next enhancement can add a carefully scoped `get_price` refresh policy using
`is_product_stale`. MCP transport remains separate from crawler parsing.

## MCP server

The read-only MCP adapter exposes `search_products`, `get_product`,
`list_categories`, and `get_catalog_info`. Every result identifies the database
as an incomplete, non-real-time snapshot.

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

ChatGPT developer mode requires a reachable HTTPS Streamable HTTP endpoint
ending in `/mcp`; localhost must be exposed through an approved development
tunnel before it can be added there.
