# Prompt: Generate the RAKSUL Stockroom MCP System Design

Generate a Markdown system-design document with valid GitHub-compatible Mermaid diagrams for the system below. Do not invent components or claim that checkout is real.

## Current architecture

- AI hosts connect only to the Python MCP server in `/Users/quan0207/Practice/printing service`.
- The MCP server exposes tools plus the embedded resource `ui://widget/raksul-stockroom-v2.html`.
- The MCP server contains no storefront SQL and never contacts a supplier website.
- It calls the loopback Go API at `http://127.0.0.1:8080`.
- The Go API and schema are owned by `go-backend/` in this repository.
- The Go API is the sole owner of catalog queries, pricing, user carts, transactional order writes, and MinIO image proxying.
- PostgreSQL database `stockroom` contains `users`, `categories`, `products`, `product_images`, `product_sizes`, `cart_items`, `orders`, and `order_items`.
- MinIO stores private image objects; the Go API serves them through `/media/{key}`.

## MCP flow

- `mock_sign_in` calls `POST /api/v1/login`; the selected backend user is kept per MCP connection and injected as `X-Stockroom-User` on later backend calls.
- `search_products`, `get_product`, and `list_categories` read the Stockroom catalog.
- `get_quote` uses the backend-calculated size price and quantity subtotal.
- `get_cart`, `add_to_cart`, and `remove_cart_item` operate on the selected user's persisted cart.
- `prepare_order` snapshots the cart and shipping address into a 15-minute in-memory confirmation challenge.
- `place_order` requires the challenge plus an explicit `approve` or `reject` decision.
- Approval checks that the cart did not change, then calls `POST /api/v1/orders`; the Go transaction snapshots order lines and clears the cart.
- Rejection creates no order and preserves the cart.
- `get_order` reads a persisted order by order number for the selected user.
- No tool opens RAKSUL or another supplier website. No real payment occurs.

## Required diagrams

1. `flowchart LR` container architecture.
2. `erDiagram` for the Stockroom PostgreSQL schema.
3. `sequenceDiagram` for host → MCP → Go API → PostgreSQL/MinIO product browsing.
4. `sequenceDiagram` for demo login, quote, and cart mutation.
5. `sequenceDiagram` for prepare, explicit approval, transactional order, and receipt.
6. `sequenceDiagram` for rejection and preserved cart.
7. `stateDiagram-v2` for confirmation and order states.
8. `flowchart TD` for backend unavailable, empty cart, expired challenge, changed cart, approval, and rejection branches.

Include scope, responsibilities, API boundaries, trust boundaries, failure behavior, local deployment, test strategy, and limitations. Explicitly state that the supplier crawler is offline ingestion, the storefront runtime reads only the Stockroom backend, identity is mock selection rather than authentication, and payment is simulated.

If the request includes `MERMAID_ONLY`, return only titled Mermaid code blocks.
