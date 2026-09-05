# Frontend

React + Vite SPA for the stockroom PoC: a customer **shop** and an admin
**dashboard**, both talking to [backend-ops](../backend-ops) over its JSON API.

## Run

The API must be up first (`docker compose up -d` from the repo root).

```bash
cd frontend-ops
npm install
npm run dev          # http://127.0.0.1:5173
```

Vite proxies `/api` and `/media` to `http://127.0.0.1:8080`, so the browser
sees a single origin: no CORS, and the `/media/...` image paths the API returns
resolve unchanged.

```bash
npm run build        # typecheck + bundle to dist/
npm run preview
```

## Pages

| Route | Who | What |
|---|---|---|
| `/` | customer | Shop: search, category and max-price filters, S/M/L picker, cart drawer, checkout |
| `/orders` | customer | Look up one of your own orders by number |
| `/admin` | admin only | Dashboard: charts, orders, catalog editing, users |

Sign-in is an **email box, not authentication** — `POST /api/v1/login` resolves
an address to a user id, creating the user when new. That id is kept in
`localStorage` and sent as `X-Stockroom-User` on every request.

Seeded accounts: `alice@stockroom.local` (customer),
`admin@stockroom.local` (admin). Any other address creates a new customer.

## The shop toggle

`SHOP_ENABLED` lives **server-side**, not in the frontend build, so it can be
flipped with an env var and a restart rather than a rebuild:

```bash
SHOP_ENABLED=false docker compose up -d api     # from the repo root
```

The SPA reads `GET /api/v1/config` on boot and, when the shop is off, renders
**Page not found** for `/` and `/orders`. A signed-in admin still reaches
`/admin`, and the API keeps serving every route — the toggle governs the
customer UI only, not the backend.

The login screen warns about this when the shop is disabled, so nobody signs in
and wonders why they got a 404.

## Dashboard

Four charts (recharts), all fed by `GET /api/v1/admin/stats`:

- **Revenue per day** and **orders per day** — the series has every date filled
  in server-side, so a quiet day renders as zero rather than being skipped
- **Products per category** — horizontal bars
- **Unit price distribution** — sizes bucketed by price

Plus tabs for orders (with status changes), catalog editing (rename, reprice,
deactivate), and users.

> Catalog edits are **overwritten by the next crawl**, which upserts on
> `source_product_id`. `is_active` survives — the crawler never sets it.

Admin routes are gated by `is_admin` on the user row, granted at startup from
`STOCKROOM_ADMIN_EMAILS`. A non-admin calling them gets `403 forbidden`, and
the dashboard link is hidden.

## UI

Built on **Mantine 9.6** — one library covering both surfaces, so there is no
second design system for the dashboard. `@mantine/charts` wraps the same
recharts the project already depends on, and `theme.ts` defines RAKSUL red as
the primary colour. Light/dark is a header toggle; Mantine handles the rest.

```
src/
  theme.ts          brand palette + component defaults
  lib/api.ts        typed client; one place unwraps the error envelope
  lib/session.ts    login + localStorage, sets X-Stockroom-User
  pages/            Login, Shop, Orders, Admin, NotFound
  styles.css        only what Mantine does not cover (product-image blending)
  postcss.config.cjs  postcss-preset-mantine (required by Mantine)
```

The dashboard route is **lazy-loaded**, so the ~132 KB of chart code never
reaches a shopper:

| Bundle | gzipped | loaded by |
|---|---|---|
| `index` | 173 KB | everyone |
| `Admin` | 132 KB | admins only |
