"""Non-destructive, restartable preparation for the Compose stack."""
from __future__ import annotations

import logging
import uuid

from psycopg import sql

from stockroom_crawler import db, pipeline
from stockroom_crawler.config import Settings
from stockroom_crawler.storage import ImageStore

log = logging.getLogger(__name__)
TABLES = ('users', 'categories', 'products', 'product_images', 'product_sizes',
          'cart_items', 'orders', 'order_items')


def signature(connection, schema: str):
    """Compare database types/nullability/defaults and business constraints."""
    columns = connection.execute("""
        SELECT table_name, column_name, udt_name, character_maximum_length,
               is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
    """, (schema, list(TABLES))).fetchall()
    # Serial defaults refer to sequences qualified with the reference schema.
    columns = [tuple(v.replace(schema + '.', '') if isinstance(v, str) else v
                     for v in row) for row in columns]
    constraints = connection.execute("""
        SELECT t.relname, c.contype, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = %s AND t.relname = ANY(%s)
        ORDER BY t.relname, c.contype, pg_get_constraintdef(c.oid)
    """, (schema, list(TABLES))).fetchall()
    constraints = [tuple(v.replace(schema + '.', '') if isinstance(v, str) else v
                         for v in row) for row in constraints]
    return columns, constraints


def prepare_schema(connection):
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(748201)")
        existing = connection.execute("""
            SELECT tablename FROM pg_tables WHERE schemaname = 'public'
              AND tablename = ANY(%s)
        """, (list(TABLES),)).fetchall()
        if not existing:
            connection.execute(db.SCHEMA_PATH.read_text())
        else:
            reference = 'bootstrap_check_' + uuid.uuid4().hex
            connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(reference)))
            connection.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(reference)))
            connection.execute(db.SCHEMA_PATH.read_text())
            expected = signature(connection, reference)
            connection.execute('SET LOCAL search_path TO public')
            actual = signature(connection, 'public')
            if actual != expected:
                raise RuntimeError('Existing database schema is incompatible with backend-ops/schema.sql. '
                                   'Apply a reviewed migration; bootstrap will not drop existing data.')
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(reference)))
        connection.execute("""
            CREATE TABLE IF NOT EXISTS stockroom_bootstrap (
                name TEXT PRIMARY KEY, completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    log.info('Database schema ready (existing data preserved)')


def prepare(settings: Settings):
    with db.connect(settings.database_url) as connection:
        prepare_schema(connection)
    ImageStore(settings).ensure_bucket()
    log.info('MinIO bucket ready')


def crawl_once(settings: Settings):
    # Session lock serializes concurrent bootstrap attempts without keeping a
    # transaction open while the crawler commits products on another connection.
    with db.connect(settings.database_url) as connection:
        connection.autocommit = True
        connection.execute('SELECT pg_advisory_lock(748202)')
        try:
            if connection.execute("SELECT 1 FROM stockroom_bootstrap WHERE name = 'catalog-v1'").fetchone():
                log.info('Initial crawl already complete; use crawler crawl to import more')
                return
            summary = pipeline.run(settings, strict=True)
            if summary.failed or summary.products == 0:
                raise RuntimeError(f'Initial crawl incomplete: {summary.products} products, '
                                   f'{summary.failed} failures. Re-run to resume; imported data is retained.')
            connection.execute("INSERT INTO stockroom_bootstrap (name) VALUES ('catalog-v1')")
            log.info('Initial crawl complete: %s products', summary.products)
        finally:
            connection.execute('SELECT pg_advisory_unlock(748202)')
