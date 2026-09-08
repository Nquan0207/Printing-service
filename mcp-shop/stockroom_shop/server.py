from __future__ import annotations

import argparse
import os
import secrets
import threading
from typing import Any
from urllib.parse import urlparse
import weakref

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from stockroom_shop.storefront_widget import (
    CART_HTML,
    CART_URI,
    ORDERS_HTML,
    ORDERS_URI,
    STOREFRONT_HTML,
    STOREFRONT_URI,
)
from stockroom_shop.tools import (
    order_history_handler,
    sign_out_handler,
    STATE,
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
    update_cart_item_handler,
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


# Per-MCP-session identity. Carts, quotes and confirmations are keyed on this,
# so two chat users talking to one server never see each other's state.
#
# This used to be str(id(ctx.session)). That is a memory address: CPython
# recycles it once a session is collected, so a new session could land on a
# dead one's key and inherit its signed-in user and pending confirmations. A
# subprocess per session used to hide that; one shared server does not.
#
# A weak key means the entry disappears with the session rather than pinning it
# alive, and the finalizer drops the commerce state that belonged to it.
_OWNER_KEYS: "weakref.WeakKeyDictionary[Any, str]" = weakref.WeakKeyDictionary()
_OWNER_LOCK = threading.Lock()


def owner(ctx: Context) -> str:
    session = ctx.session
    with _OWNER_LOCK:
        key = _OWNER_KEYS.get(session)
        if key is not None:
            return key
        key = secrets.token_urlsafe(18)
        try:
            _OWNER_KEYS[session] = key
        except TypeError:
            # Not weak-referenceable: fall back to the old behaviour rather
            # than failing the call, and accept the recycling risk.
            return str(id(session))
        weakref.finalize(session, forget_owner, key)
        return key


def forget_owner(key: str) -> None:
    """Drop one session's commerce state once its session is gone."""
    with STATE.lock:
        STATE.users.pop(key, None)
        for token, confirmation in list(STATE.confirmations.items()):
            if confirmation.owner_key == key:
                STATE.confirmations.pop(token, None)


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


def _panel_meta(uri: str, description: str) -> dict[str, Any]:
    """Resource meta for a focused panel.

    connectDomains stays empty: these panels fetch nothing themselves, every
    read goes back through tools/call. resourceDomains is what lets product
    images load from the Go service, a different origin than the iframe.
    """
    return {
        "ui": {
            "prefersBorder": True,
            "csp": {"connectDomains": [], "resourceDomains": RESOURCE_DOMAINS},
        },
        "openai/widgetDescription": description,
        "openai/widgetCSP": {"connect_domains": [], "resource_domains": RESOURCE_DOMAINS},
    }


@mcp.resource(
    ORDERS_URI,
    name="RAKSUL Stockroom order history",
    description="The shopper's own past orders with their line items.",
    mime_type="text/html;profile=mcp-app",
    meta=_panel_meta(ORDERS_URI, "Past orders for the signed-in shopper."),
)
def orders_widget() -> str:
    return ORDERS_HTML


@mcp.resource(
    CART_URI,
    name="RAKSUL Stockroom cart",
    description="The current cart, with removal and the mock confirmation.",
    mime_type="text/html;profile=mcp-app",
    meta=_panel_meta(CART_URI, "The shopper's current cart and mock checkout."),
)
def cart_widget() -> str:
    return CART_HTML


@mcp.tool(
    title="Open embedded RAKSUL Stockroom storefront",
    annotations=annotations(True),
    meta=OPEN_STOREFRONT_META,
    structured_output=True,
)
def open_storefront(
    ctx: Context,
    query: str | None = None,
    category: str | None = None,
    limit: int = 60,
    per_category: int | None = None,
) -> dict[str, Any]:
    """Render the embedded database storefront. Never open an external supplier website or browser.

    `limit` caps the TOTAL across categories, and whole groups are trimmed once
    it is spent -- so a small limit shows every product of whichever category
    sorts first and none of the rest. `per_category` is what spreads the panel
    across the catalog; use it whenever the user wants to browse rather than to
    find one specific thing.

    The catalog is in Japanese, so `query` (a substring match over the product
    text) rarely matches an English word. Put English words in `category`,
    which folds case and separators and matches slugs and display names alike.
    """
    # A bare "open the shop" should touch every category, not spend the whole
    # limit on whichever one sorts first. It stays a small sample on purpose:
    # the View lists the categories itself and fetches a whole category when
    # one is opened, so a large payload here would only burn model context.
    if per_category is None and not query and not category:
        per_category = 3
    # owner_key rides along so the envelope carries the shopper's identity:
    # this result is what the widget renders from, and without it a signed-in
    # shopper would be shown the sign-in form again on every open.
    return search_products_handler(
        query=query, category=category, limit=limit, per_category=per_category,
        owner_key=owner(ctx),
    )


@mcp.tool(title="Mock sign in", annotations=annotations(False, False), meta=APP_CALLABLE, structured_output=True)
def mock_sign_in(name: str, email: str, ctx: Context) -> dict[str, Any]:
    """Switch to a different demo shopper. Selects or creates a database user; no password.

    DO NOT call this to start shopping. Browsing and the cart need no identity,
    and checkout collects a name and email on its own -- asking up front is the
    behaviour this replaced. Use it only when the shopper explicitly asks to
    sign in or to switch to another account. Anything already in a guest cart
    follows them to the account they name.
    """
    return mock_sign_in_handler(owner(ctx), name, email)


@mcp.tool(title="Sign out", annotations=annotations(False, False), meta=APP_CALLABLE, structured_output=True)
def sign_out(ctx: Context) -> dict[str, Any]:
    """Forget the current shopper so the next order can be placed as someone else.

    Their cart stays with their account and is waiting when they sign back in;
    the session becomes an anonymous guest again.
    """
    return sign_out_handler(owner(ctx))


@mcp.tool(title="Search Stockroom products", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def search_products(
    ctx: Context,
    query: str | None = None,
    category: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    limit: int = 20,
    per_category: int | None = None,
) -> dict[str, Any]:
    """Search active products in the backend Stockroom PostgreSQL catalog.

    THE CATALOG IS IN JAPANESE. `query` is a plain substring match over the
    product name and description, so an English word almost never matches:
    "paper" finds nothing even though the catalog has 12 コピー用紙 products.

    `category` is the parameter that understands English. It tries an exact
    slug first, then substring-matches slug and display name with case and
    separators folded, so category="paper" matches the copy_paper_toner group
    and category="drinks" matches ドリンク・フード.

    So: for an English request, put the user's words in `category`. Use `query`
    only for a Japanese term, a brand, or a model number. Passing both narrows
    to products matching the query inside those categories. Passing neither
    returns the whole catalog grouped by category.

    An empty result means no match, not an empty shop -- retry with the word in
    `category` before telling the user the catalog has nothing.
    """
    return search_products_handler(
        query, category, min_price, max_price, limit, per_category, owner_key=owner(ctx)
    )


@mcp.tool(title="Get Stockroom product", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def get_product(product_id: int) -> dict[str, Any]:
    return get_product_handler(product_id)


@mcp.tool(title="List Stockroom categories", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def list_categories() -> dict[str, Any]:
    """List every category with its product count.

    Returns names only -- no products and no prices. The chat UI renders them
    as clickable chips, so say the categories are shown rather than listing
    them all in prose.

    When the user wants to SEE products, call search_products(category=...)
    instead; this tool alone never puts a product on screen.
    """
    return list_categories_handler()


@mcp.tool(title="Get mock quote", annotations=annotations(True), meta=APP_CALLABLE, structured_output=True)
def get_quote(product_id: int, size_id: int, quantity: int, ctx: Context) -> dict[str, Any]:
    """Return backend-calculated integer-JPY mock pricing for one product size and quantity."""
    return get_quote_handler(owner(ctx), product_id, size_id, quantity)


@mcp.tool(
    title="Get cart",
    annotations=annotations(True),
    meta={
        "ui": {"resourceUri": CART_URI, "visibility": ["model", "app"]},
        "openai/outputTemplate": CART_URI,
        "openai/widgetAccessible": True,
    },
    structured_output=True,
)
def get_cart(ctx: Context) -> dict[str, Any]:
    return get_cart_handler(owner(ctx))


@mcp.tool(title="Add to cart", annotations=annotations(False, False), meta=APP_CALLABLE, structured_output=True)
def add_to_cart(product_id: int, size_id: int, quantity: int, ctx: Context) -> dict[str, Any]:
    """Add quantity to the selected product-size line in the current demo user's database cart."""
    return add_to_cart_handler(owner(ctx), product_id, size_id, quantity)


@mcp.tool(title="Remove cart item", annotations=annotations(False, True), meta=APP_CALLABLE, structured_output=True)
def remove_cart_item(item_id: int, ctx: Context) -> dict[str, Any]:
    return remove_cart_item_handler(owner(ctx), item_id)


@mcp.tool(title="Update cart item", annotations=annotations(False, True), meta=APP_CALLABLE, structured_output=True)
def update_cart_item(item_id: int, size_id: int, quantity: int, ctx: Context) -> dict[str, Any]:
    """Change one cart line's size and quantity, repricing it from the catalog.

    Switching to a size the cart already holds for that product merges the two
    lines rather than failing: one line per (product, size) is a database
    constraint, not a rule the shopper should have to know about.
    """
    return update_cart_item_handler(owner(ctx), item_id, size_id, quantity)


@mcp.tool(title="Prepare mock order", annotations=annotations(False, False), meta=APP_CALLABLE, structured_output=True)
def prepare_order(
    shipping_address: str,
    ctx: Context,
    name: str = "",
    email: str = "",
) -> dict[str, Any]:
    """Snapshot cart and address into a 15-minute confirmation challenge; ask the user before proceeding.

    Checkout is the ONE point a shopper is asked who they are -- browsing and
    the cart are anonymous, exactly like a normal shop. Pass `name` and `email`
    the first time a guest checks out. A shopper who is already identified
    needs neither, and must not be asked again.

    A `428 identity_required` reply means the shopper is still a guest: ask for
    their name and email once, then call this again with them.
    """
    return prepare_order_handler(owner(ctx), shipping_address, name, email)


@mcp.tool(title="Place or reject mock order", annotations=annotations(False, True), meta=APP_CALLABLE, structured_output=True)
def place_order(confirmation_token: str, decision: str, ctx: Context) -> dict[str, Any]:
    """Use only after explicit user approval or rejection. Approval writes the backend order; rejection preserves the cart."""
    return place_order_handler(owner(ctx), confirmation_token, decision)


@mcp.tool(
    title="Order history",
    annotations=annotations(True),
    meta={
        "ui": {"resourceUri": ORDERS_URI, "visibility": ["model", "app"]},
        "openai/outputTemplate": ORDERS_URI,
        "openai/widgetAccessible": True,
    },
    structured_output=True,
)
def order_history(ctx: Context, limit: int = 20) -> dict[str, Any]:
    """The shopper's own past orders, newest first, with their line items.

    Use it for "my orders", "what did I buy", "where is my order", "order
    history". Scoped to whoever is signed in on this session -- it takes no
    user id, so it can never be pointed at somebody else's history.

    A `428 identity_required` reply means they are still a guest: a guest has
    no history, because checkout is the first point an order is attached to a
    person. Ask which email they ordered with and sign them in.
    """
    return order_history_handler(owner(ctx), limit)


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
