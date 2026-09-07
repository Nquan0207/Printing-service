from datetime import timedelta

from app.mcp_server import tools as handlers
from app.mcp_server.server import mcp
from app.mcp_server.storefront_widget import STOREFRONT_HTML, STOREFRONT_URI


class FakeClient:
    def __init__(self):
        self.cart_value = {"items": [], "item_count": 0, "total_jpy": 0}
        self.orders = []

    def login(self, email, name): return {"user_id": 7, "email": email.lower(), "name": name, "created": True}
    def categories(self): return {"categories": [{"id": 1, "slug": "bags", "name": "Bags"}]}
    def search_products(self, **filters): return {"groups": [{"category": {"id": 1, "slug": "bags", "name": "Bags"}, "count": 1, "products": [{"id": 1, "name": "Bag", "base_price_jpy": 100, "sizes": [{"id": 2, "size_name": "S", "unit_price_jpy": 100}], "images": []}]}], "count": 1}
    def product(self, product_id): return self.search_products()["groups"][0]["products"][0]
    def quote(self, product_id, size_id, quantity, user_id=None): return {"product_id": product_id, "product_name": "Bag", "size_id": size_id, "size_name": "S", "quantity": quantity, "unit_price_jpy": 100, "subtotal_jpy": 100 * quantity, "currency": "JPY", "notes": ["Mock pricing."]}
    def cart(self, user_id=None): return self.cart_value
    def add_to_cart(self, product_id, size_id, quantity, user_id=None):
        self.cart_value = {"items": [{"id": 9, "product_id": product_id, "product_name": "Bag", "size_id": size_id, "size_name": "S", "quantity": quantity, "unit_price_jpy": 100, "subtotal_jpy": 100 * quantity}], "item_count": 1, "total_jpy": 100 * quantity}
        return self.cart_value
    def remove_cart_item(self, item_id, user_id=None):
        self.cart_value = {"items": [], "item_count": 0, "total_jpy": 0}; return self.cart_value
    def place_order(self, shipping_address, user_id=None):
        order = {"order_number": "RKS-TEST-0001", "status": "confirmed", "shipping_address": shipping_address, "total_jpy": self.cart_value["total_jpy"], "items": self.cart_value["items"]}
        self.orders.append(order); self.cart_value = {"items": [], "item_count": 0, "total_jpy": 0}; return order
    def order(self, order_number, user_id=None): return self.orders[-1]


def reset(monkeypatch):
    fake = FakeClient(); monkeypatch.setattr(handlers, "CLIENT", fake)
    handlers.STATE.users.clear(); handlers.STATE.confirmations.clear()
    return fake


def test_tools_resource_and_contract():
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    assert {"open_storefront", "mock_sign_in", "search_products", "get_product", "list_categories", "get_quote", "get_cart", "add_to_cart", "remove_cart_item", "prepare_order", "place_order", "get_order"} <= tools.keys()
    assert tools["open_storefront"].meta["ui"]["resourceUri"] == STOREFRONT_URI
    assert tools["place_order"].annotations.readOnlyHint is False
    resources = {str(r.uri): r for r in mcp._resource_manager.list_resources()}
    assert resources[STOREFRONT_URI].mime_type == "text/html;profile=mcp-app"
    assert resources[STOREFRONT_URI].meta["ui"]["csp"]["resourceDomains"] == ["http://127.0.0.1:8080"]


def test_backend_flow_approval_and_rejection(monkeypatch):
    fake = reset(monkeypatch); owner = "session-a"
    assert handlers.mock_sign_in_handler(owner, "Alice", "ALICE@example.com")["user"]["user_id"] == 7
    assert handlers.search_products_handler()["count"] == 1
    assert handlers.add_to_cart_handler(owner, 1, 2, 3)["cart"]["total_jpy"] == 300
    prepared = handlers.prepare_order_handler(owner, "Tokyo")
    approved = handlers.place_order_handler(owner, prepared["confirmation"]["token"], "approve")
    assert approved["order"]["order_number"] == "RKS-TEST-0001"
    assert len(fake.orders) == 1
    assert handlers.place_order_handler(owner, prepared["confirmation"]["token"], "approve")["idempotent"] is True
    assert handlers.place_order_handler(owner, prepared["confirmation"]["token"], "reject")["error"]["code"] == "decision_conflict"

    handlers.add_to_cart_handler(owner, 1, 2, 1)
    rejected_prep = handlers.prepare_order_handler(owner, "Tokyo")
    rejected = handlers.place_order_handler(owner, rejected_prep["confirmation"]["token"], "reject")
    assert rejected["decision"] == "reject"
    assert fake.cart()["item_count"] == 1


def test_confirmation_expiry_and_cart_change(monkeypatch):
    fake = reset(monkeypatch); owner = "session-b"
    handlers.mock_sign_in_handler(owner, "Bob", "bob@example.com")
    handlers.add_to_cart_handler(owner, 1, 2, 1)
    prepared = handlers.prepare_order_handler(owner, "Osaka")
    token = prepared["confirmation"]["token"]
    handlers.STATE.confirmations[token].expires_at = handlers.utcnow() - timedelta(seconds=1)
    assert handlers.place_order_handler(owner, token, "approve")["error"]["code"] == "confirmation_expired"
    prepared = handlers.prepare_order_handler(owner, "Osaka")
    fake.cart_value["items"][0]["quantity"] = 2
    assert handlers.place_order_handler(owner, prepared["confirmation"]["token"], "approve")["error"]["code"] == "cart_changed"


def test_widget_is_embedded_and_has_no_supplier_navigation():
    for marker in ("tools/call", "ui/initialize", "Approve mock order", "Reject mock order", "Mock receipt", "Stockroom backend"):
        assert marker in STOREFRONT_HTML
    assert "window.open(" not in STOREFRONT_HTML
    assert "raksul.com" not in STOREFRONT_HTML
