from __future__ import annotations

import argparse
import os
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from app.mcp_server.storefront_widget import STOREFRONT_HTML, STOREFRONT_URI
from app.mcp_server.tools import (
    add_to_cart_handler,
    get_cart_handler,
    get_order_handler,
    get_product_handler,
    get_quote_handler,
    list_categories_handler,
    mock_sign_in_handler,
    place_order_handler,
    prepare_order_handler,
    remove_cart_item_handler,
    search_products_handler,
)

mcp = FastMCP(
    "raksul-stockroom-commerce",
    instructions=(
        "Render the embedded Stockroom storefront and use only the configured Go backend, "
        "whose PostgreSQL database is the commerce source of truth. Never open a supplier website. "
        "Before place_order, call prepare_order, summarize the cart and address, and obtain an explicit "
        "approve or reject decision. This is a mock checkout and never moves money."
    ),
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
)


def annotations(read_only: bool, idempotent: bool = True) -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=False,
        idempotentHint=idempotent,
        openWorldHint=False,
    )


def owner(ctx: Context) -> str:
    return str(id(ctx.session))


def _origin(url: str) -> str | None:
    """Return scheme://host[:port] for CSP, or None for an unset/invalid URL."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


# The iframe never talks to the Go API directly; UI actions go through MCP tools.
# Only product images may need a browser-reachable origin.
ASSET_BASE_URL = (
    os.getenv("STOCKROOM_PUBLIC_ASSET_URL")
    or os.getenv("STOCKROOM_API_URL")
    or "http://127.0.0.1:8080"
)

PUBLIC_ASSET_ORIGIN = _origin(ASSET_BASE_URL.strip())
RESOURCE_DOMAINS = [PUBLIC_ASSET_ORIGIN] if PUBLIC_ASSET_ORIGIN else []

# Standard MCP Apps visibility plus OpenAI compatibility.
# Keeping model + app means Claude/the model can call a tool and the embedded app can call it too.
APP_CALLABLE = {
    "ui": {"visibility": ["model", "app"]},
    "openai/widgetAccessible": True,
}

OPEN_STOREFRONT_META = {
    "ui": {
        "resourceUri": STOREFRONT_URI,
        "visibility": ["model", "app"],
    },
    # Compatibility for ChatGPT Apps SDK hosts.
    "openai/outputTemplate": STOREFRONT_URI,
    "openai/widgetAccessible": True,
}


@mcp.resource(
    STOREFRONT_URI,
    name="RAKSUL Stockroom mock storefront",
    description="Embedded database-backed catalog, quote, cart, and mock confirmation UI.",
    mime_type="text/html;profile=mcp-app",
    meta={
        "ui": {
            "prefersBorder": True,
            "csp": {
                # No fetch/XHR is made by the iframe. All data operations use tools/call.
                "connectDomains": [],
                "resourceDomains": RESOURCE_DOMAINS,
            },
        },
        # Compatibility for ChatGPT Apps SDK hosts.
        "openai/widgetDescription": "Browse the Stockroom PostgreSQL catalog and explicitly confirm a mock order.",
        "openai/widgetCSP": {
            "connect_domains": [],
            "resource_domains": RESOURCE_DOMAINS,
        },
    },
)
def storefront_widget() -> str:
    return STOREFRONT_HTML


@mcp.tool(
    title="Open embedded RAKSUL Stockroom storefront",
    annotations=annotations(True),
    meta=OPEN_STOREFRONT_META,
    structured_output=True,
)
def open_storefront(
    query: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Render the embedded database storefront. Never open an external supplier website or browser."""
    return search_products_handler(query=query, category=category, limit=limit)


@mcp.tool(title="Mock sign in", annotations=annotations(False, False), meta=APP_CALLABLE, structured_output=True)
def mock_sign_in(name: str, email: str, ctx: Context) -> dict[str, Any]:
    """Select or create a demo user in the Stockroom database; no password or real authentication."""
    return mock_sign_in_handler(owner(ctx), name, email)


@mcp.tool(title="Search Stockroom products", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def search_products(
    query: str | None = None,
    category: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    limit: int = 20,
    per_category: int | None = None,
) -> dict[str, Any]:
    """Search active products in the backend Stockroom PostgreSQL catalog."""
    return search_products_handler(query, category, min_price, max_price, limit, per_category)


@mcp.tool(title="Get Stockroom product", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def get_product(product_id: int) -> dict[str, Any]:
    return get_product_handler(product_id)


@mcp.tool(title="List Stockroom categories", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def list_categories() -> dict[str, Any]:
    return list_categories_handler()


@mcp.tool(title="Get mock quote", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def get_quote(product_id: int, size_id: int, quantity: int, ctx: Context) -> dict[str, Any]:
    """Return backend-calculated integer-JPY mock pricing for one product size and quantity."""
    return get_quote_handler(owner(ctx), product_id, size_id, quantity)


@mcp.tool(title="Get cart", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def get_cart(ctx: Context) -> dict[str, Any]:
    return get_cart_handler(owner(ctx))


@mcp.tool(title="Add to cart", annotations=annotations(False, False), meta=APP_CALLABLE, structured_output=True)
def add_to_cart(product_id: int, size_id: int, quantity: int, ctx: Context) -> dict[str, Any]:
    """Add quantity to the selected product-size line in the current demo user's database cart."""
    return add_to_cart_handler(owner(ctx), product_id, size_id, quantity)


@mcp.tool(title="Remove cart item", annotations=annotations(False, True), meta=APP_CALLABLE, structured_output=True)
def remove_cart_item(item_id: int, ctx: Context) -> dict[str, Any]:
    return remove_cart_item_handler(owner(ctx), item_id)


@mcp.tool(title="Prepare mock order", annotations=annotations(False, False), meta=APP_CALLABLE, structured_output=True)
def prepare_order(shipping_address: str, ctx: Context) -> dict[str, Any]:
    """Snapshot cart and address into a 15-minute confirmation challenge; ask the user before proceeding."""
    return prepare_order_handler(owner(ctx), shipping_address)


@mcp.tool(title="Place or reject mock order", annotations=annotations(False, True), meta=APP_CALLABLE, structured_output=True)
def place_order(confirmation_token: str, decision: str, ctx: Context) -> dict[str, Any]:
    """Use only after explicit user approval or rejection. Approval writes the backend order; rejection preserves the cart."""
    return place_order_handler(owner(ctx), confirmation_token, decision)


@mcp.tool(title="Get mock order", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def get_order(order_number: str, ctx: Context) -> dict[str, Any]:
    return get_order_handler(owner(ctx), order_number)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAKSUL Stockroom commerce MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
