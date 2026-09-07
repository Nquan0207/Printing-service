from datetime import timedelta

from stockroom_shop import tools as handlers
from stockroom_shop.server import mcp
from stockroom_shop.storefront_widget import STOREFRONT_HTML, STOREFRONT_URI


class FakeClient:
    def __init__(self):
        self.cart_value = {"items": [], "item_count": 0, "total_jpy": 0}
        self.placed = []   # rows, not the orders() method
        # Per-email ids, so a guest account and the account it is claimed by
        # are distinguishable -- with one shared id the claim path is untestable.
        self.ids: dict[str, int] = {}
        self.carts: dict[int, list] = {}
        self.next_item_id = 100

    def login(self, email, name):
        key = email.lower()
        created = key not in self.ids
        self.ids.setdefault(key, 7 + len(self.ids))
        return {"user_id": self.ids[key], "email": key, "name": name, "created": created}
    def categories(self): return {"categories": [{"id": 1, "slug": "bags", "name": "Bags"}]}
    def search_products(self, **filters): return {"groups": [{"category": {"id": 1, "slug": "bags", "name": "Bags"}, "count": 1, "products": [{"id": 1, "name": "Bag", "base_price_jpy": 100, "sizes": [{"id": 2, "size_name": "S", "unit_price_jpy": 100}], "images": []}]}], "count": 1}
    def product(self, product_id): return self.search_products()["groups"][0]["products"][0]
    def quote(self, product_id, size_id, quantity, user_id=None): return {"product_id": product_id, "product_name": "Bag", "size_id": size_id, "size_name": "S", "quantity": quantity, "unit_price_jpy": 100, "subtotal_jpy": 100 * quantity, "currency": "JPY", "notes": ["Mock pricing."]}
    def _rebuild(self, user_id):
        items = self.carts.setdefault(user_id, [])
        self.cart_value = {"items": items, "item_count": len(items),
                           "total_jpy": sum(i["subtotal_jpy"] for i in items)}
        return self.cart_value

    def cart(self, user_id=None):
        # user_id=None never comes from the handlers -- they always resolve a
        # guest or real id. It is the tests inspecting the fake directly, and
        # it means "whichever cart was touched last".
        return self.cart_value if user_id is None else self._rebuild(user_id)

    def add_to_cart(self, product_id, size_id, quantity, user_id=None):
        self.next_item_id += 1
        self.carts.setdefault(user_id, []).append({
            "id": self.next_item_id, "product_id": product_id, "product_name": "Bag",
            "size_id": size_id, "size_name": "S", "quantity": quantity,
            "unit_price_jpy": 100, "subtotal_jpy": 100 * quantity,
        })
        return self._rebuild(user_id)

    def remove_cart_item(self, item_id, user_id=None):
        self.carts[user_id] = [i for i in self.carts.get(user_id, []) if i["id"] != item_id]
        return self._rebuild(user_id)
    def place_order(self, shipping_address, user_id=None):
        cart = self._rebuild(user_id)
        order = {"order_number": "RKS-TEST-%04d" % (len(self.placed) + 1), "status": "confirmed", "shipping_address": shipping_address, "total_jpy": cart["total_jpy"], "items": list(cart["items"]), "user_id": user_id}
        self.placed.append(order); self.carts[user_id] = []; self._rebuild(user_id); return order
    def order(self, order_number, user_id=None): return self.placed[-1]
    def orders(self, user_id=None, limit=20):
        mine = [o for o in self.placed if o.get("user_id") == user_id]
        return {"orders": list(reversed(mine)), "total": len(mine), "limit": limit, "offset": 0}


def reset(monkeypatch):
    fake = FakeClient(); monkeypatch.setattr(handlers, "CLIENT", fake)
    handlers.STATE.users.clear(); handlers.STATE.confirmations.clear()
    return fake


def test_tools_resource_and_contract():
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    assert {"open_storefront", "mock_sign_in", "sign_out", "order_history", "search_products", "get_product", "list_categories", "get_quote", "get_cart", "add_to_cart", "remove_cart_item", "prepare_order", "place_order", "get_order"} <= tools.keys()
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
    assert len(fake.placed) == 1
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


def test_guest_can_shop_and_is_asked_once_at_checkout(monkeypatch):
    """Browsing and the cart are anonymous; identity is collected at checkout."""
    reset(monkeypatch)
    owner = "guest-session"

    # Nothing identifies the shopper, and browsing creates no account at all.
    assert handlers.search_products_handler(owner_key=owner)["user"] is None
    assert handlers.STATE.users == {}

    # The cart works, but now a guest account exists to own the rows: without
    # one the API would fall back to its default user and every guest would
    # share a single basket.
    assert handlers.add_to_cart_handler(owner, 1, 2, 3)["cart"]["total_jpy"] == 300
    assert handlers.STATE.is_guest(owner)
    assert handlers.get_cart_handler(owner)["user"] is None, "a guest account is not an identity"

    # Checkout is the one place the shopper is asked.
    refused = handlers.prepare_order_handler(owner, "Tokyo")
    assert refused["error"]["code"] == "identity_required"

    claimed = handlers.prepare_order_handler(owner, "Tokyo", "Ada", "ada@example.com")
    assert claimed["status"] == "confirmation_required"
    assert claimed["user"]["email"] == "ada@example.com"
    assert claimed["cart"]["total_jpy"] == 300, "the guest cart must survive the claim"

    # And having been identified, they are never asked again.
    again = handlers.prepare_order_handler(owner, "Osaka")
    assert again["status"] == "confirmation_required"


def test_two_guests_do_not_share_a_cart(monkeypatch):
    reset(monkeypatch)
    handlers.add_to_cart_handler("guest-a", 1, 2, 1)
    handlers.add_to_cart_handler("guest-b", 1, 2, 1)
    assert handlers.STATE.user_id("guest-a") != handlers.STATE.user_id("guest-b")


def test_owner_key_never_reaches_the_client(monkeypatch):
    """Everything in an envelope reaches the model and the browser, and the
    owner key is the capability the whole session is keyed on."""
    reset(monkeypatch)
    owner = "secret-owner-key"
    handlers.mock_sign_in_handler(owner, "Ada", "ada@example.com")
    for payload in (
        handlers.search_products_handler(owner_key=owner),
        handlers.get_cart_handler(owner),
        handlers.add_to_cart_handler(owner, 1, 2, 1),
        handlers.prepare_order_handler(owner, "Tokyo"),
    ):
        assert owner not in repr(payload)
        assert "owner_key" not in repr(payload)
        assert "guest" not in repr(payload.get("user") or {})


def test_sign_out_switches_shopper_without_leaking_the_cart(monkeypatch):
    """The first identity of a session must not be permanent."""
    reset(monkeypatch)
    owner = "shared-session"

    handlers.mock_sign_in_handler(owner, "Kaka", "kaka@gmail.com")
    handlers.add_to_cart_handler(owner, 1, 2, 2)
    assert handlers.get_cart_handler(owner)["cart"]["item_count"] == 1

    out = handlers.sign_out_handler(owner)
    assert out["user"] is None
    assert handlers.STATE.user(owner) is None

    # A fresh guest, not Kaka's basket -- carrying it over would show one
    # shopper's items to the next.
    assert handlers.get_cart_handler(owner)["cart"]["item_count"] == 0
    handlers.add_to_cart_handler(owner, 1, 2, 1)
    prepared = handlers.prepare_order_handler(owner, "Osaka", "Mimi", "mimi@gmail.com")
    assert prepared["user"]["email"] == "mimi@gmail.com"
    assert prepared["cart"]["item_count"] == 1

    # Kaka's cart is still Kaka's when they come back.
    handlers.mock_sign_in_handler(owner, "Kaka", "kaka@gmail.com")
    assert handlers.get_cart_handler(owner)["cart"]["item_count"] == 1


def test_sign_out_drops_a_pending_confirmation(monkeypatch):
    """A confirmation is a capability tied to one shopper's user_id."""
    reset(monkeypatch)
    owner = "session"
    handlers.mock_sign_in_handler(owner, "Kaka", "kaka@gmail.com")
    handlers.add_to_cart_handler(owner, 1, 2, 1)
    token = handlers.prepare_order_handler(owner, "Tokyo")["confirmation"]["token"]

    handlers.sign_out_handler(owner)
    refused = handlers.place_order_handler(owner, token, "approve")
    assert refused["error"]["code"] == "invalid_confirmation"


def test_order_history_is_scoped_and_needs_an_identity(monkeypatch):
    reset(monkeypatch)
    owner = "session"

    # A guest has no history: checkout is the first point an order is attached
    # to anyone, so an empty list would read as "you never ordered".
    assert handlers.order_history_handler(owner)["error"]["code"] == "identity_required"
    handlers.add_to_cart_handler(owner, 1, 2, 1)
    assert handlers.order_history_handler(owner)["error"]["code"] == "identity_required"

    # Buy as Kaka.
    prepared = handlers.prepare_order_handler(owner, "Tokyo", "Kaka", "kaka@example.com")
    handlers.place_order_handler(owner, prepared["confirmation"]["token"], "approve")
    mine = handlers.order_history_handler(owner)
    assert mine["total"] == 1
    assert mine["user"]["email"] == "kaka@example.com"

    # Someone else's history is theirs, not Kaka's.
    handlers.sign_out_handler(owner)
    handlers.mock_sign_in_handler(owner, "Mimi", "mimi@example.com")
    assert handlers.order_history_handler(owner)["total"] == 0

    # And it is hidden again once nobody is signed in.
    handlers.sign_out_handler(owner)
    assert handlers.order_history_handler(owner)["error"]["code"] == "identity_required"
