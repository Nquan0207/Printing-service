import os

import pytest
import requests


BASE_URL = os.getenv("STOCKROOM_E2E_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="set STOCKROOM_E2E_URL to run against the local API")


def api(method, path, *, user_id=None, body=None):
    headers = {"Accept": "application/json"}
    if user_id is not None:
        headers["X-Stockroom-User"] = str(user_id)
    response = requests.request(method, BASE_URL + path, headers=headers, json=body, timeout=10)
    response.raise_for_status()
    return response.json()


def test_catalog_quote_cart_and_mock_order_round_trip():
    assert api("GET", "/healthz")["status"] == "ok"
    catalog = api("GET", "/api/v1/products?limit=1")
    assert catalog["count"] == 1, "crawl at least one product before running e2e"

    product = catalog["groups"][0]["products"][0]
    assert len(product["sizes"]) == 3
    assert product["images"]
    size = product["sizes"][0]

    user = api(
        "POST",
        "/api/v1/login",
        body={"name": "E2E User", "email": "e2e@stockroom.local"},
    )
    user_id = user["user_id"]
    quote = api(
        "POST",
        "/api/v1/quote",
        user_id=user_id,
        body={"product_id": product["id"], "size_id": size["id"], "quantity": 2},
    )
    assert quote["subtotal_jpy"] == quote["unit_price_jpy"] * 2

    cart = api(
        "POST",
        "/api/v1/cart/items",
        user_id=user_id,
        body={"product_id": product["id"], "size_id": size["id"], "quantity": 2},
    )
    assert cart["items"]
    order = api(
        "POST",
        "/api/v1/orders",
        user_id=user_id,
        body={"shipping_address": "Local E2E address"},
    )
    loaded = api("GET", "/api/v1/orders/" + order["order_number"], user_id=user_id)
    assert loaded["order_number"] == order["order_number"]
    assert loaded["items"]
