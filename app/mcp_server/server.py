from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.mcp_server.tools import (
    get_catalog_info_handler,
    get_product_handler,
    list_categories_handler,
    search_products_handler,
)

mcp = FastMCP(
    "raksul-product-catalog",
    instructions=(
        "Read-only access to a limited local RAKSUL Apparel catalog snapshot. "
        "Empty results do not prove absence from the full website. "
        "Prices are snapshot values and are not guaranteed current."
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


@mcp.tool(
    title="Search RAKSUL products",
    annotations=read_only_annotations(),
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
