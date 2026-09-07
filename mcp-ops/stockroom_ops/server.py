"""MCP Apps server: read-only admin operations for the stockroom PoC.

Read-only is deliberate. Product text is crawled from a live website, so it is
attacker-influenceable; exposing order cancellation or price edits as tools
would let a prompt injection trigger them. Nothing here mutates state.
"""

from __future__ import annotations

import argparse
import logging
from typing import Annotated, Any

from mcp.server.apps import Apps, Context, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BeforeValidator, Field

from stockroom_ops import adminauth
from stockroom_ops.adminauth import public
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

STATUSES = ("pending", "confirmed", "cancelled")


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


def _score(name: str, needle: str) -> tuple[int, int]:
    """Rank a name against what the user typed: exact, then prefix, then
    shortest containing match -- the shortest is the most specific, so
    "電池" prefers the battery over a product that merely mentions it."""
    lowered, wanted = name.lower(), needle.lower()
    if lowered == wanted:
        return (0, len(name))
    if lowered.startswith(wanted):
        return (1, len(name))
    return (2, len(name))


async def _find_product(api: StockroomApi, admin_id: int, text: str) -> dict[str, Any]:
    """Resolve a name fragment to exactly one product.

    Uses the admin catalog because it carries descriptions and inactive rows;
    an admin asking about a deactivated product should still get an answer.
    """
    res = await api.products(admin_id, text)
    matches = [p for group in res.get("groups", []) for p in group.get("products", [])]
    if not matches:
        return {
            "error": {
                "code": "product_not_found",
                "message": f"No product matches {text!r}.",
            }
        }
    matches.sort(key=lambda p: _score(p.get("name", ""), text))
    best = dict(matches[0])
    if len(matches) > 1:
        # Named so the View can offer them and the model can ask which -- a
        # silent pick of one row out of eight is how you show the wrong product.
        best["other_matches"] = [
            {"id": p["id"], "name": p["name"]} for p in matches[1:6]
        ]
    return best


def with_admin(payload: dict[str, Any], owner_key: str) -> dict[str, Any]:
    """Attach the signed-in admin to a tool result.

    The panel renders its sign-out control from this, and a freshly re-rendered
    panel uses it to tell that the connection is still authenticated instead of
    showing the sign-in form over the top of real data.
    """
    if isinstance(payload, dict) and "error" not in payload:
        payload = {**payload, "admin": public(owner_key)}
    return payload


def build_server(settings: Settings) -> tuple[MCPServer, StockroomApi]:
    adminauth.set_ttl(settings.admin_session_ttl_seconds)
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
            "THE tool for charts, trends and 'how is the shop doing' questions — "
            "'visualise the data', 'show me some charts', 'revenue over time', "
            "'what sells best', 'how are orders trending'.\n\n"
            "Renders an interactive panel: six headline tiles plus five charts — "
            "revenue per day, orders per day, products per category, unit price "
            "distribution, and top products by revenue. Hovering any bar, point "
            "or row shows its exact figure, and 7d/14d/30d/90d buttons change "
            "the range inside the panel.\n\n"
            "`days` sets the opening range: 'this week' -> 7, 'this quarter' -> "
            "90. One call is enough — the user changes the range in the panel. "
            "Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def get_dashboard(ctx: Context, days: int = 30) -> dict[str, Any]:
        """Return dashboard figures for the last `days` days (1-365)."""
        owner_key = adminauth.owner(ctx)
        admin_id = adminauth.user_id(owner_key)
        if admin_id is None:
            return adminauth.auth_required(owner_key)
        days = max(1, min(int(days), 365))
        try:
            return with_admin(await api.stats(admin_id, days), owner_key)
        except ApiError as exc:
            # Surface a usable message rather than an empty iframe.
            return {"error": {"code": exc.code, "message": str(exc)}}

    @apps.tool(
        resource_uri=ORDERS_URI,
        name="list_orders",
        title="List orders",
        description=(
            "THE tool for any question about orders. Returns them newest first "
            "with line items, totals, unit counts and status, and renders as an "
            "interactive panel showing exactly the filters you passed.\n\n"
            "Translate the user's words into the arguments — several at once is "
            "normal:\n"
            "  'pending and cancelled orders'   -> status='pending, cancelled'\n"
            "  'orders over ¥50,000'            -> min_total=50000\n"
            "  'cheap orders under ¥5,000'      -> max_total=5000\n"
            "  'the last week'                  -> days=7\n"
            "  'in August'                      -> date_from='2026-08-01', "
            "date_to='2026-08-31'\n"
            "  'bulk orders of 20+ items'       -> min_quantity=20\n"
            "  'carol's orders' / 'order RKS-…0009' -> q='carol' / q='0009'\n\n"
            "Quantity means UNITS ordered (the sum of item quantities), not the "
            "number of distinct products. Omit anything the user did not ask "
            "for.\n\n"
            "The panel arrives with these filters already filled in, and the "
            "user can refine them there — by order number, customer, price, "
            "units, date or status — without another prompt. So call this once "
            "with what they asked for; do not re-call it to narrow further "
            "unless they ask you to. Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def list_orders(
        ctx: Context,
        q: Annotated[
            LooseText,
            Field(
                default="",
                description=(
                    "Free text matched against the order number, the customer's "
                    "name and their email. Use it for 'carol's orders' or "
                    "'order RKS-20260906-0009'."
                ),
            ),
        ] = "",
        status: Annotated[
            LooseText,
            Field(
                default="",
                description=(
                    "Comma-separated statuses to include: pending, confirmed, "
                    "cancelled. Any combination, e.g. 'pending, cancelled'. "
                    "Leave empty for all three."
                ),
            ),
        ] = "",
        days: Annotated[
            int,
            Field(default=0, description="Only orders from the last N days. 0 = no limit."),
        ] = 0,
        date_from: Annotated[
            LooseText,
            Field(default="", description="Earliest order date, YYYY-MM-DD, inclusive."),
        ] = "",
        date_to: Annotated[
            LooseText,
            Field(default="", description="Latest order date, YYYY-MM-DD, inclusive."),
        ] = "",
        min_total: Annotated[
            int, Field(default=0, description="Minimum order total in yen. 0 = no minimum.")
        ] = 0,
        max_total: Annotated[
            int, Field(default=0, description="Maximum order total in yen. 0 = no maximum.")
        ] = 0,
        min_quantity: Annotated[
            int,
            Field(default=0, description="Minimum units ordered across the whole order."),
        ] = 0,
        max_quantity: Annotated[
            int,
            Field(default=0, description="Maximum units ordered across the whole order."),
        ] = 0,
        limit: Annotated[int, Field(default=50, description="Rows to return.")] = 50,
    ) -> dict[str, Any]:
        """List orders, filtered by status, date, total and units ordered."""
        owner_key = adminauth.owner(ctx)
        admin_id = adminauth.user_id(owner_key)
        if admin_id is None:
            return adminauth.auth_required(owner_key)
        bad = [s for s in normalize_tokens(status) if s not in STATUSES]
        if bad:
            # Caught here rather than at the API so the message can name the
            # word the model actually used.
            return {
                "error": {
                    "code": "invalid_request",
                    "message": f"Unknown status {bad[0]!r}. Use pending, confirmed or cancelled.",
                }
            }
        try:
            # Filtering happens in SQL and the API echoes back what it applied,
            # so there is nothing to post-process here.
            # Only send what was actually asked for: the client no longer
            # guesses which zeros are meaningful, so each sentinel is applied
            # here, where its meaning is known.
            bounds = {
                "min_total": int(min_total),
                "max_total": int(max_total),
                "min_quantity": int(min_quantity),
                "max_quantity": int(max_quantity),
            }
            return with_admin(await api.orders(
                admin_id,
                limit=max(1, min(int(limit), 200)),
                q=str(q).strip(),
                status=",".join(normalize_tokens(status)),
                days=max(0, int(days)) or None,
                **{"from": date_from, "to": date_to},
                **{k: v for k, v in bounds.items() if v > 0},
            ), owner_key)
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
        ctx: Context,
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
        owner_key = adminauth.owner(ctx)
        admin_id = adminauth.user_id(owner_key)
        if admin_id is None:
            return adminauth.auth_required(owner_key)
        # One request. The API resolves the words to slugs, filters in SQL and
        # returns category-first groups, so there is nothing to fetch first and
        # nothing to regroup after.
        try:
            data = with_admin(await api.products(
                admin_id, q, normalize_tokens(categories), include_inactive
            ), owner_key)
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}
        return absolute_images(data, settings.public_api_base)

    @apps.tool(
        resource_uri=PRODUCT_URI,
        name="get_product",
        title="Get product",
        description=(
            "ONE product in full, as its own panel: every photo, the "
            "description, brand, and the S/M/L price ladder.\n\n"
            "Use it when the user points at a single product — 'give me this "
            "アルカリ乾電池 エボルタ 単1 4本入', 'tell me about product 34', "
            "'show me the Evolta batteries'. `product` takes the catalog id or "
            "any part of the name; pass the user's own words.\n\n"
            "NEVER call this more than once for a request. To show several "
            "products, or a category, use list_products — its result is already "
            "complete, with sizes, prices and images for every row. Calling "
            "this per product turns one request into dozens. Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def get_product(
        ctx: Context,
        product: Annotated[
            LooseText,
            Field(
                description=(
                    "The catalog id (e.g. '34') or any part of the product name "
                    "(e.g. 'エボルタ' or 'Evolta batteries')."
                ),
            ),
        ],
    ) -> dict[str, Any]:
        """Return one product, found by catalog id or by name."""
        owner_key = adminauth.owner(ctx)
        admin_id = adminauth.user_id(owner_key)
        if admin_id is None:
            return adminauth.auth_required(owner_key)
        text = str(product).strip()
        try:
            if text.isdigit():
                data = await api.product(admin_id, int(text))
            else:
                data = await _find_product(api, admin_id, text)
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}
        if "error" in data:
            return data
        return with_admin(absolute_images(data, settings.public_api_base), owner_key)

    @apps.tool(
        resource_uri=USERS_URI,
        name="list_users",
        title="List users",
        description=(
            "THE tool for any question about accounts or customers. Returns "
            "them with open cart lines, order count and lifetime spend, and "
            "renders as an interactive panel showing exactly the filters you "
            "passed.\n\n"
            "Translate the user's words into the arguments — several at once is "
            "normal:\n"
            "  'find carol' / 'who is bob@…'   -> q='carol'\n"
            "  'just the admins'               -> role='admin'\n"
            "  'customers, not admins'         -> role='customer'\n"
            "  'who has an abandoned cart'     -> has_cart=True\n"
            "  'repeat buyers' / '3+ orders'   -> min_orders=3\n"
            "  'who never ordered'             -> max_orders=0\n"
            "  'spent over ¥100,000'           -> min_spent=100000\n"
            "  'signed up in August'           -> date_from='2026-08-01', "
            "date_to='2026-08-31'\n\n"
            "Spend excludes cancelled orders. The panel arrives with these "
            "filters filled in and the user can refine them there, so call this "
            "once with what they asked for. Read-only."
        ),
        annotations=read_only(),
        structured_output=True,
    )
    async def list_users(
        ctx: Context,
        q: Annotated[
            LooseText,
            Field(default="", description="Free text matched against name and email."),
        ] = "",
        role: Annotated[
            LooseText,
            Field(default="", description="'admin', 'customer', or empty for both."),
        ] = "",
        has_cart: Annotated[
            bool,
            Field(default=False, description="Only accounts with an open cart."),
        ] = False,
        min_orders: Annotated[
            int, Field(default=0, description="Minimum orders placed. 0 = no minimum.")
        ] = 0,
        max_orders: Annotated[
            int,
            Field(
                default=-1,
                description="Maximum orders placed. Use 0 for 'never ordered'; -1 = no maximum.",
            ),
        ] = -1,
        min_spent: Annotated[
            int, Field(default=0, description="Minimum lifetime spend in yen.")
        ] = 0,
        max_spent: Annotated[
            int, Field(default=0, description="Maximum lifetime spend in yen. 0 = no maximum.")
        ] = 0,
        date_from: Annotated[
            LooseText,
            Field(default="", description="Earliest signup date, YYYY-MM-DD, inclusive."),
        ] = "",
        date_to: Annotated[
            LooseText,
            Field(default="", description="Latest signup date, YYYY-MM-DD, inclusive."),
        ] = "",
        limit: Annotated[int, Field(default=50, description="Rows to return.")] = 50,
    ) -> dict[str, Any]:
        """List user accounts, filtered by name, role, activity and spend."""
        owner_key = adminauth.owner(ctx)
        admin_id = adminauth.user_id(owner_key)
        if admin_id is None:
            return adminauth.auth_required(owner_key)
        wanted = str(role).strip().lower()
        if wanted not in ("", "admin", "customer"):
            return {
                "error": {
                    "code": "invalid_request",
                    "message": f"Unknown role {role!r}. Use 'admin' or 'customer'.",
                }
            }
        try:
            bounds = {
                "min_orders": int(min_orders),
                "min_spent": int(min_spent),
                "max_spent": int(max_spent),
            }
            return with_admin(await api.users(
                admin_id,
                limit=max(1, min(int(limit), 200)),
                q=str(q).strip(),
                role=wanted,
                has_cart="true" if has_cart else "",
                # 0 is a real filter here -- "never ordered" -- so its sentinel
                # for "no maximum" is negative, not falsy.
                **({"max_orders": int(max_orders)} if int(max_orders) >= 0 else {}),
                **{k: v for k, v in bounds.items() if v > 0},
                **{"from": date_from, "to": date_to},
            ), owner_key)
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}

    # The sign-in pair is app-only: it ships in tools/list carrying
    # _meta.ui.visibility, so a host that honours it offers these to the View
    # and never to the model. A passcode must not be something a model can be
    # talked into asking for, repeating, or putting in a transcript.
    @apps.tool(
        resource_uri=DASHBOARD_URI,
        visibility=["app"],
        name="admin_sign_in",
        title="Admin sign in",
        description=(
            "Verify an administrator email and passcode for THIS connection. "
            "Called by the sign-in form inside the panel, never by the model."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                    idempotentHint=True, openWorldHint=False),
        structured_output=True,
    )
    async def admin_sign_in(ctx: Context, email: str, passcode: str) -> dict[str, Any]:
        """Sign in as an administrator on this connection."""
        owner_key = adminauth.owner(ctx)
        address = (email or "").strip().lower()

        if not adminauth.passcode_ok(passcode or "", settings.admin_passcode):
            # One message for a bad passcode and for a non-admin address: which
            # half was wrong is not something an attacker should learn.
            log.warning("admin sign-in refused for %r", address or "(no email)")
            return {"error": {"code": "invalid_credentials",
                              "message": "That email and passcode do not match an administrator."}}
        try:
            account = await api.resolve(address)
        except ApiError as exc:
            return {"error": {"code": exc.code, "message": str(exc)}}
        if not account.get("is_admin"):
            log.warning("admin sign-in refused for %r (not an admin)", address)
            return {"error": {"code": "invalid_credentials",
                              "message": "That email and passcode do not match an administrator."}}

        return {"status": "ok", "admin": adminauth.sign_in(owner_key, account)}

    @apps.tool(
        resource_uri=DASHBOARD_URI,
        visibility=["app"],
        name="admin_sign_out",
        title="Admin sign out",
        description="End the administrator session on this connection.",
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                    idempotentHint=True, openWorldHint=False),
        structured_output=True,
    )
    async def admin_sign_out(ctx: Context) -> dict[str, Any]:
        """Forget the administrator signed in on this connection."""
        adminauth.sign_out(adminauth.owner(ctx))
        return {"status": "ok", "admin": None}

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
    if not settings.admin_passcode:
        raise SystemExit(
            "STOCKROOM_ADMIN_PASSCODE is not set. The admin tools are gated on it, "
            "and an unset passcode would mean nobody can sign in.\n"
            "Set it in .env (or the environment) and restart."
        )
    server, _api = build_server(settings)

    if args.transport == "stdio":
        # One connection per process, so the admin session can key on a
        # constant. Over HTTP it keys on the transport's session id instead.
        adminauth.set_stdio(True)
        server.run("stdio")
        return

    import uvicorn

    log.info("MCP endpoint http://%s:%s/mcp", settings.host, settings.port)
    log.info("backend %s as %s", settings.api_base, settings.admin_email)
    uvicorn.run(
        server.streamable_http_app(
            json_response=True,
            transport_security=TransportSecuritySettings(
                allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", "mcp:3001"],
                allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
            ),
        ),
        host=settings.host,
        port=settings.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
