from __future__ import annotations

import re
import secrets
from datetime import timedelta

from app.database.models import utcnow
from app.repositories.shopping_repository import ShoppingRepository


SESSION_LIFETIME = timedelta(hours=24)
CONFIRMATION_LIFETIME = timedelta(minutes=15)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ShoppingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _clean_option(value: str | None) -> str | None:
    value = value.strip() if value else None
    return value or None


class ShoppingService:
    def __init__(self, repository: ShoppingRepository):
        self.repository = repository

    def mock_sign_in(self, name: str, email: str):
        name = " ".join((name or "").split())
        email = (email or "").strip().lower()
        if not name or len(name) > 120:
            raise ShoppingError("invalid_name", "Name must contain 1 through 120 characters.")
        if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
            raise ShoppingError("invalid_email", "Enter a valid email address.")
        customer = self.repository.get_customer_by_email(email)
        if customer is None:
            customer = self.repository.create_customer(name, email)
        elif customer.name != name:
            self.repository.update_customer_name(customer, name)
        return self.repository.create_session(customer, utcnow() + SESSION_LIFETIME)

    def get_session(self, session_id: str):
        mock_session = self.repository.get_session(session_id)
        if not mock_session:
            raise ShoppingError("session_not_found", "Mock session was not found. Sign in again.")
        if mock_session.expires_at <= utcnow():
            raise ShoppingError("session_expired", "Mock session expired. Sign in again.")
        return mock_session

    def create_cart(self, session_id: str):
        self.get_session(session_id)
        return self.repository.create_cart(session_id)

    def get_cart(self, session_id: str, cart_id: str):
        self.get_session(session_id)
        if not self.repository.session_owns_cart(session_id, cart_id):
            raise ShoppingError("cart_access_denied", "This cart does not belong to the mock session.")
        cart = self.repository.get_cart(cart_id)
        if not cart:
            raise ShoppingError("cart_not_found", f"Cart {cart_id} was not found.")
        return cart

    def add_item(self, session_id: str, cart_id: str, product_id: int, quantity: int, color=None, size=None):
        cart = self.get_cart(session_id, cart_id)
        self._require_active(cart)
        if quantity < 1 or quantity > 100:
            raise ShoppingError("invalid_quantity", "Quantity must be between 1 and 100.")
        product = self.repository.get_product(product_id)
        if not product:
            raise ShoppingError("product_not_found", f"Product {product_id} was not found.")
        if product.price_jpy is None:
            raise ShoppingError("price_unavailable", "This product has no snapshot price and cannot be added.")
        color = _clean_option(color)
        size = _clean_option(size)
        self._validate_option("color", color, product.colors or [])
        self._validate_option("size", size, product.sizes or [])
        self.repository.add_item(cart, product, quantity, color, size)
        return self.get_cart(session_id, cart_id)

    def update_item(self, session_id: str, cart_id: str, item_id: int, quantity: int):
        cart = self.get_cart(session_id, cart_id)
        self._require_active(cart)
        if quantity < 1 or quantity > 100:
            raise ShoppingError("invalid_quantity", "Quantity must be between 1 and 100.")
        item = self.repository.get_item(cart, item_id)
        if not item:
            raise ShoppingError("item_not_found", f"Cart item {item_id} was not found.")
        self.repository.update_item(cart, item, quantity)
        return self.get_cart(session_id, cart_id)

    def remove_item(self, session_id: str, cart_id: str, item_id: int):
        cart = self.get_cart(session_id, cart_id)
        self._require_active(cart)
        item = self.repository.get_item(cart, item_id)
        if not item:
            raise ShoppingError("item_not_found", f"Cart item {item_id} was not found.")
        self.repository.remove_item(cart, item)
        return self.get_cart(session_id, cart_id)

    def create_checkout(self, session_id: str, cart_id: str):
        cart = self.get_cart(session_id, cart_id)
        self._require_active(cart)
        if not cart.items:
            raise ShoppingError("empty_cart", "Add at least one product before checkout.")
        pending = self.repository.pending_order(cart.id)
        if not pending:
            lines = [self._line_snapshot(item) for item in cart.items]
            total = sum(line["line_total_jpy"] for line in lines)
            pending = self.repository.create_order(cart, total, lines)
        confirmation = self.repository.current_confirmation(pending.id)
        if not confirmation or confirmation.status != "pending" or confirmation.expires_at <= utcnow():
            confirmation = self.repository.create_confirmation(
                pending.id, secrets.token_urlsafe(32), utcnow() + CONFIRMATION_LIFETIME
            )
        return pending, confirmation

    def get_order(self, session_id: str, order_id: str):
        self.get_session(session_id)
        if not self.repository.session_owns_order(session_id, order_id):
            raise ShoppingError("order_access_denied", "This order does not belong to the mock session.")
        order = self.repository.get_order(order_id)
        if not order:
            raise ShoppingError("order_not_found", f"Mock order {order_id} was not found.")
        return order

    def decide_payment(self, session_id: str, order_id: str, confirmation_token: str, decision: str):
        order = self.get_order(session_id, order_id)
        decision = (decision or "").strip().lower()
        if decision not in {"approve", "reject"}:
            raise ShoppingError("invalid_decision", "Decision must be approve or reject.")
        decision = "approved" if decision == "approve" else "rejected"
        confirmation = self.repository.current_confirmation(order_id)
        if not confirmation or not secrets.compare_digest(confirmation.token, confirmation_token or ""):
            raise ShoppingError("invalid_confirmation", "The confirmation token is invalid.")
        if order.status == decision:
            return order
        if order.status != "pending":
            raise ShoppingError(
                "decision_conflict",
                f"Order is already {order.status}; its final decision cannot be changed.",
            )
        if confirmation.status != "pending":
            raise ShoppingError("confirmation_used", "The confirmation token has already been used.")
        if confirmation.expires_at <= utcnow():
            raise ShoppingError("confirmation_expired", "The confirmation expired. Start checkout again.")
        cart = self.get_cart(session_id, order.cart_id)
        self.repository.use_confirmation(confirmation)
        self.repository.decide_order(order, cart, decision)
        return order

    @staticmethod
    def _require_active(cart):
        if cart.status != "active":
            raise ShoppingError("cart_closed", "This cart has already been checked out.")

    @staticmethod
    def _validate_option(name: str, selected: str | None, available: list):
        if available and selected not in available:
            raise ShoppingError(
                f"invalid_{name}",
                f"Select a valid {name}: {', '.join(map(str, available))}.",
            )
        if not available and selected is not None:
            raise ShoppingError(f"invalid_{name}", f"This product does not define a {name} option.")

    @staticmethod
    def _line_snapshot(item):
        return {
            "item_id": item.id,
            "product_id": item.product_id,
            "name": item.product.name,
            "image_url": item.product.image_url,
            "quantity": item.quantity,
            "color": item.selected_color,
            "size": item.selected_size,
            "unit_price_jpy": item.unit_price_jpy,
            "line_total_jpy": item.unit_price_jpy * item.quantity,
        }
