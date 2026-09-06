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
| `list_orders` | `q?`, `status?`, `days?`, `date_from?`, `date_to?`, `min_total?`, `max_total?`, `min_quantity?`, `max_quantity?`, `limit` | `ui://stockroom/orders` | `GET /api/v1/admin/orders` |
| `list_products` | `categories?`, `q?`, `include_inactive` (default true) | `ui://stockroom/catalog` | `GET /api/v1/admin/products` |
| `get_product` | `product_id` | `ui://stockroom/product` | `GET /api/v1/products/{id}` |
| `list_users` | `q?`, `role?`, `has_cart?`, `min_orders?`, `max_orders?`, `min_spent?`, `max_spent?`, `date_from?`, `date_to?`, `limit` | `ui://stockroom/users` | `GET /api/v1/admin/users` |

**All five are built and verified.**

---

### `get_dashboard(days)`

*"How is the shop doing?"*, *"give me some charts to visualise the data"* —
the Overview tab.

Six stat tiles and **five charts**, all from one call:

| Chart | Series |
|---|---|
| Revenue per day | `orders_by_day.revenue_jpy`, filled line |
| Orders per day | `orders_by_day.orders`, bars |
| Products per category | `products_by_category`, horizontal bars |
| Unit price distribution | `price_buckets`, bars |
| Top products by revenue | `top_products`, table |

`orders_by_day` is gap-filled, so a quiet day renders as a zero rather than
vanishing and bending the trend line.

**The charts are hand-rolled inline SVG** — see
[views/src/charts.ts](../mcp-ops/views/src/charts.ts). A View is inlined into
one HTML file for the deny-by-default iframe CSP, so recharts + React would
roughly triple the bundle to draw five simple shapes; the whole chart toolkit
costs about 6 KB. Tooltips are a native `<title>` per shape: no JS, no
positioning maths, and nothing that can escape the iframe.

Returns `totals`, `products_by_category`, `orders_by_day`, `top_products`,
`price_buckets`.

### `list_orders(q?, status?, days?, date_from?, date_to?, min_total?, max_total?, min_quantity?, max_quantity?, limit)`

*"Show me recent orders"*, *"pending and cancelled orders over ¥50,000 from
last week"* — the Orders tab.

A table of every user's orders, newest first: order number, customer, units
ordered and line count, total, date, status.

Every filter is optional and they combine with AND, so one call answers a
compound question:

| The user says | Arguments |
|---|---|
| "pending and cancelled orders" | `status='pending, cancelled'` |
| "orders over ¥50,000" | `min_total=50000` |
| "cheap orders under ¥5,000" | `max_total=5000` |
| "the last week" | `days=7` |
| "in August" | `date_from='2026-08-01'`, `date_to='2026-08-31'` |
| "bulk orders of 20+ items" | `min_quantity=20` |
| "carol's orders" | `q='carol'` |
| "order RKS-20260906-0009" | `q='0009'` |

**Quantity means units**, the sum of item quantities — not the number of
distinct lines. An order of two products can easily be twenty things. Both
numbers ride in every row (`total_quantity` and `item_count`) so the figure the
filter used is visible beside the row it kept.

`status` is a plain comma-separated string for the same reason `categories` is:
a union schema makes models omit the argument entirely. An unknown status is a
clean error naming the word the model used, not an empty table.

Line items ride along in the payload, so the model can answer "what was in
order RKS-…" without another call.

The response echoes an **`applied`** block — the filter as the server
understood it — and the View renders its controls from that rather than from
what it believes it sent. That is what makes the panel arrive **pre-filled**:
the prompt's filters and a typed one land in exactly the same place, so the bar
always agrees with the rows beneath it.

From there the panel is self-sufficient. Order number, customer, price, units,
date (native pickers) and status can all be refined inside it, each going
straight back to this tool without the model. So one call per question is
enough — narrowing is the user's job, not a second tool call's.

The bar is built once and only its *values* update, because re-rendering it on
each result would take the caret away mid-keystroke.

### `list_products(categories?, q?, include_inactive)`

*"What do we sell?"*, *"find paper products"*, *"show me files and drinks"* —
the Catalog tab.

Products grouped by category: id, name, base price, and the S/M/L ladder with
computed unit prices. Includes deactivated products by default — that is the
point of an admin view.

`categories` takes the user's own words, not slugs — `files`, `copy paper`,
`ファイル` all resolve, in the Go service. Two things make this one HTTP call
rather than three:

- **The API resolves the words**, so the tool does not fetch the category list
  first to translate them.
- **The API returns category-first groups**, so the tool does not regroup, and
  the panel does not follow up with `get_product` per row.

The response carries only the categories that were asked for. Listing the
others would mean fetching them, and asking for two categories should cost one
request for two categories.

`categories` is typed as a **plain string**, deliberately. A union schema
(`anyOf` array/string/null) makes models omit the argument entirely — which
presents exactly as "the category filter is broken". A `BeforeValidator` still
accepts a list, because some hosts send one.

### `get_product(product_id)`

One product in full: description, brand, all three sizes with unit prices, and
its images. No equivalent tab in the frontend.

**Declared `visibility=["app"]`** — it ships in `tools/list` carrying
`_meta.ui.visibility`, and a host that honours it offers the tool to Views but
not to the model. Left visible, the model fanned out one call per product to
"work around" `list_products` instead of filtering, turning one request into
dozens. Sharpening the tool descriptions did not stop it; taking it out of the
model's view did. Descriptions are suggestions; visibility is declared and
host-enforced.

### `list_users(q?, role?, has_cart?, min_orders?, max_orders?, min_spent?, max_spent?, date_from?, date_to?, limit)`

*"Who has been ordering?"*, *"which customers never bought anything?"* — the
Users tab.

Id, name, email, admin flag, open cart lines, order count, lifetime spend and
signup date. Same filter-and-panel contract as `list_orders`:

| The user says | Arguments |
|---|---|
| "find carol" / "who is bob@…" | `q='carol'` |
| "just the admins" | `role='admin'` |
| "customers, not admins" | `role='customer'` |
| "who has an abandoned cart" | `has_cart=True` |
| "repeat buyers" / "3+ orders" | `min_orders=3` |
| "who never ordered" | `max_orders=0` |
| "spent over ¥100,000" | `min_spent=100000` |
| "signed up in August" | `date_from='2026-08-01'`, `date_to='2026-08-31'` |

Spend excludes cancelled orders, and the numeric bounds read the same derived
figures the rows display — filtering on a number the table does not show would
be untraceable.

**`max_orders=0` is a real filter**, not "unset". That is why its "no maximum"
sentinel is `-1` rather than `0`, and why the API client drops only `None` and
`""`: a falsy check silently discarded "customers who never ordered", which
looked exactly like the filter being ignored.

> Emails are visible here. They are seeded demo accounts, but the tool result
> enters the model's context — worth knowing before pointing this at a host
> with real user data.

---

## Shared conventions

**One View per tool.** A tool without its own `ui://` resource renders as text.

**Views receive the tool result directly** via `app.ontoolresult` — no second
fetch. Filters inside a View (a status dropdown, a search box) call
`app.callServerTool()` and re-render without involving the model.

**One tool call is one backend call.** The Go API returns data already shaped
for the View — resolved, grouped, sorted, with unit prices computed and image
URLs built — so no tool fetches a lookup table first or post-processes after.
Anything the panel can derive from the payload it already has (expanding a row,
revealing a description) never touches the server at all.

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
