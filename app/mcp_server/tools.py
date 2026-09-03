from __future__ import annotations

from typing import Any

from app.database.connection import session_scope
from app.repositories.product_repository import ProductRepository
from app.services.product_service import ProductService

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
        "product_url": product.product_url,
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
            "colors", "sizes", "description", "product_url",
        ],
        "unsupported_fields": [
            "live_stock", "shipping_fee", "delivery_date",
            "printing_quote", "real_time_price",
        ],
        "scope": CATALOG_SCOPE,
    }

