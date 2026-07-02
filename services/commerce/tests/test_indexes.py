"""COM-101 AC: required indexes exist on orders (user_id, status, created_at)."""

from sqlalchemy import inspect


def _indexed_columns(engine, table: str) -> set[str]:
    columns: set[str] = set()
    for index in inspect(engine).get_indexes(table):
        columns.update(index["column_names"])
    return columns


def test_orders_user_id_indexed(engine):
    assert "user_id" in _indexed_columns(engine, "orders")


def test_orders_status_indexed(engine):
    assert "status" in _indexed_columns(engine, "orders")


def test_orders_created_at_indexed(engine):
    assert "created_at" in _indexed_columns(engine, "orders")


def test_addresses_user_id_indexed(engine):
    assert "user_id" in _indexed_columns(engine, "addresses")


def test_order_items_order_id_indexed(engine):
    assert "order_id" in _indexed_columns(engine, "order_items")
