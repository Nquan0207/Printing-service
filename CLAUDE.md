# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python MVP that crawls a bounded sample of RAKSUL Apparel products, normalizes them into PostgreSQL 17, and exposes read-only retrieval through a CLI and an MCP server. Everything is deliberately small and conservative — the crawler is capped by design, and the MCP tools advertise the catalog as an incomplete, non-real-time snapshot.

## Commands

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
- **The README's Architecture section says there is no MCP server yet; that is stale** — [app/mcp_server/](app/mcp_server/) exists and is described further down the same README.
- `go-backend/` is an empty directory on the current `backend/schema` branch.

## MCP tool contract

Every handler in [tools.py](app/mcp_server/tools.py) returns a `scope` block marking the data as an incomplete, non-real-time snapshot, and an empty search returns `status: "no_match_in_current_catalog"` with an explicit message that absence from the snapshot is not absence from RAKSUL. Preserve that framing when adding tools — it is the point of the design, not boilerplate. All tools are annotated read-only and must stay read-only; `get_catalog_info` names `live_stock`, `shipping_fee`, `delivery_date`, `printing_quote`, and `real_time_price` as deliberately unsupported.

`app/services/product_service.py` also carries `is_product_stale(product, max_age_hours=24)`, currently unused — it is the intended hook for a future scoped price-refresh policy.
