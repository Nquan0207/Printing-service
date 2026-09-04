# Go service ⇄ MCP server contract

The frozen interface between the two processes. requirement.md calls for this
on Day 0 and warns against changing names mid-week — that warning applies
doubly here, because we split what it specified as one process into two.

- **Go service** owns SQL, MinIO, pricing arithmetic, and order writes.
- **MCP server** owns tool definitions, `ui://` Views, and the confirm-gate on
  `place_order`. It holds no SQL and never reaches MinIO directly.

Base URL `http://127.0.0.1:8080`, loopback only. JSON in, JSON out, UTF-8.

## How this contract was derived

Six rules; every shape below follows from them.

1. **Model the tool surface, not the tables.** There are five MCP tools, so
   there are five workflows. `product_sizes` never appears as its own endpoint
   — it is always nested inside a product, because no tool asks for a size on
   its own.
2. **The server returns display-ready values.** `unit_price_jpy` is computed
   (`base_price + price_adjustment`) and image paths arrive as `/media/...`.
   A View must never do arithmetic or build a URL — that is how MinIO keys leak
   into an iframe that cannot fetch them.
3. **Money is an integer of yen.** No floats, no currency math. The crawler
   already rounded fractional source prices up.
4. **One error envelope, always.** A caller writes one error path, not nine.
5. **Version the prefix (`/api/v1`).** Renaming later costs a deploy of two
   processes; adding `/v2` costs nothing.
6. **State who enforces what.** Ambiguity here is how "no silent checkout"
   quietly stops being true.

## Conventions

| Concern | Rule |
|---|---|
| Money | Integer JPY. `unit_price_jpy = base_price_jpy + price_adjustment_jpy`. |
| Ordering | Sizes by `price_adjustment_jpy` ascending (**never alphabetically** — that yields L, M, S). Images by `id`. |
| Identity | No `user_id` in any request body or query. The MCP server resolves `UserContext` and passes it as `X-Stockroom-User`. See [Identity propagation](#identity-propagation). |
| Unknown query params | Ignored, not an error. |
| Timestamps | RFC 3339 UTC. |

## Identity propagation

### The rule: identity never travels in tool arguments

No tool takes a `user_id`, and no endpoint accepts one. This is a security
boundary, not a convenience:

- **Tool arguments are model-controlled.** The LLM fills them in. A prompt
  injection — from a product description, a page the model read, a pasted
  message — can make it pass any id it likes. A `user_id` parameter is an
  invitation to act as someone else.
- **Views are untrusted too.** A `ui://` View is sandboxed HTML calling
  `app.callServerTool()`. Whatever it sends is attacker-reachable if the page
  is ever compromised.

Identity must come from the **transport**, which the model cannot influence.

### The chain

```
Host
  |  Custom chat  -> user picked in the UI (Alice / Bob / Charlie)
  |  Claude,ChatGPT -> no identity at all; assume Alice
  v
MCP server            <-- the ONLY place identity is decided
  |  resolves UserContext { userId }
  |  X-Stockroom-User: 1
  |  (later: Authorization: Bearer <token>)
  v
Go service            <-- one resolver turns that into a user_id
  |  WHERE user_id = $1
  v
Postgres
```

The MCP server owns a `UserContext { userId }` and injects it into every
business operation. That resolution is the abstract seam: swapping it for
OAuth-derived identity later changes only how `UserContext` is produced, not a
single tool, endpoint, or query.

| Hop | Identity available | PoC behaviour |
|---|---|---|
| Custom chat → MCP | The `userId` the person selected, on the session. | Three seeded users; the selector sets it. |
| Claude / ChatGPT → MCP | **None** — there is no OAuth in the PoC. | Defaults to Alice. |
| View → MCP | The session it was rendered in; sends **no** identity. | `app.callServerTool()` carries tool args only. |
| MCP → Go | `X-Stockroom-User`, set by the MCP server. | Go trusts it (see below). |
| Go → DB | `user_id` from its resolver. | `WHERE user_id = $1` on cart and orders. |

### The trust boundary

The Go service **trusts `X-Stockroom-User` without verification**. That is only
safe because of two properties that must hold together:

1. It binds `127.0.0.1` and is never exposed to a host, a View, or the network.
2. The MCP server is its sole client.

If either stops being true, the header becomes a free impersonation switch —
anyone who can reach the port picks whoever they like. A View must never call
the Go service directly, and the port must never be published, tunnelled, or
forwarded. When real auth arrives, this header is replaced by a verified token
rather than merely supplemented.

### Seeded users

| id | Name | Email | Used by |
|---|---|---|---|
| 1 | Alice | `alice@stockroom.local` | Default for Claude / ChatGPT, and the selector |
| 2 | Bob | `bob@stockroom.local` | Selector only |
| 3 | Charlie | `charlie@stockroom.local` | Selector only |

Carts and orders are per-user, so switching the selector switches carts — which
is the point of seeding three rather than one.

### User *info* is not identity

`place_order` takes `shipping_address` in the **request body**, from the
confirm View's form — it is not read off the user record. Address, name, and
contact details are order data the person typed, so they stay decoupled from
whoever the caller is. Adding real auth later does not change where the
shipping address comes from.

### Error envelope

Every non-2xx response:

```json
{ "error": { "code": "product_not_found", "message": "Product 999 does not exist." } }
```

| Code | HTTP | When |
|---|---|---|
| `invalid_request` | 400 | Malformed body, bad type, `quantity < 1`. |
| `product_not_found` | 404 | Unknown product id. |
| `size_not_found` | 404 | Size id absent, or not a size of that product. |
| `cart_empty` | 409 | `POST /orders` with nothing in the cart. |
| `order_not_found` | 404 | Unknown order number. |
| `internal` | 500 | Anything else; details logged, not returned. |

## Tool → endpoint map

| MCP tool | Endpoint |
|---|---|
| `search_products` | `GET /api/v1/products` |
| — (View detail) | `GET /api/v1/products/{id}` |
| — (filters) | `GET /api/v1/categories` |
| `get_quote` | `POST /api/v1/quote` |
| `add_to_cart` | `POST /api/v1/cart/items` (+ `GET`/`PATCH`/`DELETE`) |
| `place_order` | `POST /api/v1/orders` |
| `get_order` | `GET /api/v1/orders/{order_number}` |
| image bytes | `GET /media/{key}` |

---

## Shared object: Product

Returned by search (without `description`) and by detail (with it).

```json
{
  "id": 12,
  "source_product_id": "158",
  "name": "手提げ紙袋",
  "brand": "ラクスル",
  "description": "…",
  "category": { "id": 3, "slug": "store_supplies", "name": "店舗用品" },
  "base_price_jpy": 168,
  "sizes": [
    { "id": 34, "size_name": "S", "price_adjustment_jpy": 0,  "unit_price_jpy": 168 },
    { "id": 35, "size_name": "M", "price_adjustment_jpy": 18, "unit_price_jpy": 186 },
    { "id": 36, "size_name": "L", "price_adjustment_jpy": 30, "unit_price_jpy": 198 }
  ],
  "images": ["/media/products/158/ab12….jpg"]
}
```

`images` are **paths, not URLs** — same origin as the API, safe inside the
iframe sandbox. An empty array is normal; render a placeholder.

## `GET /api/v1/products`

Query: `q`, `category` (slug), `min_price`, `max_price`, `limit` (default 20,
max 100), `offset`.

`q` matches name and description, case-insensitive. Filters combine with AND.

```json
{
  "products": [ { "…Product without description…" } ],
  "total": 57,
  "limit": 20,
  "offset": 0
}
```

`total` is the count before pagination, so a View can say "57 results".
An empty list is `200` with `"products": []` — **not** a 404. The MCP tool is
responsible for saying "nothing in this snapshot" rather than "does not exist".

## `GET /api/v1/categories`

```json
{ "categories": [
    { "id": 3, "slug": "store_supplies", "name": "店舗用品", "product_count": 9 }
] }
```

Only categories that actually hold products, so filter chips never render a
dead option.

## `POST /api/v1/quote`

```json
{ "product_id": 12, "size_id": 34, "quantity": 500 }
```

```json
{
  "product_id": 12, "product_name": "手提げ紙袋",
  "size_id": 34, "size_name": "S",
  "quantity": 500,
  "unit_price_jpy": 168,
  "subtotal_jpy": 84000,
  "currency": "JPY",
  "notes": ["Mock pricing: no tax, shipping, or quantity discounts."]
}
```

`subtotal = unit_price × quantity`. The source site prices in quantity tiers,
but the schema stores one price per size, so **there is no volume discount** —
`notes` says so out loud, and the MCP tool should surface it rather than let a
model imply a real quote.

## Cart

Server-side and persisted in `cart_items` (requirement.md suggested in-memory;
the schema won). Scoped to the demo user.

```
GET    /api/v1/cart                 → Cart
POST   /api/v1/cart/items           { product_id, size_id, quantity } → Cart
PATCH  /api/v1/cart/items/{item_id} { quantity }                     → Cart
DELETE /api/v1/cart/items/{item_id}                                  → Cart
```

Every mutation returns the **whole cart**, so a View re-renders from one
response and never recomputes a total.

```json
{
  "items": [
    { "id": 7, "product_id": 12, "product_name": "手提げ紙袋",
      "size_id": 34, "size_name": "S",
      "image": "/media/products/158/ab12….jpg",
      "quantity": 500, "unit_price_jpy": 168, "subtotal_jpy": 84000 }
  ],
  "item_count": 1,
  "total_jpy": 84000
}
```

`POST` **adds to** an existing line's quantity (`UNIQUE(user_id, product_id,
product_size_id)` makes this an upsert); `PATCH` sets it absolutely.
`PATCH` with `quantity: 0` deletes the line.

## `POST /api/v1/orders`

```json
{ "shipping_address": "東京都…", "idempotency_key": "uuid-optional" }
```

Converts the cart to an order in one transaction: inserts `orders`, snapshots
each line into `order_items` (copying `product_name`, `size_name`, and
`unit_price_jpy` so later catalog edits cannot rewrite history), clears the
cart, returns `201`.

```json
{
  "order_number": "RKS-20260904-0001",
  "status": "confirmed",
  "shipping_address": "東京都…",
  "total_jpy": 84000,
  "items": [ { "product_name": "手提げ紙袋", "size_name": "S",
               "quantity": 500, "unit_price_jpy": 168, "subtotal_jpy": 84000 } ],
  "created_at": "2026-09-04T14:22:31Z"
}
```

Repeating a request with the same `idempotency_key` returns the original order
instead of creating a second one — a retry after a dropped response must not
double-order.

> **Enforcement lives in the MCP server.** requirement.md requires
> `place_order` to be reachable only from the confirm View. This endpoint
> cannot see which View called it, so the MCP server must gate the tool. The Go
> service is loopback-only and never exposed directly to a host.

## `GET /api/v1/orders/{order_number}`

Same object as above. `404 order_not_found` if unknown.

## `GET /media/{key}`

`key` is the full `product_images.image_key`, slashes included:
`/media/products/158/ab12….jpg`. Streams `GetObject` from MinIO with its
`Content-Type` and a long `Cache-Control`. `404` for an unknown key.

Read-only, no listing endpoint, and the bucket stays private — this proxy is
the only reader.

## Health

`GET /healthz` → `{"status":"ok","database":"ok","minio":"ok"}`, `503` if a
dependency is down.

## Changing this contract

Renaming a field or endpoint breaks the other process silently. Add fields
freely — both sides ignore unknown ones. To remove or rename, bump to
`/api/v2` and keep `v1` until the MCP server has moved.
