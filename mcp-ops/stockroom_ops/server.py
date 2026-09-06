"""MCP Apps server: read-only admin operations for the stockroom PoC.

Read-only is deliberate. Product text is crawled from a live website, so it is
attacker-influenceable; exposing order cancellation or price edits as tools
would let a prompt injection trigger them. Nothing here mutates state.
"""

from __future__ import annotations

import argparse
import logging
from typing import Annotated, Any

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BeforeValidator, Field

from stockroom_ops.api import ApiError, StockroomApi
from stockroom_ops.catalog import normalize_tokens
from stockroom_ops.config import VIEWS_DIR, Settings

log = logging.getLogger(__name__)

def _as_text(value: Any) -> Any:
    """Accept a list even though the schema advertises a string.

    The schema is a plain string on purpose -- a union makes models omit the
    argument entirely. But some hosts still send ["files","drinks"], and
    rejecting that would be a validation error the model cannot see past.
    """
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value)
    return value


LooseText = Annotated[str, BeforeValidator(_as_text)]

DASHBOARD_URI = "ui://stockroom/dashboard"
ORDERS_URI = "ui://stockroom/orders"
CATALOG_URI = "ui://stockroom/catalog"
PRODUCT_URI = "ui://stockroom/product"
USERS_URI = "ui://stockroom/users"


def read_only() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def load_view(name: str) -> str:
    path = VIEWS_DIR / name
    if not path.exists():
        raise SystemExit(
            f"Missing built View {path}.\nRun: cd views && npm install && npm run build"
        )
    return path.read_text(encoding="utf-8")


def absolute_images(payload: dict[str, Any], public_base: str) -> dict[str, Any]:
    """Rewrite relative /media paths to absolute, browser-reachable URLs.

    The API returns "/media/<key>", which resolves against the *iframe's*
    origin -- not the API's -- so inside a View it would 404. The CSP allowance
    on the product Views names the same origin.
    """
    base = public_base.rstrip("/")

    def fix(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("/media/"):
            return base + value
        if isinstance(value, list):
            return [fix(v) for v in value]
        if isinstance(value, dict):
            return {k: fix(v) for k, v in value.items()}
        return value

    return fix(payload)


def build_server(settings: Settings) -> tuple[MCPServer, StockroomApi]:
    apps = Apps()
    api = StockroomApi(settings.api_base, settings.admin_email)

    # Product Views load images from the Go service, a different origin than
    # the iframe. Without this the deny-by-default CSP blocks them.
    image_csp = ResourceCsp(resource_domains=[settings.public_api_base])

    # The View is a single self-contained HTML file: the host renders ui://
    # resources in a sandboxed iframe under a deny-by-default CSP, so nothing
    # may be loaded from outside the document.
    apps.add_html_resource(
        DASHBOARD_URI,
        load_view("dashboard.html"),
        name="Stockroom dashboard",
        description="Catalog, order and revenue overview.",
    )
    apps.add_html_resource(
        ORDERS_URI,
        load_view("orders.html"),
        name="Orders",
        description="Every customer order with its line items.",
    )
    apps.add_html_resource(
        CATALOG_URI,
        load_view("catalog.html"),
        name="Catalog",
        description="Products with their S/M/L price ladder.",
        csp=image_csp,
    )
    apps.add_html_resource(
        PRODUCT_URI,
        load_view("product.html"),
        name="Product",
        description="One product in full, with photos.",
        csp=image_csp,
    )
    apps.add_html_resource(
        USERS_URI,
        load_view("users.html"),
        name="Users",
        description="Accounts with cart and order activity.",
    )

    @apps.tool(
        resource_uri=DASHBOARD_URI,
        name="get_dashboard",
        title="Stockroom dashboard",
        description=(
            "Show the stockroom operations dashboard: catalog size, order counts, "
            "revenue, and per-category product totals. Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def get_dashboard(days: int = 30) -> dict[str, Any]:
        """Return dashboard figures for the last `days` days (1-365)."""
        days = max(1, min(int(days), 365))
        try:
            return await api.stats(days)
        except ApiError as exc:
            # Surface a usable message rather than an empty iframe.
            return {"error": {"code": exc.code, "message": str(exc)}}

    @apps.tool(
        resource_uri=ORDERS_URI,
        name="list_orders",
        title="List orders",
        description=(
            "List customer orders newest first, with line items, totals and status. "
            "Optionally filter by status (pending, confirmed, cancelled). Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def list_orders(status: str | None = None, limit: int = 50) -> dict[str, Any]:
        """List orders, optionally filtered by status."""
        if status and status not in ("pending", "confirmed", "cancelled"):
            return {
                "error": {
                    "code": "invalid_request",
                    "message": "status must be pending, confirmed or cancelled.",
                }
            }
        try:
            return await api.orders(status, max(1, min(int(limit), 200)))
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}

    @apps.tool(
        resource_uri=CATALOG_URI,
        name="list_products",
        title="List products",
        description=(
            "THE tool for any request about multiple products, including "
            "'show me category X and Y'. Returns products grouped by category, "
            "each with its full details: sizes, unit prices and image URLs.\n\n"
            "Pass the user's own words straight into `categories` — slugs, English "
            "or Japanese all match, e.g. ['files', 'drinks'] or ['ファイル']. The "
            "response renders as an interactive panel showing exactly those "
            "categories.\n\n"
            "The result is already complete: do NOT follow up with get_product for "
            "each item. One call answers the whole request. Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def list_products(
        # A plain string, deliberately. A union schema (anyOf array/string/null)
        # makes models omit the argument entirely -- which looked exactly like
        # "the filter is broken".
        categories: Annotated[
            LooseText,
            Field(
                default="",
                description=(
                    "Comma-separated categories to show, e.g. 'files, drinks' or "
                    "'ファイル、ドリンク'. Slugs, English words and Japanese names all "
                    "match — you do not need to know the exact category names. "
                    "Leave empty to show every category."
                ),
            ),
        ] = "",
        q: Annotated[
            LooseText,
            Field(default="", description="Free-text search over product name and description."),
        ] = "",
        include_inactive: Annotated[
            bool,
            Field(default=True, description="Include deactivated products."),
        ] = True,
    ) -> dict[str, Any]:
        """List products grouped by category, optionally limited to some categories."""
        # One request. The API resolves the words to slugs, filters in SQL and
        # returns category-first groups, so there is nothing to fetch first and
        # nothing to regroup after.
        try:
            data = await api.products(
                q, normalize_tokens(categories), include_inactive
            )
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}
        return absolute_images(data, settings.public_api_base)

    @apps.tool(
        resource_uri=PRODUCT_URI,
        # app-only: the model cannot see or call this. Left visible, it fans
        # out one call per product to "work around" list_products instead of
        # filtering. Views can still call it; the model must use list_products.
        visibility=["app"],
        name="get_product",
        title="Get product",
        description=(
            "Details for ONE product, identified by its numeric catalog id.\n\n"
            "Use this only when the user asks about a single specific product "
            "('tell me about product 34'). Do NOT call it repeatedly to enumerate "
            "several products or to expand a category — list_products already "
            "returns sizes, prices and images for many products in one call. "
            "Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def get_product(product_id: int) -> dict[str, Any]:
        """Return a single product by its catalog id."""
        try:
            data = await api.product(int(product_id))
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}
        return absolute_images(data, settings.public_api_base)

    @apps.tool(
        resource_uri=USERS_URI,
        name="list_users",
        title="List users",
        description=(
            "List accounts with their open cart lines, order count and lifetime spend. "
            "Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def list_users(limit: int = 50) -> dict[str, Any]:
        """List user accounts."""
        try:
            return await api.users(max(1, min(int(limit), 200)))
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}

    server = MCPServer(
        name="stockroom-ops",
        version="0.1.0",
        instructions=(
            "Read-only operations view over a local RAKSUL stockroom PoC. "
            "The catalog is a fixed crawled snapshot, not live inventory."
        ),
        extensions=[apps],
    )
    return server, api


def main() -> None:
    parser = argparse.ArgumentParser(description="Stockroom ops MCP Apps server")
    parser.add_argument(
        "--transport", choices=("stdio", "streamable-http"), default="streamable-http"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    settings = Settings.from_env()
    server, _api = build_server(settings)

    if args.transport == "stdio":
        server.run("stdio")
        return

    import uvicorn

    log.info("MCP endpoint http://%s:%s/mcp", settings.host, settings.port)
    log.info("backend %s as %s", settings.api_base, settings.admin_email)
    uvicorn.run(
        server.streamable_http_app(json_response=True),
        host=settings.host,
        port=settings.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
