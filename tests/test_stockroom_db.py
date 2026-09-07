from contextlib import contextmanager

from stockroom_crawler import db


class Cursor:
    def __init__(self):
        self.calls = []

    def executemany(self, sql, params):
        self.calls.append((sql, list(params)))

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class Connection:
    def __init__(self):
        self.cursor_instance = Cursor()

    @contextmanager
    def cursor(self):
        yield self.cursor_instance


def test_size_recrawl_uses_upsert_and_never_deletes_ids():
    connection = Connection()
    db.replace_sizes(connection, 9, [("S", "101", 0), ("M", "102", 100), ("L", "103", 200)])
    sql, params = connection.cursor_instance.calls[0]
    assert "ON CONFLICT (product_id, size_name) DO UPDATE" in sql
    assert "DELETE" not in sql
    assert params[0] == (9, "S", "101", 0)


def test_image_recrawl_removes_database_rows_not_in_latest_set():
    connection = Connection()
    db.sync_images(connection, 9, ["products/9/new.jpg"])
    statements = [sql for sql, _ in connection.cursor_instance.calls]
    assert "ON CONFLICT (product_id, image_key) DO NOTHING" in statements[0]
    assert "NOT (image_key = ANY(%s))" in statements[1]
