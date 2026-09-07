from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from stockroom_shop.stockroom_client import StockroomAPIError, StockroomClient

SCOPE = {"data_source": "stockroom_postgresql_via_go_api", "real_time": False, "mock_checkout": True}


def utcnow(): return datetime.now(timezone.utc)


@dataclass
class Confirmation:
    token: str
    owner_key: str
    user_id: int | None
    shipping_address: str
    cart_digest: str
    expires_at: datetime
    decision: str | None = None
    order: dict[str, Any] | None = None


class CommerceState:
    def __init__(self):
        self.users: dict[str, dict[str, Any]] = {}
        self.confirmations: dict[str, Confirmation] = {}
        self.lock = threading.Lock()

    def user_id(self, owner_key: str) -> int | None:
        user = self.users.get(owner_key)
        return user["user_id"] if user else None


STATE, CLIENT = CommerceState(), StockroomClient()


def success(**values): return {"status": "ok", **values, "scope": SCOPE}


def failure(exc: Exception):
    if isinstance(exc, StockroomAPIError):
        return {"status": "error", "error": {"code": exc.code, "message": str(exc)}, "scope": SCOPE}
    return {"status": "error", "error": {"code": "internal", "message": str(exc)}, "scope": SCOPE}


def run(action):
    try: return action()
    except Exception as exc: return failure(exc)


def mock_sign_in_handler(owner_key: str, name: str, email: str):
    def action():
        user = CLIENT.login(email=email, name=name)
        with STATE.lock: STATE.users[owner_key] = user
        return success(user=user, mock_authentication=True)
    return run(action)


def search_products_handler(query=None, category=None, min_price=None, max_price=None, limit=20, per_category=None):
    def action():
        result = CLIENT.search_products(q=query, category=category, min_price=min_price, max_price=max_price, limit=limit, per_category=per_category)
        return {"status": "ok" if result.get("count") else "no_match_in_current_catalog", **result, "scope": SCOPE}
    return run(action)


def get_product_handler(product_id: int): return run(lambda: success(product=CLIENT.product(product_id)))
def list_categories_handler(): return run(lambda: success(**CLIENT.categories()))
def get_quote_handler(owner_key: str, product_id: int, size_id: int, quantity: int): return run(lambda: success(quote=CLIENT.quote(product_id, size_id, quantity, STATE.user_id(owner_key))))
def get_cart_handler(owner_key: str): return run(lambda: success(cart=CLIENT.cart(STATE.user_id(owner_key))))
def add_to_cart_handler(owner_key: str, product_id: int, size_id: int, quantity: int): return run(lambda: success(cart=CLIENT.add_to_cart(product_id, size_id, quantity, STATE.user_id(owner_key))))
def remove_cart_item_handler(owner_key: str, item_id: int): return run(lambda: success(cart=CLIENT.remove_cart_item(item_id, STATE.user_id(owner_key))))


def _cart_digest(cart: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cart, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def prepare_order_handler(owner_key: str, shipping_address: str):
    def action():
        address = " ".join((shipping_address or "").split())
        if not address: raise StockroomAPIError("invalid_request", "Shipping address is required.", 400)
        cart = CLIENT.cart(STATE.user_id(owner_key))
        if not cart.get("items"): raise StockroomAPIError("cart_empty", "The cart is empty.", 409)
        token = secrets.token_urlsafe(32)
        confirmation = Confirmation(token, owner_key, STATE.user_id(owner_key), address, _cart_digest(cart), utcnow() + timedelta(minutes=15))
        with STATE.lock: STATE.confirmations[token] = confirmation
        return {"status": "confirmation_required", "cart": cart, "confirmation": {"token": token, "expires_at": confirmation.expires_at.isoformat(), "shipping_address": address}, "message": "Ask the user to explicitly approve or reject this mock order before calling place_order.", "scope": SCOPE}
    return run(action)


def place_order_handler(owner_key: str, confirmation_token: str, decision: str):
    def action():
        value = (decision or "").strip().lower()
        if value not in {"approve", "reject"}: raise StockroomAPIError("invalid_decision", "Decision must be approve or reject.", 400)
        with STATE.lock: confirmation = STATE.confirmations.get(confirmation_token)
        if not confirmation or confirmation.owner_key != owner_key: raise StockroomAPIError("invalid_confirmation", "Confirmation token is invalid.", 403)
        if confirmation.decision:
            if confirmation.decision != value: raise StockroomAPIError("decision_conflict", "This confirmation already has the opposite final decision.", 409)
            return success(decision=value, order=confirmation.order, idempotent=True)
        if confirmation.expires_at <= utcnow(): raise StockroomAPIError("confirmation_expired", "Confirmation expired. Review the cart again.", 409)
        if value == "reject":
            confirmation.decision = "reject"
            return success(decision="reject", order=None, message="Mock order rejected; the database cart was preserved.")
        cart = CLIENT.cart(confirmation.user_id)
        if _cart_digest(cart) != confirmation.cart_digest: raise StockroomAPIError("cart_changed", "The cart changed after review. Prepare the order again.", 409)
        order = CLIENT.place_order(confirmation.shipping_address, confirmation.user_id)
        confirmation.decision, confirmation.order = "approve", order
        return success(decision="approve", order=order, message="Mock order confirmed; no real payment occurred.")
    return run(action)


def get_order_handler(owner_key: str, order_number: str): return run(lambda: success(order=CLIENT.order(order_number, STATE.user_id(owner_key))))
