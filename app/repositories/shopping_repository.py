from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database.models import (
    Cart,
    CartItem,
    MockCheckoutConfirmation,
    MockCustomer,
    MockOrder,
    MockSession,
    MockSessionCart,
    Product,
    utcnow,
)


class ShoppingRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_customer_by_email(self, email: str) -> MockCustomer | None:
        return self.session.scalar(select(MockCustomer).where(MockCustomer.email == email))

    def create_customer(self, name: str, email: str) -> MockCustomer:
        customer = MockCustomer(id=str(uuid4()), name=name, email=email)
        self.session.add(customer)
        self.session.flush()
        return customer

    def update_customer_name(self, customer: MockCustomer, name: str) -> None:
        customer.name = name
        customer.updated_at = utcnow()
        self.session.flush()

    def create_session(self, customer: MockCustomer, expires_at) -> MockSession:
        mock_session = MockSession(
            id=str(uuid4()), customer_id=customer.id, customer=customer, expires_at=expires_at
        )
        self.session.add(mock_session)
        self.session.flush()
        return mock_session

    def get_session(self, session_id: str) -> MockSession | None:
        return self.session.scalar(
            select(MockSession)
            .where(MockSession.id == session_id)
            .options(joinedload(MockSession.customer))
        )

    def create_cart(self, session_id: str) -> Cart:
        cart = Cart(id=str(uuid4()), status="active")
        self.session.add(cart)
        self.session.flush()
        self.session.add(MockSessionCart(session_id=session_id, cart_id=cart.id))
        self.session.flush()
        return cart

    def session_owns_cart(self, session_id: str, cart_id: str) -> bool:
        return self.session.scalar(
            select(MockSessionCart).where(
                MockSessionCart.session_id == session_id,
                MockSessionCart.cart_id == cart_id,
            )
        ) is not None

    def get_cart(self, cart_id: str) -> Cart | None:
        return self.session.execute(
            select(Cart)
            .where(Cart.id == cart_id)
            .options(joinedload(Cart.items).joinedload(CartItem.product))
        ).unique().scalar_one_or_none()

    def get_product(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def add_item(
        self,
        cart: Cart,
        product: Product,
        quantity: int,
        color: str | None,
        size: str | None,
    ) -> CartItem:
        item = next(
            (
                existing
                for existing in cart.items
                if existing.product_id == product.id
                and existing.selected_color == color
                and existing.selected_size == size
            ),
            None,
        )
        if item:
            item.quantity += quantity
            item.updated_at = utcnow()
        else:
            item = CartItem(
                product_id=product.id,
                quantity=quantity,
                selected_color=color,
                selected_size=size,
                unit_price_jpy=product.price_jpy,
                cart=cart,
                product=product,
            )
            self.session.add(item)
        cart.updated_at = utcnow()
        self.session.flush()
        return item

    def get_item(self, cart: Cart, item_id: int) -> CartItem | None:
        return next((item for item in cart.items if item.id == item_id), None)

    def update_item(self, cart: Cart, item: CartItem, quantity: int) -> None:
        item.quantity = quantity
        item.updated_at = utcnow()
        cart.updated_at = utcnow()
        self.session.flush()

    def remove_item(self, cart: Cart, item: CartItem) -> None:
        cart.items.remove(item)
        cart.updated_at = utcnow()
        self.session.flush()

    def pending_order(self, cart_id: str) -> MockOrder | None:
        return self.session.scalar(
            select(MockOrder).where(
                MockOrder.cart_id == cart_id, MockOrder.status == "pending"
            )
        )

    def create_order(self, cart: Cart, total_jpy: int, line_items: list[dict]) -> MockOrder:
        order = MockOrder(
            id=str(uuid4()),
            cart_id=cart.id,
            status="pending",
            total_jpy=total_jpy,
            line_items=line_items,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def get_order(self, order_id: str) -> MockOrder | None:
        return self.session.get(MockOrder, order_id)

    def session_owns_order(self, session_id: str, order_id: str) -> bool:
        return self.session.scalar(
            select(MockOrder.id)
            .join(MockSessionCart, MockSessionCart.cart_id == MockOrder.cart_id)
            .where(MockSessionCart.session_id == session_id, MockOrder.id == order_id)
        ) is not None

    def current_confirmation(self, order_id: str) -> MockCheckoutConfirmation | None:
        return self.session.scalar(
            select(MockCheckoutConfirmation)
            .where(MockCheckoutConfirmation.order_id == order_id)
            .order_by(MockCheckoutConfirmation.created_at.desc())
        )

    def create_confirmation(self, order_id: str, token: str, expires_at) -> MockCheckoutConfirmation:
        confirmation = MockCheckoutConfirmation(
            id=str(uuid4()), order_id=order_id, token=token, expires_at=expires_at
        )
        self.session.add(confirmation)
        self.session.flush()
        return confirmation

    def use_confirmation(self, confirmation: MockCheckoutConfirmation) -> None:
        confirmation.status = "used"
        confirmation.used_at = utcnow()
        self.session.flush()

    def decide_order(self, order: MockOrder, cart: Cart, decision: str) -> None:
        order.status = decision
        order.decided_at = utcnow()
        if decision == "approved":
            cart.status = "checked_out"
            cart.updated_at = utcnow()
        self.session.flush()
