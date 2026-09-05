import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.crawler.parser import NormalizedProduct
from app.database.models import Base
from app.repositories.product_repository import ProductRepository
from app.repositories.shopping_repository import ShoppingRepository
from app.services.shopping_service import ShoppingError, ShoppingService

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="set TEST_DATABASE_URL to run PostgreSQL integration tests")


@pytest.fixture()
def shopping():
    engine = create_engine(TEST_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        with Session(connection) as session:
            products = ProductRepository(session)
            category = products.ensure_category("food", "Food", "aprons", "Aprons", "https://example.test")
            product, _ = products.upsert(
                NormalizedProduct(
                    source_product_id="shop-42", name="Mock Apron", brand="TestBrand",
                    industry_slug="food", category_slug="aprons", price_jpy=1200,
                    description="For storefront tests", colors=["black", "white"], sizes=["M", "L"],
                    product_url="https://example.test/products/42", scraped_at=datetime.now(timezone.utc),
                ), category.id,
            )
            session.flush()
            repository = ShoppingRepository(session)
            yield ShoppingService(repository), repository, product.id
            session.commit()
    Base.metadata.drop_all(engine)


def sign_in(service, name="Test User", email="test@example.com"):
    return service.mock_sign_in(name, email)


def test_sign_in_reuses_customer_and_validates_input(shopping):
    service, _, _ = shopping
    first = sign_in(service)
    second = sign_in(service, "Updated User")
    assert first.customer_id == second.customer_id
    assert first.id != second.id
    assert second.customer.name == "Updated User"
    with pytest.raises(ShoppingError, match="valid email"):
        service.mock_sign_in("User", "invalid")


def test_cart_ownership_totals_and_approved_receipt(shopping):
    service, _, product_id = shopping
    owner, stranger = sign_in(service), sign_in(service, "Other", "other@example.com")
    cart = service.create_cart(owner.id)
    with pytest.raises(ShoppingError, match="does not belong"):
        service.get_cart(stranger.id, cart.id)
    with pytest.raises(ShoppingError, match="valid color"):
        service.add_item(owner.id, cart.id, product_id, 1, "red", "M")
    cart = service.add_item(owner.id, cart.id, product_id, 2, "black", "M")
    assert cart.items[0].unit_price_jpy == 1200
    cart = service.update_item(owner.id, cart.id, cart.items[0].id, 3)
    order, confirmation = service.create_checkout(owner.id, cart.id)
    assert order.total_jpy == 3600
    assert order.line_items[0]["line_total_jpy"] == 3600
    with pytest.raises(ShoppingError, match="does not belong"):
        service.get_order(stranger.id, order.id)
    approved = service.decide_payment(owner.id, order.id, confirmation.token, "approve")
    assert approved.status == "approved"
    assert service.get_cart(owner.id, cart.id).status == "checked_out"
    assert service.decide_payment(owner.id, order.id, confirmation.token, "approve").status == "approved"
    with pytest.raises(ShoppingError, match="cannot be changed"):
        service.decide_payment(owner.id, order.id, confirmation.token, "reject")


def test_rejection_preserves_cart_and_allows_retry(shopping):
    service, _, product_id = shopping
    mock_session = sign_in(service)
    cart = service.create_cart(mock_session.id)
    service.add_item(mock_session.id, cart.id, product_id, 1, "white", "L")
    first, token = service.create_checkout(mock_session.id, cart.id)
    assert service.decide_payment(mock_session.id, first.id, token.token, "reject").status == "rejected"
    assert service.get_cart(mock_session.id, cart.id).status == "active"
    second, token2 = service.create_checkout(mock_session.id, cart.id)
    assert second.id != first.id
    assert service.decide_payment(mock_session.id, second.id, token2.token, "approve").status == "approved"


def test_expired_confirmation_and_session(shopping):
    service, repository, product_id = shopping
    mock_session = sign_in(service)
    cart = service.create_cart(mock_session.id)
    service.add_item(mock_session.id, cart.id, product_id, 1, "black", "M")
    order, confirmation = service.create_checkout(mock_session.id, cart.id)
    confirmation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    repository.session.flush()
    with pytest.raises(ShoppingError, match="expired"):
        service.decide_payment(mock_session.id, order.id, confirmation.token, "approve")
    _, renewed = service.create_checkout(mock_session.id, cart.id)
    assert renewed.token != confirmation.token
    mock_session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    repository.session.flush()
    with pytest.raises(ShoppingError, match="session expired"):
        service.get_cart(mock_session.id, cart.id)


def test_empty_cart_quantity_and_confirmation_validation(shopping):
    service, _, product_id = shopping
    mock_session = sign_in(service)
    cart = service.create_cart(mock_session.id)
    with pytest.raises(ShoppingError, match="at least one"):
        service.create_checkout(mock_session.id, cart.id)
    with pytest.raises(ShoppingError, match="between 1 and 100"):
        service.add_item(mock_session.id, cart.id, product_id, 0, "black", "M")
    service.add_item(mock_session.id, cart.id, product_id, 1, "black", "M")
    order, _ = service.create_checkout(mock_session.id, cart.id)
    with pytest.raises(ShoppingError, match="invalid"):
        service.decide_payment(mock_session.id, order.id, "wrong", "approve")
