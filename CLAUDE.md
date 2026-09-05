# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two stacks live here

**Active work — the stockroom PoC.** [docs/requirement.md](docs/requirement.md) specifies a conversational-commerce PoC over MCP Apps. Its pieces:

- [backend-ops/schema.sql](backend-ops/schema.sql) — the PoC schema (users, categories, products, product_images, product_sizes, cart_items, orders, order_items). Hand-written DDL, no migration tool; it is the single source of truth.
- [crawler/](crawler/) — a **standalone** Python service that crawls stockroom.raksul.com into that schema and pushes images to MinIO. Own venv, own `requirements.txt`, own `.env`. See [crawler/README.md](crawler/README.md).
- A Go service (not yet written) will read those tables and proxy `GET /media/{key}` to MinIO; a separate MCP server calls it. That two-process split is a deliberate deviation from requirement.md, which specifies tools running SQL directly in a single MCP server.

`docker compose up -d` at the root now serves this stack: PostgreSQL 17 with database **`stockroom`** plus MinIO, both bound to `127.0.0.1` only.

**Prior work — the apparel MVP.** [app/](app/) crawls apparel.raksul.com into `raksul_db` via SQLAlchemy and serves a chat-only MCP server. It is a different site, schema, and product. Its database no longer exists in the compose file, so its CLI will fail until `raksul_db` is recreated. Do not extend it for stockroom work.

## Commands (apparel MVP — see crawler/README.md for the stockroom stack)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d                      # PostgreSQL 17 on :5432 (raksul/raksul_password/raksul_db)
python -m app.cli init-db                 # Base.metadata.create_all — no migration tool
python -m app.cli crawl [--category SLUG] [--limit N] [--config PATH]
python -m app.cli stats
python -m app.cli categories [--industry SLUG]
python -m app.cli search --query vest --industry food_service --max-price 4000 --limit 5
python -m app.cli --verbose <command>     # DEBUG logging
```

Tests:

```bash
pytest                                    # unit tests only; DB tests skip without TEST_DATABASE_URL
TEST_DATABASE_URL=postgresql+psycopg://raksul:raksul_password@localhost:5432/raksul_db pytest
pytest tests/test_parser.py::test_normalized_product_from_jsonld
```

`tests/test_repository.py` calls `Base.metadata.drop_all` on its target database — point `TEST_DATABASE_URL` at a throwaway DB, never at a database holding a real crawl.

MCP server:

```bash
./.venv/bin/python -m app.mcp_server.server                            # stdio
./.venv/bin/python -m app.mcp_server.server --transport streamable-http  # http://127.0.0.1:8000/mcp
npx @modelcontextprotocol/inspector@latest ./.venv/bin/python -m app.mcp_server.server
```

There is no linter or formatter configured; `pyproject.toml` holds only pytest config.

## Architecture

Layers, each depending only on the one below it:

`app/cli.py` and `app/mcp_server/` → `app/services/product_service.py` → `app/repositories/product_repository.py` → `app/database/models.py` → PostgreSQL. The crawler (`app/crawler/`) writes into the same repository.

The service layer is the read boundary: it accepts only keyword filters and forwards them to repository methods, so callers can never pass SQL. Both the CLI and the MCP tool handlers construct `ProductService(ProductRepository(session))` inside a `session_scope()` block.

Crawl is two-stage. Stage A ([discovery.py](app/crawler/discovery.py)) fetches each enabled category page and extracts links matching `/(work|clinic|food|casual)-uniform/products/<digits>`, canonicalizing to scheme+path with query and fragment stripped, then deduplicating. Stage B ([parser.py](app/crawler/parser.py)) fetches each product page and prefers Product JSON-LD (including `@graph`), falling back to OpenGraph meta, then `<h1>`, then page text; the URL supplies `source_product_id`. `printing_available` is only set to `True` when the page text contains 印刷 or プリント — it is never set to `False`. Colors, sizes, and stock are left empty/`NULL` rather than inferred.

[runner.py](app/crawler/runner.py) enforces the caps: a per-category `max_products`, a global `remaining` budget, and a cross-category `seen` URL set so the same product is not fetched twice. Failures are logged and counted in `CrawlSummary`, never raised.

## Things that will bite you

- **`.env.example` is referenced by the README but does not exist in the repo.** `DATABASE_URL` is required and raises at `make_engine()` if unset. Create `.env` by hand (it is gitignored).
- **`MAX_PRODUCTS_TOTAL` and `REQUEST_DELAY_SECONDS` are module-level constants in [config.py](app/crawler/config.py) read at import time, before `load_dotenv()` runs in [connection.py](app/database/connection.py).** Setting them in `.env` has no effect through the CLI; export them in the shell instead. `MAX_PRODUCTS_PER_CATEGORY` is read inside `load_categories()` and so does work from `.env`.
- **Upsert preserves existing data.** [`ProductRepository.upsert`](app/repositories/product_repository.py) drops `None` values from the `ON CONFLICT (product_url) DO UPDATE` set clause (except `colors`/`sizes`), so a later parse that fails to find a description will not blank the stored one. Price history rows are appended only on insert or an actual price change.
- **`robots.txt` failure is treated as denial.** `HttpClient.robots_allowed` returns `False` if robots cannot be read, which aborts the crawl — intentional, not a bug.
- **`categories.json` is the crawl whitelist.** Each entry needs a URL reached through RAKSUL's own navigation, unique `industry`/`category` slugs, and a small `max_products`. `--category` matches the `category` slug, which is not unique across industries (`t_shirts` appears twice), so it selects every industry using that slug.
- **The README's Architecture section says there is no MCP server yet; that is stale** — [app/mcp_server/](app/mcp_server/) exists and is described further down the same README. The root [README.md](README.md) documents only the apparel MVP and predates the stockroom stack entirely.

## stockroom stack — things that will bite you

- **`/products/{id}` 404s without `?sku=`.** The SKU query parameter is mandatory on stockroom product pages.
- **Never read prices from the Nuxt payload.** It uses index-based dereferencing, so `"price":181` means *element 181 of a flat array*, not ¥181. Only the schema.org `Product` JSON-LD block has real numbers — that is all [crawler/stockroom_crawler/parser.py](crawler/stockroom_crawler/parser.py) parses.
- **Prices are tiered and fractional** (`lowPrice` bulk vs `highPrice` at minimum order, values like 916.5). The schema stores one integer, so the crawler keeps `ceil(highPrice)`. There is no quantity model.
- **A bare L1 category page lists no products** — it is a hub of subcategory tiles. Discovery must walk depth ≥ 2. Only the 16 L1 categories are persisted; products attach to their L1 ancestor.
- **`init-db` drops every table**, `users` and `orders` included. Use `crawl --reset` to re-import just the catalog.
- **The crawler is a separate service.** It has its own `crawler/.venv` and does not share the root project's dependencies; it needs only psycopg, minio, and requests. Build that venv with `python3.13` (Homebrew): macOS's `/usr/bin/python3` is 3.9 on LibreSSL, which makes urllib3 v2 print a `NotOpenSSLWarning` on every command.
- **schema.sql had two defects** now fixed: a `UNIQUE(product_id, display_order)` referencing a column that was never defined, and a trailing comma before `)` in `product_sizes`. Either one makes the whole file fail to execute.

## MCP tool contract

Every handler in [tools.py](app/mcp_server/tools.py) returns a `scope` block marking the data as an incomplete, non-real-time snapshot, and an empty search returns `status: "no_match_in_current_catalog"` with an explicit message that absence from the snapshot is not absence from RAKSUL. Preserve that framing when adding tools — it is the point of the design, not boilerplate. All tools are annotated read-only and must stay read-only; `get_catalog_info` names `live_stock`, `shipping_fee`, `delivery_date`, `printing_quote`, and `real_time_price` as deliberately unsupported.

`app/services/product_service.py` also carries `is_product_stale(product, max_age_hours=24)`, currently unused — it is the intended hook for a future scoped price-refresh policy.
