from __future__ import annotations

from typing import Any

from app.database.connection import session_scope
from app.repositories.product_repository import ProductRepository
from app.repositories.shopping_repository import ShoppingRepository
from app.services.product_service import ProductService
from app.services.shopping_service import ShoppingError, ShoppingService

CATALOG_SCOPE = {
    "data_source": "fixed_catalog_snapshot",
    "catalog_complete": False,
    "real_time": False,
}


def _product_payload(product) -> dict[str, Any]:
    return {
        "id": product.id,
        "source_product_id": product.source_product_id,
        "name": product.name,
        "brand": product.brand,
        "industry": product.category.industry.slug,
        "industry_name": product.category.industry.name,
        "category": product.category.slug,
        "category_name": product.category.name,
        "price_jpy": product.price_jpy,
        "description": product.description,
        "colors": product.colors or [],
        "sizes": product.sizes or [],
        "stock_status": product.stock_status,
        "printing_available": product.printing_available,
        "image_url": product.image_url,
        "scraped_at": product.scraped_at.isoformat() if product.scraped_at else None,
    }


def search_products_handler(
    query: str | None = None,
    industry: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    color: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search the limited local RAKSUL catalog snapshot."""
    with session_scope() as session:
        service = ProductService(ProductRepository(session))
        products = service.search_products(
            query=query,
            industry=industry,
            category=category,
            brand=brand,
            color=color,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
        )
        results = [_product_payload(product) for product in products]

    if not results:
        return {
            "status": "no_match_in_current_catalog",
            "results": [],
            "result_count": 0,
            "message": (
                "No matching product was found in the current catalog snapshot. "
                "This does not mean it is absent from the full RAKSUL website."
            ),
            "scope": CATALOG_SCOPE,
        }
    return {
        "status": "ok",
        "results": results,
        "result_count": len(results),
        "scope": CATALOG_SCOPE,
    }


def get_product_handler(product_id: int) -> dict[str, Any]:
    """Get one product from the local snapshot by database ID."""
    with session_scope() as session:
        service = ProductService(ProductRepository(session))
        product = service.get_product(product_id)
        payload = _product_payload(product) if product else None

    if payload is None:
        return {
            "status": "not_found_in_current_catalog",
            "product": None,
            "message": f"Product ID {product_id} is not in the current snapshot.",
            "scope": CATALOG_SCOPE,
        }
    return {"status": "ok", "product": payload, "scope": CATALOG_SCOPE}


def list_categories_handler() -> dict[str, Any]:
    """List industries and categories represented by the local snapshot."""
    with session_scope() as session:
        service = ProductService(ProductRepository(session))
        categories = service.list_categories()
        results = [
            {
                "industry": item.industry.slug,
                "industry_name": item.industry.name,
                "category": item.slug,
                "category_name": item.name,
                "enabled": item.enabled,
            }
            for item in categories
        ]
    return {"status": "ok", "categories": results, "scope": CATALOG_SCOPE}


def get_catalog_info_handler() -> dict[str, Any]:
    """Describe snapshot coverage and unsupported real-time fields."""
    with session_scope() as session:
        stats = ProductRepository(session).stats()
    return {
        "status": "ok",
        "source": "RAKSUL Apparel",
        "catalog_type": "fixed_snapshot",
        "catalog_complete": False,
        "product_count": stats["products"],
        "category_count": stats["categories"],
        "industry_count": stats["industries"],
        "supported_fields": [
            "name", "brand", "industry", "category", "price_jpy",
            "colors", "sizes", "description", "image_url",
        ],
        "unsupported_fields": [
            "live_stock", "shipping_fee", "delivery_date",
            "printing_quote", "real_time_price",
        ],
        "scope": CATALOG_SCOPE,
    }


def _cart_payload(cart) -> dict[str, Any]:
    items = [ShoppingService._line_snapshot(item) for item in cart.items]
    return {
        "id": cart.id,
        "status": cart.status,
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "total_jpy": sum(item["line_total_jpy"] for item in items),
        "created_at": cart.created_at.isoformat() if cart.created_at else None,
        "updated_at": cart.updated_at.isoformat() if cart.updated_at else None,
    }


def _order_payload(order) -> dict[str, Any]:
    return {
        "id": order.id,
        "cart_id": order.cart_id,
        "status": order.status,
        "total_jpy": order.total_jpy,
        "items": order.line_items,
        "mock_payment": True,
        "message": "This is a simulation. No payment method was collected and no money moved.",
        "receipt": order.status == "approved",
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "decided_at": order.decided_at.isoformat() if order.decided_at else None,
    }


def _session_payload(mock_session) -> dict[str, Any]:
    return {
        "id": mock_session.id,
        "customer": {
            "id": mock_session.customer.id,
            "name": mock_session.customer.name,
            "email": mock_session.customer.email,
        },
        "created_at": mock_session.created_at.isoformat() if mock_session.created_at else None,
        "expires_at": mock_session.expires_at.isoformat(),
        "mock_authentication": True,
    }


def _shopping_action(action) -> dict[str, Any]:
    try:
        with session_scope() as session:
            service = ShoppingService(ShoppingRepository(session))
            kind, value = action(service)
            if kind == "cart":
                payload = _cart_payload(value)
            elif kind == "order":
                payload = _order_payload(value)
            elif kind == "session":
                payload = _session_payload(value)
            elif kind == "checkout":
                order, confirmation = value
                payload = {
                    "order": _order_payload(order),
                    "confirmation": {
                        "token": confirmation.token,
                        "expires_at": confirmation.expires_at.isoformat(),
                        "instruction": (
                            "Summarize this mock order and ask the user to explicitly approve or reject it. "
                            "Do not call decide_mock_payment until the user makes that decision."
                        ),
                    },
                }
            else:
                raise RuntimeError(f"Unsupported shopping payload kind: {kind}")
        if kind == "checkout":
            return {"status": "confirmation_required", **payload, "scope": CATALOG_SCOPE}
        return {"status": "ok", kind: payload, "scope": CATALOG_SCOPE}
    except ShoppingError as exc:
        return {
            "status": "error",
            "error": {"code": exc.code, "message": str(exc)},
            "scope": CATALOG_SCOPE,
        }


def mock_sign_in_handler(name: str, email: str) -> dict[str, Any]:
    return _shopping_action(lambda service: ("session", service.mock_sign_in(name, email)))


def get_mock_session_handler(session_id: str) -> dict[str, Any]:
    return _shopping_action(lambda service: ("session", service.get_session(session_id)))


def create_cart_handler(session_id: str) -> dict[str, Any]:
    return _shopping_action(lambda service: ("cart", service.create_cart(session_id)))


def get_cart_handler(session_id: str, cart_id: str) -> dict[str, Any]:
    return _shopping_action(lambda service: ("cart", service.get_cart(session_id, cart_id)))


def add_cart_item_handler(
    session_id: str,
    cart_id: str,
    product_id: int,
    quantity: int = 1,
    color: str | None = None,
    size: str | None = None,
) -> dict[str, Any]:
    return _shopping_action(
        lambda service: (
            "cart",
            service.add_item(session_id, cart_id, product_id, quantity, color, size),
        )
    )


def update_cart_item_handler(session_id: str, cart_id: str, item_id: int, quantity: int) -> dict[str, Any]:
    return _shopping_action(
        lambda service: ("cart", service.update_item(session_id, cart_id, item_id, quantity))
    )


def remove_cart_item_handler(session_id: str, cart_id: str, item_id: int) -> dict[str, Any]:
    return _shopping_action(
        lambda service: ("cart", service.remove_item(session_id, cart_id, item_id))
    )


def create_mock_checkout_handler(session_id: str, cart_id: str) -> dict[str, Any]:
    return _shopping_action(
        lambda service: ("checkout", service.create_checkout(session_id, cart_id))
    )


def get_mock_order_handler(session_id: str, order_id: str) -> dict[str, Any]:
    return _shopping_action(lambda service: ("order", service.get_order(session_id, order_id)))


def decide_mock_payment_handler(
    session_id: str, order_id: str, confirmation_token: str, decision: str
) -> dict[str, Any]:
    return _shopping_action(
        lambda service: (
            "order",
            service.decide_payment(session_id, order_id, confirmation_token, decision),
        )
    )
