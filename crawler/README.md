## Run with Docker (partner setup)

From the repository root, `docker compose up -d --build --wait` starts services
using existing data. Schema preparation and crawling are manual only. For a new
empty installation, run `docker compose run --rm --build crawler bootstrap` first.

```bash
docker compose run --rm crawler stats
docker compose run --rm crawler crawl
```

`crawler init-db` is destructive; the manual `crawler bootstrap` command prepares
a new schema and bucket without dropping existing data. For a deliberate reset, use `make reset-db CONFIRM_RESET=1`.
The instructions below are optional **native development** instructions, not
requirements for Docker users. Native settings are in `crawler/.env.example`.

---

# Stockroom Crawler

A standalone service that crawls [stockroom.raksul.com](https://stockroom.raksul.com)
(RAKSUL Business Mall) and imports its catalog into the PoC Postgres schema,
with product images pushed to MinIO.

It runs **once, offline** to populate the database. The Go service and the MCP
server read what it wrote; nothing at request time depends on this crawler.

```
stockroom.raksul.com          sitemap -> category pages -> product pages
        |
        v
  stockroom_crawler           JSON-LD parse, S/M/L mapping
        |
   +----+--------+
   v             v
Postgres       MinIO          rows + image objects
   |             ^
   v             |
Go service ------+            reads rows, proxies GET /media/{key}
```

## What it produces

Per the PoC budget: **70 products**, each with exactly **3 sizes (S/M/L)** and
**up to 3 images**, spread across **8** of the 16 top-level categories. Both
numbers are configurable -- see [Choosing how much to crawl](#choosing-how-much-to-crawl).

| Table | Written | Notes |
|---|---|---|
| `categories` | one row per crawled top-level slug | Subcategories are traversed but not stored; products attach to their L1 ancestor. |
| `products` | one per `/products/{id}` | `base_price_jpy` is the cheapest variant. |
| `product_sizes` | 3 per product | `S`/`M`/`L` by ascending price; `price_adjustment_jpy` is the delta from base. |
| `product_images` | up to 3 per product | Stores the MinIO **object key**, never a URL. |

`users`, `cart_items`, `orders`, and `order_items` are left untouched — they
belong to the Go service.

## Setup

From the repo root, start Postgres and MinIO (both bind to `127.0.0.1` only):

```bash
docker compose up -d
```

Then, in this directory, create and **activate** the virtualenv. Use Homebrew
Python 3.13 — macOS's system `/usr/bin/python3` is 3.9 and linked against
LibreSSL, which makes urllib3 warn on every command:

```bash
cd crawler
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Your prompt should now be prefixed with `(.venv)`. Every command below assumes
that active virtualenv — run `deactivate` when you are done, and re-run
`source .venv/bin/activate` in any new shell.

```bash
python -c "import minio, psycopg; print('ready')"   # sanity check
```

The crawler keeps its **own** virtualenv and dependencies — it does not share
the root project's `.venv`, and it needs only psycopg, minio, and requests.

## Crawl and import

With the virtualenv active (`(.venv)` in your prompt):

```bash
# 1. Create the tables from backend-ops/schema.sql (DROPs any existing ones)
python -m stockroom_crawler.cli init-db

# 2. Crawl and import (defaults: 70 products across 8 categories)
python -m stockroom_crawler.cli crawl

# 3. Check what landed
python -m stockroom_crawler.cli stats
```

A 70-product run takes roughly **25–30 minutes** — about 3–4 minutes per
category. Most of that is discovery: subcategory pages are fetched at a 1.25 s
delay while hunting for products that carry at least three SKUs. Everything is
committed per product, so an interrupted run keeps what it already imported and
`crawl` can simply be re-run.

To trade politeness for speed, lower the delay — `CRAWL_REQUEST_DELAY=0.6`
roughly halves the wall time and stays well within reasonable limits for a site
this size.

### Choosing how much to crawl

Two knobs in `.env` control the size of a run — the defaults are 70 products
across 8 categories:

```bash
CRAWL_MAX_PRODUCTS=70      # total products
CRAWL_MAX_CATEGORIES=8     # how many top-level categories to draw from
```

The budget is divided across the selected categories and **re-divided as the
run proceeds**, so the total is met exactly and a thin category's shortfall is
picked up by later ones:

| Products | Categories | Per-category plan |
|---|---|---|
| 70 | 8 | `9, 9, 9, 9, 9, 9, 8, 8` |
| 70 | 7 | `10, 10, 10, 10, 10, 10, 10` |
| 150 | 16 | `10, 10, 10, 10, 10, 10, 9, …` |

Categories are taken from the top of the whitelist. To pick *which* ones
instead of just how many, set `CRAWL_CATEGORIES` — it overrides the default
order, and the count still caps it:

```bash
CRAWL_CATEGORIES=store_supplies,daily_life_goods,drinks_food
```

An unknown slug fails fast with the list of valid ones. Both knobs have
per-run flags, so you can experiment without editing `.env`:

```bash
python -m stockroom_crawler.cli crawl --limit 70 --categories 8
```

If the budget is smaller than the category count, the run simply stops once
it is spent — `--limit 5 --categories 8` visits 5 categories, one product each.

### Useful variations

```bash
# One category only, handy while iterating
python -m stockroom_crawler.cli crawl --category store_supplies --limit 5

# Re-import from scratch (truncates crawled tables, keeps users/orders)
python -m stockroom_crawler.cli crawl --reset

# List the category whitelist (no DB needed)
python -m stockroom_crawler.cli categories

# Verbose request logging
python -m stockroom_crawler.cli --verbose crawl --limit 3
```

## Verifying the import

```bash
# Rows per table
python -m stockroom_crawler.cli stats

# Products with their S/M/L ladder and computed unit prices
docker exec printing-service-postgres-1 psql -U raksul -d stockroom -c "
SELECT p.name, s.size_name, p.base_price_jpy + s.price_adjustment_jpy AS unit_jpy
FROM products p JOIN product_sizes s ON s.product_id = p.id
ORDER BY p.id, s.price_adjustment_jpy LIMIT 12;"

# Image objects in MinIO
docker exec printing-service-minio-1 \
  mc alias set local http://127.0.0.1:9000 minioadmin minioadmin
docker exec printing-service-minio-1 mc ls --recursive local/stockroom-media | head
```

The MinIO console is at <http://127.0.0.1:9001> (`minioadmin` / `minioadmin`).
The bucket has **no public policy** — the Go service is its only reader.

## Configuration

All settings come from `.env` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `STOCKROOM_DATABASE_URL` | `postgresql://raksul:raksul_password@127.0.0.1:5432/stockroom` | Required; no default in code. |
| `MINIO_ENDPOINT` | `127.0.0.1:9000` | S3 API address. |
| `MINIO_BUCKET` | `stockroom-media` | Created on first run if absent. |
| `CRAWL_MAX_PRODUCTS` | `70` | Total products across the selected categories. |
| `CRAWL_MAX_CATEGORIES` | `8` | How many top-level categories to draw from. |
| `CRAWL_CATEGORIES` | _(unset)_ | Comma-separated slugs; overrides the default ordering. |
| `CRAWL_SIZES_PER_PRODUCT` | `3` | Variants needed to earn S/M/L labels. |
| `CRAWL_MAX_IMAGES` | `3` | Cap per product. |
| `CRAWL_REQUEST_DELAY` | `1.25` | Seconds between product-page requests. |

## How it works

**Discovery.** `robots.txt` is honoured and read once; `/search`, `/cart`, and
`/collections` are disallowed and never touched. The sitemap index yields
`sitemap_general.xml` (~3,800 category pages), which is grouped by top-level
slug. A bare L1 page is skipped — it is a hub of subcategory tiles and lists no
products — so discovery walks that L1's subcategory pages shallowest-first
until it has enough products.

**Parsing.** Each `/products/{id}?sku={sku}` page is server-rendered and carries
one schema.org `Product` JSON-LD block, which is the only thing parsed.

**Sizes.** Three variants at *distinct* prices are fetched per product, sorted
ascending, and labelled S/M/L. A product offering fewer than three usable
variants is skipped rather than padded.

**Images.** URLs are collected across the product's variants, deduplicated, and
the first three are downloaded and put to MinIO under a content-addressed key
(`products/{id}/{sha256}.jpg`), so re-crawling overwrites in place.

## Tests

```bash
python -m pytest
```

Fourteen tests run against trimmed fixtures captured from real pages — no network
and no database required.

## Gotchas

- **`/products/{id}` without `?sku=` returns a 404 page.** The SKU parameter is
  mandatory.
- **Never parse the Nuxt payload for prices.** It uses index-based
  dereferencing, so `"price":181` means "element 181 of a flat array", not
  ¥181. Only the JSON-LD block carries real numbers.
- **Prices are tiered and fractional.** stockroom quotes `lowPrice` (bulk) and
  `highPrice` (minimum order). The schema has one integer price, so the crawler
  stores `ceil(highPrice)` — what a buyer pays for the smallest order. The
  quantity ladder is not modelled.
- **`init-db` drops every table**, including `users` and `orders`. Use
  `crawl --reset` to re-import the catalog without touching those.
- **Popular products can have hundreds of SKUs** (product 4734 has 309), and a
  product page does not list its siblings. SKU candidates come from category
  listing pages, capped at three.
- **Build the venv with Homebrew Python, not macOS's `/usr/bin/python3`.** The
  system 3.9 is linked against LibreSSL, and urllib3 v2 warns
  (`NotOpenSSLWarning`) on every command because it only supports OpenSSL
  1.1.1+. Harmless, but noisy — `brew install python@3.13` avoids it.
