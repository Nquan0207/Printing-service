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

    def user(self, owner_key: str) -> dict[str, Any] | None:
        return self.users.get(owner_key)

    def is_guest(self, owner_key: str) -> bool:
        user = self.users.get(owner_key)
        return bool(user and user.get("guest"))


STATE, CLIENT = CommerceState(), StockroomClient()


def success(*, owner_key: str | None = None, **values):
    """Standard envelope.

    `owner_key` is consumed here, never emitted: it is the capability the whole
    session is keyed on, and everything in this envelope reaches the model and
    the browser. What goes out is the identified user, so a freshly rendered
    widget can tell it is already known instead of asking again -- the reason
    the sign-in form used to reappear on every render.
    """
    out = {"status": "ok", **values, "scope": SCOPE}
    if owner_key is not None:
        out["user"] = _public_user(owner_key)
    return out


def _public_user(owner_key: str) -> dict[str, Any] | None:
    """The shopper's identity, or None while they are still a guest.

    A guest account is an implementation detail of "the cart needs a user_id";
    surfacing it would have the UI announce a name nobody chose.
    """
    user = STATE.user(owner_key)
    if not user or user.get("guest"):
        return None
    # Name and email only. The login response also carries user_id, is_admin
    # and created; none of that is the panel's business, and everything in this
    # envelope reaches the model and the browser. The id in particular is the
    # key every cart and order row is scoped by -- it stays server-side.
    return {"name": user.get("name", ""), "email": user["email"]}


def failure(exc: Exception):
    if isinstance(exc, StockroomAPIError):
        return {"status": "error", "error": {"code": exc.code, "message": str(exc)}, "scope": SCOPE}
    return {"status": "error", "error": {"code": "internal", "message": str(exc)}, "scope": SCOPE}


def run(action):
    try: return action()
    except Exception as exc: return failure(exc)


# A cart line needs a user_id, and the Go API falls back to its DEFAULT user
# when the identity header is absent -- so an anonymous add_to_cart would land
# in that user's basket and every guest would share one cart. Each guest
# therefore gets its own throwaway account, created on the first write and
# claimed at checkout. Browsing still touches none of this.
GUEST_DOMAIN = "guest.stockroom.local"


def _guest_user(owner_key: str) -> dict[str, Any]:
    """The user id to write a cart against, creating a guest on first use."""
    with STATE.lock:
        existing = STATE.users.get(owner_key)
    if existing:
        return existing
    token = secrets.token_hex(8)
    user = CLIENT.login(email=f"guest-{token}@{GUEST_DOMAIN}", name="Guest")
    user["guest"] = True
    with STATE.lock:
        # Another call may have raced us here; first writer wins so the two
        # do not end up with a cart each.
        if owner_key in STATE.users:
            return STATE.users[owner_key]
        STATE.users[owner_key] = user
    return user


def cart_user_id(owner_key: str) -> int:
    return _guest_user(owner_key)["user_id"]


def _claim_cart(owner_key: str, name: str, email: str) -> dict[str, Any]:
    """Attach a guest's cart to a real account at checkout.

    A returning customer's email already exists, so this moves the lines rather
    than renaming the guest -- renaming would collide on the unique email and
    would silently strand whatever was already in their basket.
    """
    real = CLIENT.login(email=email, name=name)
    previous = STATE.user(owner_key)
    guest_id = previous["user_id"] if previous and previous.get("guest") else None

    if guest_id is not None and guest_id != real["user_id"]:
        for item in CLIENT.cart(guest_id).get("items", []):
            CLIENT.add_to_cart(
                item["product_id"], item["size_id"], item["quantity"], real["user_id"]
            )
            CLIENT.remove_cart_item(item["id"], guest_id)

    real["guest"] = False
    with STATE.lock:
        STATE.users[owner_key] = real
    return real


def sign_out_handler(owner_key: str):
    """Forget who the shopper is, without touching what they bought.

    The cart stays with the account it belongs to -- signing out must not carry
    one person's basket into the next person's session, and it must still be
    there when they sign back in. A pending confirmation goes too: it was
    issued against a user_id that is no longer the one at the keyboard.
    """
    def action():
        with STATE.lock:
            STATE.users.pop(owner_key, None)
            for token, confirmation in list(STATE.confirmations.items()):
                if confirmation.owner_key == owner_key and not confirmation.decision:
                    STATE.confirmations.pop(token, None)
        return success(user=None, cart=None, message="Signed out. Browsing as a guest.")
    return run(action)


def mock_sign_in_handler(owner_key: str, name: str, email: str):
    def action():
        # Signing in mid-basket must not drop the basket, so this goes through
        # the same claim path as checkout.
        user = _claim_cart(owner_key, name, email)
        return success(user=_public_user(owner_key), mock_authentication=True)
    return run(action)


def search_products_handler(query=None, category=None, min_price=None, max_price=None, limit=20, per_category=None, owner_key=None):
    def action():
        result = CLIENT.search_products(q=query, category=category, min_price=min_price, max_price=max_price, limit=limit, per_category=per_category)
        payload = {"status": "ok" if result.get("count") else "no_match_in_current_catalog", **result, "scope": SCOPE}
        # This envelope seeds the widget's first render, so it must say who the
        # shopper is -- otherwise a signed-in shopper meets the sign-in form
        # again every time the panel opens. Built inline rather than through
        # success() because the status is not always "ok".
        if owner_key is not None:
            payload["user"] = _public_user(owner_key)
        return payload
    return run(action)


def get_product_handler(product_id: int): return run(lambda: success(product=CLIENT.product(product_id)))
def list_categories_handler(): return run(lambda: success(**CLIENT.categories()))
# A quote is pure arithmetic, so it needs no identity and creates no guest.
def get_quote_handler(owner_key: str, product_id: int, size_id: int, quantity: int): return run(lambda: success(quote=CLIENT.quote(product_id, size_id, quantity, STATE.user_id(owner_key)), owner_key=owner_key))
def get_cart_handler(owner_key: str): return run(lambda: success(cart=CLIENT.cart(cart_user_id(owner_key)), owner_key=owner_key))
def add_to_cart_handler(owner_key: str, product_id: int, size_id: int, quantity: int): return run(lambda: success(cart=CLIENT.add_to_cart(product_id, size_id, quantity, cart_user_id(owner_key)), owner_key=owner_key))
def update_cart_item_handler(owner_key: str, item_id: int, size_id: int, quantity: int):
    return run(lambda: success(cart=CLIENT.update_cart_item(item_id, size_id, quantity, STATE.user_id(owner_key))))


def remove_cart_item_handler(owner_key: str, item_id: int): return run(lambda: success(cart=CLIENT.remove_cart_item(item_id, cart_user_id(owner_key)), owner_key=owner_key))


def _cart_digest(cart: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cart, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def prepare_order_handler(owner_key: str, shipping_address: str, name: str = "", email: str = ""):
    def action():
        address = " ".join((shipping_address or "").split())
        if not address: raise StockroomAPIError("invalid_request", "Shipping address is required.", 400)

        # Checkout is the ONE place a shopper is asked who they are. Browsing
        # and the cart are anonymous; a returning customer is already known and
        # is never asked again.
        if (email or "").strip():
            _claim_cart(owner_key, (name or "").strip(), email.strip())
        elif STATE.is_guest(owner_key) or STATE.user_id(owner_key) is None:
            raise StockroomAPIError(
                "identity_required",
                "Ask the shopper for the name and email this order is for, then call prepare_order again with them.",
                428,
            )

        cart = CLIENT.cart(STATE.user_id(owner_key))
        if not cart.get("items"): raise StockroomAPIError("cart_empty", "The cart is empty.", 409)
        token = secrets.token_urlsafe(32)
        confirmation = Confirmation(token, owner_key, STATE.user_id(owner_key), address, _cart_digest(cart), utcnow() + timedelta(minutes=15))
        with STATE.lock: STATE.confirmations[token] = confirmation
        return {"status": "confirmation_required", "user": _public_user(owner_key), "cart": cart, "confirmation": {"token": token, "expires_at": confirmation.expires_at.isoformat(), "shipping_address": address}, "message": "Ask the user to explicitly approve or reject this mock order before calling place_order.", "scope": SCOPE}
    return run(action)


def place_order_handler(owner_key: str, confirmation_token: str, decision: str):
    def action():
        value = (decision or "").strip().lower()
        if value not in {"approve", "reject"}: raise StockroomAPIError("invalid_decision", "Decision must be approve or reject.", 400)
        with STATE.lock: confirmation = STATE.confirmations.get(confirmation_token)
        if not confirmation or confirmation.owner_key != owner_key: raise StockroomAPIError("invalid_confirmation", "Confirmation token is invalid.", 403)
        if confirmation.decision:
            if confirmation.decision != value: raise StockroomAPIError("decision_conflict", "This confirmation already has the opposite final decision.", 409)
            return success(decision=value, order=confirmation.order, idempotent=True, owner_key=owner_key)
        if confirmation.expires_at <= utcnow(): raise StockroomAPIError("confirmation_expired", "Confirmation expired. Review the cart again.", 409)
        if value == "reject":
            confirmation.decision = "reject"
            return success(decision="reject", order=None, message="Mock order rejected; the database cart was preserved.", owner_key=owner_key)
        cart = CLIENT.cart(confirmation.user_id)
        if _cart_digest(cart) != confirmation.cart_digest: raise StockroomAPIError("cart_changed", "The cart changed after review. Prepare the order again.", 409)
        order = CLIENT.place_order(confirmation.shipping_address, confirmation.user_id)
        confirmation.decision, confirmation.order = "approve", order
        return success(decision="approve", order=order, message="Mock order confirmed; no real payment occurred.", owner_key=owner_key)
    return run(action)


def order_history_handler(owner_key: str, limit: int = 20):
    """A shopper's own past orders.

    Requires an identity, and a guest is not one: they have no history because
    checkout is the first point anything is attached to a person. Rather than
    return an empty list -- which reads as "you have never ordered" -- say what
    is missing, the same 428 the checkout uses.
    """
    def action():
        if STATE.is_guest(owner_key) or STATE.user_id(owner_key) is None:
            raise StockroomAPIError(
                "identity_required",
                "Ask the shopper for the email they ordered with, then sign them in to show their history.",
                428,
            )
        return success(
            **CLIENT.orders(STATE.user_id(owner_key), max(1, min(int(limit), 100))),
            owner_key=owner_key,
        )
    return run(action)


def get_order_handler(owner_key: str, order_number: str): return run(lambda: success(order=CLIENT.order(order_number, STATE.user_id(owner_key)), owner_key=owner_key))
