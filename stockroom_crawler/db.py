"""Writes into the go-backend schema.

schema.sql is the single source of truth, so this talks raw SQL through
psycopg rather than mirroring the DDL in an ORM.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)

# stockroom_crawler/db.py -> repo root -> go-backend/schema.sql
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "go-backend" / "schema.sql"

# Crawler-owned tables only; users/cart/orders belong to the Go service.
_CRAWLED_TABLES = ("product_images", "product_sizes", "products", "categories")


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, autocommit=False)


def apply_schema(connection: psycopg.Connection) -> None:
    """Create every table from scratch, dropping any existing ones."""
    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    with connection.cursor() as cur:
        cur.execute(
            "DROP TABLE IF EXISTS order_items, orders, cart_items, product_sizes,"
            " product_images, products, categories, users CASCADE"
        )
        cur.execute(ddl)
    connection.commit()
    log.info("Applied schema from %s", SCHEMA_PATH)


def reset_catalog(connection: psycopg.Connection) -> None:
    """Clear catalog and dependent commerce rows while preserving users."""
    with connection.cursor() as cur:
        cur.execute(
            "TRUNCATE order_items, orders, cart_items, "
            f"{', '.join(_CRAWLED_TABLES)} RESTART IDENTITY CASCADE"
        )
    connection.commit()


def upsert_category(connection: psycopg.Connection, slug: str, name: str) -> int:
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO categories (slug, name) VALUES (%s, %s)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (slug, name),
        )
        return cur.fetchone()[0]


def upsert_product(
    connection: psycopg.Connection,
    *,
    category_id: int,
    source_product_id: str,
    name: str,
    brand: str | None,
    description: str | None,
    base_price_jpy: int,
) -> int:
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO products (category_id, source_product_id, name, brand,
                                  description, base_price_jpy)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_product_id) DO UPDATE SET
                category_id    = EXCLUDED.category_id,
                name           = EXCLUDED.name,
                brand          = COALESCE(EXCLUDED.brand, products.brand),
                description    = COALESCE(EXCLUDED.description, products.description),
                base_price_jpy = EXCLUDED.base_price_jpy,
                updated_at     = NOW()
            RETURNING id
            """,
            (
                category_id,
                source_product_id,
                name[:500],
                brand[:200] if brand else None,
                description,
                base_price_jpy,
            ),
        )
        return cur.fetchone()[0]


def replace_sizes(
    connection: psycopg.Connection,
    product_id: int,
    sizes: list[tuple[str, str, int]],
) -> None:
    """Upsert fixed S/M/L variants without changing their database ids.

    Cart and order rows reference product_sizes.  Deleting all variants before
    re-inserting them would either violate those references or silently detach
    order history, so recrawls update each stable label in place.
    """
    with connection.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO product_sizes
                (product_id, size_name, source_sku_id, price_adjustment_jpy)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (product_id, size_name) DO UPDATE SET
                source_sku_id = EXCLUDED.source_sku_id,
                price_adjustment_jpy = EXCLUDED.price_adjustment_jpy
            """,
            [(product_id, label, sku_id, delta) for label, sku_id, delta in sizes],
        )


def sync_images(connection: psycopg.Connection, product_id: int, keys: list[str]) -> None:
    """Make the product's database image list match the latest crawl."""
    with connection.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO product_images (product_id, image_key) VALUES (%s, %s)
            ON CONFLICT (product_id, image_key) DO NOTHING
            """,
            [(product_id, key) for key in keys],
        )
        if keys:
            cur.execute(
                "DELETE FROM product_images WHERE product_id = %s AND NOT (image_key = ANY(%s))",
                (product_id, keys),
            )
        else:
            cur.execute("DELETE FROM product_images WHERE product_id = %s", (product_id,))


def counts(connection: psycopg.Connection) -> dict[str, int]:
    with connection.cursor() as cur:
        result = {}
        for table in ("categories", "products", "product_sizes", "product_images"):
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            result[table] = cur.fetchone()[0]
        return result
