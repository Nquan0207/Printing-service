from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.mcp_server.tools import (
    add_cart_item_handler,
    create_cart_handler,
    create_mock_checkout_handler,
    decide_mock_payment_handler,
    get_catalog_info_handler,
    get_cart_handler,
    get_mock_order_handler,
    get_mock_session_handler,
    get_product_handler,
    list_categories_handler,
    remove_cart_item_handler,
    search_products_handler,
    mock_sign_in_handler,
    update_cart_item_handler,
)
from app.mcp_server.storefront_widget import STOREFRONT_HTML, STOREFRONT_URI

mcp = FastMCP(
    "raksul-product-catalog",
    instructions=(
        "Use only the local PostgreSQL catalog snapshot for storefront activity. "
        "Never open or navigate to the supplier website during shopping. Render the embedded "
        "MCP App with open_storefront. Before deciding a mock payment, summarize the order and "
        "ask the user to explicitly approve or reject it. No real payment or authentication occurs."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
)


def read_only_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def write_annotations(*, idempotent: bool = False) -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=idempotent,
        openWorldHint=False,
    )


WIDGET_ACCESSIBLE = {"openai/widgetAccessible": True}


@mcp.resource(
    STOREFRONT_URI,
    name="RAKSUL mock storefront",
    description="Interactive mock product browser, cart, and payment confirmation.",
    mime_type="text/html;profile=mcp-app",
    meta={
        "openai/widgetDescription": "Database-backed mock storefront with sign-in, cart, and explicit simulated payment confirmation.",
        "openai/widgetCSP": {"resource_domains": ["https://cdn-apparel.raksul.com"]},
    },
)
def storefront_widget() -> str:
    return STOREFRONT_HTML


@mcp.tool(
    title="Search RAKSUL products",
    annotations=read_only_annotations(),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def search_products(
    query: str | None = None,
    industry: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    color: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search the limited local RAKSUL Apparel snapshot.

    Empty results mean no match in this snapshot only. Prices are stored
    snapshot prices, not real-time quotes.
    """
    return search_products_handler(
        query, industry, category, brand, color, min_price, max_price, limit
    )


@mcp.tool(
    title="Get RAKSUL product",
    annotations=read_only_annotations(),
    structured_output=True,
)
def get_product(product_id: int) -> dict[str, Any]:
    """Return one product by local database ID from the limited snapshot."""
    return get_product_handler(product_id)


@mcp.tool(
    title="List catalog categories",
    annotations=read_only_annotations(),
    structured_output=True,
)
def list_categories() -> dict[str, Any]:
    """List industries and categories supported by the current snapshot."""
    return list_categories_handler()


@mcp.tool(
    title="Get catalog information",
    annotations=read_only_annotations(),
    structured_output=True,
)
def get_catalog_info() -> dict[str, Any]:
    """Return snapshot size, scope, supported fields, and known limitations."""
    return get_catalog_info_handler()


@mcp.tool(
    title="Open RAKSUL mock storefront",
    annotations=read_only_annotations(),
    meta={
        "ui": {"resourceUri": STOREFRONT_URI},
        "openai/outputTemplate": STOREFRONT_URI,
    },
    structured_output=True,
)
def open_storefront(query: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Render the embedded database storefront. Never open an external website or browser."""
    return search_products_handler(query=query, limit=min(max(limit, 1), 40))


@mcp.tool(
    title="Mock sign in",
    annotations=write_annotations(),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def mock_sign_in(name: str, email: str) -> dict[str, Any]:
    """Create a local 24-hour mock session using a name and email; no password or real authentication."""
    return mock_sign_in_handler(name, email)


@mcp.tool(
    title="Get mock session",
    annotations=read_only_annotations(),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def get_mock_session(session_id: str) -> dict[str, Any]:
    """Read a local mock customer session and its expiry."""
    return get_mock_session_handler(session_id)


@mcp.tool(
    title="Create shopping cart",
    annotations=write_annotations(),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def create_cart(session_id: str) -> dict[str, Any]:
    """Create an empty cart owned by the supplied mock session."""
    return create_cart_handler(session_id)


@mcp.tool(
    title="Get shopping cart",
    annotations=read_only_annotations(),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def get_cart(session_id: str, cart_id: str) -> dict[str, Any]:
    """Return a mock cart and its server-calculated total."""
    return get_cart_handler(session_id, cart_id)


@mcp.tool(
    title="Add product to cart",
    annotations=write_annotations(),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def add_cart_item(
    session_id: str,
    cart_id: str,
    product_id: int,
    quantity: int = 1,
    color: str | None = None,
    size: str | None = None,
) -> dict[str, Any]:
    """Add a priced snapshot product with validated options to an active cart."""
    return add_cart_item_handler(session_id, cart_id, product_id, quantity, color, size)


@mcp.tool(
    title="Update cart quantity",
    annotations=write_annotations(idempotent=True),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def update_cart_item(session_id: str, cart_id: str, item_id: int, quantity: int) -> dict[str, Any]:
    """Set a cart item's quantity to a value from 1 through 100."""
    return update_cart_item_handler(session_id, cart_id, item_id, quantity)


@mcp.tool(
    title="Remove cart item",
    annotations=write_annotations(idempotent=False),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def remove_cart_item(session_id: str, cart_id: str, item_id: int) -> dict[str, Any]:
    """Remove one item from an active mock cart."""
    return remove_cart_item_handler(session_id, cart_id, item_id)


@mcp.tool(
    title="Create mock checkout",
    annotations=write_annotations(idempotent=True),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def create_mock_checkout(session_id: str, cart_id: str) -> dict[str, Any]:
    """Create a pending mock order and confirmation challenge. Ask the user to approve or reject before continuing."""
    return create_mock_checkout_handler(session_id, cart_id)


@mcp.tool(
    title="Get mock order receipt",
    annotations=read_only_annotations(),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def get_mock_order(session_id: str, order_id: str) -> dict[str, Any]:
    """Retrieve a session-owned mock order or approved receipt from PostgreSQL."""
    return get_mock_order_handler(session_id, order_id)


@mcp.tool(
    title="Decide mock payment",
    annotations=write_annotations(idempotent=True),
    meta=WIDGET_ACCESSIBLE,
    structured_output=True,
)
def decide_mock_payment(
    session_id: str,
    order_id: str,
    confirmation_token: str,
    decision: str,
) -> dict[str, Any]:
    """After explicit user confirmation, approve or reject a challenged mock payment; never moves money."""
    return decide_mock_payment_handler(session_id, order_id, confirmation_token, decision)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAKSUL catalog MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
