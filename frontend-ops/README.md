# Frontend

React + Vite SPA for the stockroom PoC: a customer **shop** and an admin
**dashboard**, both talking to [backend-ops](../backend-ops) over its JSON API.

## Run

### In Docker (the whole stack)

```bash
docker compose up -d --build      # from the repo root
open http://127.0.0.1:3000
```

nginx serves the built SPA and reverse-proxies `/api` and `/media` to the `api`
service, so the browser sees one origin. `try_files ... /index.html` makes the
client-side routes (`/shop`, `/admin`, `/orders`) work on a hard refresh or a
pasted link, which a plain static server would 404.

### Dev server (hot reload)

The API must be up (`docker compose up -d postgres minio api`).

```bash
cd frontend-ops
npm install
npm run dev          # http://127.0.0.1:5173
```

Vite proxies the same two paths to `http://127.0.0.1:8080`, so behaviour
matches the container.

```bash
npm run build        # typecheck + bundle to dist/
```

### Browser check

`render-check.mjs` drives the real app in headless Chrome — sign-in, product
detail gallery, admin size editing — and fails loudly on console errors:

```bash
node render-check.mjs                          # against the dev server
BASE=http://127.0.0.1:3000 node render-check.mjs   # against the container
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
flipped with an env var and a restart of the API alone — the frontend image is
never rebuilt:

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
