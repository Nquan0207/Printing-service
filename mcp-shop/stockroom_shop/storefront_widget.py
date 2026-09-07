"""Locates the built storefront View.

The View runs in the host's sandboxed iframe, so it is browser code whatever
the server is written in. It lives in `views/` and is built by vite, the same
arrangement as mcp-ops: `vite-plugin-singlefile` inlines the CSS and JS into
one HTML file because the iframe CSP is deny-by-default and there is no origin
to fetch a second file from.

It used to be a 457-line raw string in this module, which meant no syntax
highlighting, no typecheck and no bundler.
"""

from __future__ import annotations

from pathlib import Path


STOREFRONT_URI = "ui://widget/raksul-stockroom-v3.html"

VIEWS_DIR = Path(__file__).resolve().parents[1] / "views" / "dist"


def load_view(name: str) -> str:
    path = VIEWS_DIR / name
    if not path.exists():
        raise SystemExit(
            f"Missing built View {path}.\nRun: cd mcp-shop/views && npm install && npm run build"
        )
    return path.read_text(encoding="utf-8")


STOREFRONT_HTML = load_view("storefront.html")

# Focused panels beside the full storefront: one order, one job. A shopper
# asking "what did I buy" should not be handed a catalog to scroll past.
ORDERS_URI = "ui://widget/raksul-orders-v1.html"
CART_URI = "ui://widget/raksul-cart-v1.html"

ORDERS_HTML = load_view("orders.html")
CART_HTML = load_view("cart.html")
