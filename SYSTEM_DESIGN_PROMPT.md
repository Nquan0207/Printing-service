# Prompt: Generate the Current RAKSUL Storefront System Design

Copy this entire prompt into ChatGPT, or upload this file and say:

> Follow the instructions in `SYSTEM_DESIGN_PROMPT.md` and generate the system design.

---

You are a senior software architect. Generate an accurate system-design document
for the application described below. Do not invent components, external services,
or production guarantees that are not listed.

## Output mode

By default, return a complete Markdown document containing explanatory text,
tables where helpful, and Mermaid diagrams.

If I add `MERMAID_ONLY` to my request, return only valid Mermaid code blocks,
with a short title immediately before each block. Do not include prose analysis.

All Mermaid diagrams must:

- use Mermaid syntax supported by GitHub and ChatGPT;
- avoid custom themes, icons, HTML labels, and experimental syntax;
- use simple alphanumeric node IDs and quoted human-readable labels;
- show trust boundaries and snapshot/non-real-time behavior where relevant;
- distinguish read-only catalog operations from state-changing cart operations.

## Application

The project is a local mock RAKSUL Apparel storefront implemented in Python.
It crawls a limited set of public product pages, normalizes product data, stores
it in PostgreSQL, exposes it through an MCP server, and provides a self-contained
MCP Apps storefront widget inside ChatGPT.

This is a demonstration application. It has no authentication, user accounts,
real inventory reservation, shipping calculation, tax calculation, payment
gateway, or real money movement.

## Main components

1. **RAKSUL Apparel website**
   - External source of public product and category pages.
   - Product data is treated as incomplete, cached, and non-real-time.

2. **Crawler and parser**
   - `app/crawler/discovery.py` discovers product URLs from configured categories.
   - `app/crawler/client.py` handles HTTP requests, robots.txt, throttling, and
     limited retries.
   - `app/crawler/parser.py` and `app/crawler/product.py` normalize category and
     product-page data.
   - `app/crawler/runner.py` coordinates discovery and product ingestion.

3. **PostgreSQL database**
   - Source of truth for the local application.
   - Catalog tables: `industries`, `categories`, `products`, and
     `product_price_history`.
   - Storefront tables: `carts`, `cart_items`, `mock_orders`, `mock_customers`,
     `mock_sessions`, `mock_session_carts`, and `mock_checkout_confirmations`.
   - Product colors and sizes are stored as JSONB snapshots.
   - Cart items snapshot the product name, unit price, selected color and size,
     and quantity when added.
   - A mock order snapshots the complete cart and the server-calculated total.

4. **Repository layer**
   - `app/repositories/product_repository.py` owns catalog queries and upserts.
   - `app/repositories/shopping_repository.py` owns cart, cart-item, checkout,
     and mock-order persistence.

5. **Service layer**
   - `app/services/product_service.py` provides catalog search and details
     without exposing raw SQL.
   - `app/services/shopping_service.py` validates products, options, prices,
     quantities, cart state, checkout state, and payment decisions.
   - Totals are always recalculated on the server. Widget-supplied totals are
     never trusted.

6. **MCP server**
   - `app/mcp_server/server.py` runs over stdio by default and can run over
     Streamable HTTP.
   - `app/mcp_server/tools.py` maps MCP requests to the repository/service layer
     and returns structured, model-readable results.
   - `app/mcp_server/storefront_widget.py` contains the embedded storefront as
     one self-contained vanilla HTML/CSS/JavaScript document.

7. **ChatGPT and MCP Apps widget**
   - ChatGPT discovers and invokes the MCP tools.
   - `open_storefront` is the only render tool and links to
     `ui://widget/raksul-storefront.html` through `_meta.ui.resourceUri`.
   - The widget invokes MCP tools through the standard `ui/*` JSON-RPC bridge
     and feature-detects compatible ChatGPT APIs.
   - The UI contains product search, product details, image and snapshot-price
     warnings, color/size/quantity controls, a cart drawer, cart totals, and
     loading/empty/error states.

8. **Plugin packaging**
   - `plugins/raksul-catalog/.codex-plugin/plugin.json` defines plugin metadata,
     capabilities, and starter prompts.
   - `plugins/raksul-catalog/.mcp.json` defines the local MCP server process.
   - `.agents/plugins/marketplace.json` exposes the plugin through the local
     `raksul-printing` marketplace.

## MCP tools

Read-only catalog/render operations:

- `search_products`
- `get_product`
- `list_categories`
- `get_catalog_info`
- `open_storefront`
- `get_cart`
- `get_mock_session`
- `get_mock_order`

State-changing operations:

- `create_cart`
- `mock_sign_in`
- `add_cart_item`
- `update_cart_item`
- `remove_cart_item`
- `create_mock_checkout`
- `decide_mock_payment`

Every tool returns structured data so a client without widget support can still
inspect the application state.

## Business rules and state transitions

- Cart IDs and order IDs are generated UUIDs.
- A local mock sign-in creates a 24-hour session using name and email without a password.
- New carts and orders are accessible only through their owning session.
- A cart starts as `active` and becomes `checked_out` only after approval.
- A cart accepts only existing products with a valid snapshot price.
- Quantity must be positive and within the server's configured limit.
- Selected colors and sizes must exist in the product snapshot.
- An empty cart cannot be checked out.
- Checkout creates a `pending` mock order and a 15-minute confirmation challenge.
- `approved` and `rejected` are final order states.
- Approving a pending order closes its cart.
- Rejecting a pending order leaves the cart active so checkout can be retried.
- Repeating the same final decision is idempotent.
- Attempting the opposite decision after finalization returns a conflict.
- The UI must explicitly label the operation as simulated, provide separate
  **Approve mock payment** and **Reject mock payment** actions, and never request
  card or bank details.

## Required document structure

Generate the following sections:

1. **System purpose and scope**
2. **Architecture overview**
3. **Component responsibilities**
4. **Data model**
5. **Catalog ingestion flow**
6. **Storefront search and rendering flow**
7. **Cart mutation flow**
8. **Mock checkout approval flow**
9. **Mock checkout rejection and retry flow**
10. **State transitions and invariants**
11. **Failure handling**
12. **Security and trust boundaries**
13. **Known limitations**
14. **Local deployment and plugin-loading topology**

Include at least these Mermaid diagrams:

1. A `flowchart LR` architecture/container diagram.
2. An `erDiagram` covering catalog, cart, cart-item, and mock-order relationships.
3. A `sequenceDiagram` for opening the widget, searching, and viewing products.
4. A `sequenceDiagram` for cart creation and item mutations.
5. A `sequenceDiagram` for checkout and approval.
6. A `sequenceDiagram` for rejection followed by retry.
7. A `stateDiagram-v2` for cart and mock-order states.
8. A `flowchart TD` failure/validation decision flow.

For sequence diagrams, use these participants when applicable:

- User
- ChatGPT
- Storefront Widget
- MCP Server
- Shopping Service or Product Service
- Repository
- PostgreSQL
- RAKSUL Website, only in the offline crawler flow

End the document with a concise list of assumptions and explicitly state that
the payment workflow is a mock confirmation flow, not OpenAI Instant Checkout
and not a real payment integration.
