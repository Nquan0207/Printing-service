"""Integration tests use a disposable database, never the application's DB."""
import os
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from stockroom_crawler import bootstrap


@pytest.fixture
def database():
    url = os.getenv('BOOTSTRAP_TEST_DATABASE_URL')
    if not url:
        pytest.skip('set BOOTSTRAP_TEST_DATABASE_URL for PostgreSQL integration tests')
    name = 'bootstrap_test_' + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            test_url = make_conninfo(url, dbname=name)
            with psycopg.connect(test_url, autocommit=True) as connection:
                yield connection, test_url
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def test_schema_initializes_and_preserves_existing_rows(database):
    connection, _ = database
    bootstrap.prepare_schema(connection)
    connection.execute("INSERT INTO users (name,email,password_hash) VALUES ('Existing','keep@example.test','!')")
    bootstrap.prepare_schema(connection)
    assert connection.execute('SELECT name FROM users').fetchone() == ('Existing',)


def test_partial_schema_is_rejected_without_modification(database):
    connection, _ = database
    connection.execute('CREATE TABLE users (id bigint)')
    connection.execute('INSERT INTO users VALUES (42)')
    with pytest.raises(RuntimeError, match='incompatible'):
        bootstrap.prepare_schema(connection)
    assert connection.execute('SELECT * FROM users').fetchall() == [(42,)]
    assert connection.execute("SELECT to_regclass('public.products')").fetchone() == (None,)


def test_changed_column_type_is_rejected(database):
    connection, _ = database
    bootstrap.prepare_schema(connection)
    connection.execute('ALTER TABLE users ALTER COLUMN name TYPE text')
    with pytest.raises(RuntimeError, match='incompatible'):
        bootstrap.prepare_schema(connection)


@pytest.mark.parametrize('result', [SimpleNamespace(products=0, failed=0), SimpleNamespace(products=2, failed=1)])
def test_failed_crawl_can_resume_and_completed_crawl_is_skipped(database, monkeypatch, result):
    connection, url = database
    bootstrap.prepare_schema(connection)
    settings = SimpleNamespace(database_url=url)
    run = Mock(return_value=result)
    monkeypatch.setattr(bootstrap.pipeline, 'run', run)
    with pytest.raises(RuntimeError, match='incomplete'):
        bootstrap.crawl_once(settings)
    assert connection.execute('SELECT count(*) FROM stockroom_bootstrap').fetchone() == (0,)
    run.return_value = SimpleNamespace(products=70, failed=0)
    bootstrap.crawl_once(settings)
    bootstrap.crawl_once(settings)
    assert run.call_count == 2
    assert connection.execute('SELECT count(*) FROM stockroom_bootstrap').fetchone() == (1,)


def test_network_failure_leaves_crawl_retryable(database, monkeypatch):
    connection, url = database
    bootstrap.prepare_schema(connection)
    monkeypatch.setattr(bootstrap.pipeline, 'run', Mock(side_effect=ConnectionError('offline')))
    with pytest.raises(ConnectionError):
        bootstrap.crawl_once(SimpleNamespace(database_url=url))
    assert connection.execute('SELECT count(*) FROM stockroom_bootstrap').fetchone() == (0,)


def test_strict_discovery_propagates_network_error():
    client = Mock()
    client.get_text.side_effect = ConnectionError('offline')
    with pytest.raises(ConnectionError):
        bootstrap.pipeline._discover_products(client, ['https://source.test'], 1, 3, strict=True)


def test_recrawl_keeps_size_id_referenced_by_cart(database):
    from stockroom_crawler import db
    connection, _ = database
    bootstrap.prepare_schema(connection)
    user = connection.execute("INSERT INTO users(name,email,password_hash) VALUES ('Cart','cart@test','!') RETURNING id").fetchone()[0]
    category = db.upsert_category(connection, 'files', 'Files')
    product = db.upsert_product(connection, category_id=category, source_product_id='test',
                               name='Test', brand='', description='', base_price_jpy=100)
    db.replace_sizes(connection, product, [('S', 'sku1', 0)])
    size = connection.execute('SELECT id FROM product_sizes').fetchone()[0]
    connection.execute('INSERT INTO cart_items(user_id,product_id,product_size_id) VALUES (%s,%s,%s)', (user, product, size))
    db.replace_sizes(connection, product, [('S', 'sku2', 50)])
    assert connection.execute('SELECT id,price_adjustment_jpy FROM product_sizes').fetchone() == (size, 50)
    assert connection.execute('SELECT product_size_id FROM cart_items').fetchone() == (size,)
