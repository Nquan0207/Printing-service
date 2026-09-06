# MCP ops — tool and View declaration

The read-only surface `mcp-ops` exposes, mirroring the four admin tabs in
[frontend-ops](../frontend-ops). Declared here before implementation so the tool
names and `ui://` URIs are fixed up front — renaming them later breaks any host
that has already seen them.

Every tool is **read-only** (`readOnlyHint: true`). Product text is crawled from
a live website, so it is attacker-influenceable; a write tool would let a prompt
injection cancel an order or change a price. The write endpoints exist on the Go
API and are deliberately not exposed here.

## The five tools

| Tool | Arguments | View | Backed by |
|---|---|---|---|
| `get_dashboard` | `days` (1–365, default 30) | `ui://stockroom/dashboard` | `GET /api/v1/admin/stats` |
| `list_orders` | `status?`, `limit` (default 50) | `ui://stockroom/orders` | `GET /api/v1/admin/orders` |
| `list_products` | `q?`, `category?`, `include_inactive` (default true) | `ui://stockroom/catalog` | `GET /api/v1/admin/products` |
| `get_product` | `product_id` | `ui://stockroom/product` | `GET /api/v1/products/{id}` |
| `list_users` | `limit` (default 50) | `ui://stockroom/users` | `GET /api/v1/admin/users` |

**All five are built and verified.**

---

### `get_dashboard(days)`

*"How is the shop doing?"* — the Overview tab.

Six stat tiles plus the series behind them: products per category, orders and
revenue per day (gap-filled, so quiet days render as zero), top products by
revenue, and a unit-price distribution.

Returns `totals`, `products_by_category`, `orders_by_day`, `top_products`,
`price_buckets`.

### `list_orders(status?, limit)`

*"Show me recent orders"*, *"any cancelled orders?"* — the Orders tab.

A table of every user's orders, newest first: order number, customer name and
email, item count, total, date, status. `status` filters to
`pending` / `confirmed` / `cancelled`.

Line items ride along in the payload, so the model can answer "what was in
order RKS-…" without another call.

### `list_products(q?, category?, include_inactive)`

*"What do we sell?"*, *"find paper products"* — the Catalog tab.

Product id, name, category, base price, and the S/M/L ladder with computed unit
prices. Includes deactivated products by default — that is the point of an
admin view — with `is_active` shown per row.

### `get_product(product_id)`

One product in full: description, brand, all three sizes with unit prices, and
its images. This has no equivalent tab in the frontend; it exists because a
model asked *"tell me about product 34"* should not have to dump the whole
catalog.

### `list_users(limit)`

*"Who has been ordering?"* — the Users tab.

Id, name, email, admin flag, open cart lines, order count, lifetime spend.

> Emails are visible here. They are seeded demo accounts, but the tool result
> enters the model's context — worth knowing before pointing this at a host
> with real user data.

---

## Shared conventions

**One View per tool.** A tool without its own `ui://` resource renders as text.

**Views receive the tool result directly** via `app.ontoolresult` — no second
fetch. Filters inside a View (a status dropdown, a search box) call
`app.callServerTool()` and re-render without involving the model.

**Money is an integer of yen**, formatted in the View. Sizes are ordered by
`price_adjustment_jpy`, never alphabetically — that would give L, M, S.

**Errors render, never blank.** Every tool catches `ApiError` and returns
`{"error": {"code", "message"}}`; each View shows it. A blank iframe is the
worst failure mode because it looks like a host bug.

**Identity is fixed at the server.** All calls go out as the admin resolved at
startup; no tool takes a user id. See
[docs/flow.md](flow.md#3-python-calls-the-go-api--as-an-admin).

## Images and CSP

Views run in a sandboxed iframe under a **deny-by-default CSP**, and product
photos live at a different origin than the iframe. Two things make them load:

**1. The catalog and product resources declare a CSP allowance:**

```python
image_csp = ResourceCsp(resource_domains=[settings.public_api_base])
apps.add_html_resource(CATALOG_URI, ..., csp=image_csp)
```

Only those two Views get it; the dashboard, orders and users Views have no
images and no allowance.

**2. Image paths are rewritten to absolute URLs** by `absolute_images()` in
[server.py](../mcp-ops/stockroom_ops/server.py). The API returns `/media/<key>`,
which inside an iframe would resolve against the *iframe's* origin and 404.

This is why `STOCKROOM_PUBLIC_API_BASE` exists separately from
`STOCKROOM_API_BASE`:

| Setting | Value in Docker | Used by |
|---|---|---|
| `STOCKROOM_API_BASE` | `http://api:8080` | the MCP server, over the Docker network |
| `STOCKROOM_PUBLIC_API_BASE` | `http://127.0.0.1:8080` | the **host browser**, for image URLs and the CSP domain |

They must name the same service by different routes. If the host browser ever
runs somewhere that cannot reach `127.0.0.1:8080`, images break — the CSP
hard-codes a localhost origin, which is the accepted cost of this approach.
