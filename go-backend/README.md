# Go backend

Reads the crawled stockroom catalog from Postgres, proxies product images from
MinIO, and serves the JSON API that the MCP server calls.

- Contract: [docs/api-contract.md](../docs/api-contract.md) — frozen; read it first.
- Schema: [schema.sql](schema.sql) — hand-written DDL, the single source of truth.
- Catalog data: written by [crawler/](../crawler/), not by this service.

Binds `127.0.0.1:8080` only. The MCP server runs on the same machine.

## Identity: the seeded demo users

Authentication is deferred, but the schema requires a user regardless:

```sql
cart_items.user_id BIGINT NOT NULL REFERENCES users(id)
orders.user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT
```

So a cart line or an order **cannot** be written without a `users` row. The
crawler deliberately never touches that table.

The PoC seeds **three demo users** on startup — the custom chat offers them in
a selector, while external hosts (Claude, ChatGPT) always resolve to Alice:

```go
// internal/auth/demo.go
var demoUsers = []struct{ Name, Email string }{
    {"Alice", "alice@stockroom.local"},   // default for external hosts
    {"Bob", "bob@stockroom.local"},
    {"Charlie", "charlie@stockroom.local"},
}

// EnsureDemoUsers creates the PoC users once and returns email -> id.
func EnsureDemoUsers(ctx context.Context, db *pgxpool.Pool) (map[string]int64, error) {
    ids := make(map[string]int64, len(demoUsers))
    for _, u := range demoUsers {
        var id int64
        err := db.QueryRow(ctx, `
            INSERT INTO users (name, email, password_hash, address)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (email) DO UPDATE SET updated_at = NOW()
            RETURNING id`,
            u.Name, u.Email, "!unusable-poc-account!", "東京都…",
        ).Scan(&id)
        if err != nil {
            return nil, err
        }
        ids[u.Email] = id
    }
    return ids, nil
}
```

`password_hash` holds a deliberately unusable sentinel, not a real hash — no
login path exists, so nothing can authenticate as these accounts.

Seeding three rather than one is what makes carts visibly per-user: switching
the selector switches carts, because every query filters on `user_id`.

**No endpoint accepts a `user_id`**, and no MCP tool exposes one — tool
arguments are model-controlled, so a `user_id` parameter would let a prompt
injection act as another user. Identity comes from the transport instead; see
[Identity propagation](../docs/api-contract.md#identity-propagation).

The MCP server resolves a `UserContext { userId }` and sends it as a header.
Handlers read it through one resolver:

```go
// X-Stockroom-User is set by the MCP server, which is this service's only
// client. Trusted WITHOUT verification -- safe solely because the port is
// loopback-bound. See docs/api-contract.md#the-trust-boundary.
func (s *Server) currentUserID(r *http.Request) int64 {
    if id, err := strconv.ParseInt(r.Header.Get("X-Stockroom-User"), 10, 64); err == nil {
        return id
    }
    return s.defaultUserID // Alice, for hosts that send no header
}
```

That indirection is the whole point: every query already says
`WHERE user_id = $1`, so the swap below touches one function, not the handlers.

### Swapping in real authentication

Five steps, in order. Nothing in the contract or the handlers changes.

**1. Populate `users` for real.** The table already has what is needed
(`email UNIQUE`, `password_hash`, `address`). Write real bcrypt/argon2 hashes;
drop the sentinel.

**2. Add a session mechanism.** The MCP server is the only caller, so a bearer
token or a signed cookie is enough. Nothing new is needed in the schema for a
stateless JWT; a server-side session table is also fine.

**3. Replace the one function.** Resolve the identity from a verified token
instead of a trusted header, and return an error rather than a bare id:

```go
func (s *Server) currentUserID(r *http.Request) (int64, error) {
    claims, err := s.tokens.Verify(r.Header.Get("Authorization"))
    if err != nil {
        return 0, ErrUnauthenticated
    }
    return claims.UserID, nil
}
```

**4. Add the auth middleware and a `401`.** Extend the error table in the
contract with `unauthenticated` / 401 and `forbidden` / 403, and wrap the
`/api/v1/cart` and `/api/v1/orders` routes. `/api/v1/products`,
`/api/v1/categories`, and `/media/{key}` stay public — they expose only catalog
data.

**5. Stop trusting the header.** Delete `EnsureDemoUsers`, the
`defaultUserID` field, and the `X-Stockroom-User` branch. A verified token
must *replace* that header, never sit alongside it — leaving both means the
unverified path still wins.

### What this deliberately does not do

No login, logout, registration, or password reset. No sessions, tokens, or
cookies. No verification of any kind: the three demo users are *selectable*,
not authenticated — whoever calls simply declares which one they are.

That is safe **only** because the service is loopback-bound with no public
route. If it is ever exposed, steps 4 and 5 stop being optional: anyone
reaching the port could name any user and read that cart or place orders as
them.

## Ordering rules the queries must follow

`schema.sql` has no `display_order` column on either child table, so ordering
is not free — get it wrong and it looks like a UI bug:

```sql
-- Sizes: S, M, L. Alphabetical would give L, M, S.
ORDER BY ps.price_adjustment_jpy ASC

-- Images: insertion order; the first is the card thumbnail.
ORDER BY pi.id ASC
```

## Local run

```bash
docker compose up -d          # from the repo root: Postgres + MinIO
go run ./cmd/api              # http://127.0.0.1:8080
curl -s 127.0.0.1:8080/healthz
```

Expects the same `.env` values the crawler uses (`STOCKROOM_DATABASE_URL`,
`MINIO_*`); see [crawler/.env.example](../crawler/.env.example). Populate the
catalog first — an empty database serves valid but empty responses.
