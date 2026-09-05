import { useCallback, useEffect, useState } from "react";
import {
  api,
  yen,
  type AdminOrder,
  type AdminUser,
  type Product,
  type Stats,
} from "../lib/api";
import { CategoryChart, OrdersChart, PriceChart, RevenueChart } from "../components/Charts";

type Tab = "overview" | "orders" | "products" | "users";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="admin">
      <div className="tabs">
        {(["overview", "orders", "products", "users"] as Tab[]).map((t) => (
          <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {tab === "overview" && <Overview />}
      {tab === "orders" && <OrdersTab />}
      {tab === "products" && <ProductsTab />}
      {tab === "users" && <UsersTab />}
    </div>
  );
}

function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [days, setDays] = useState(14);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.admin.stats(days).then(setStats).catch((e) => setError(e.message));
  }, [days]);

  if (error) return <p className="error">{error}</p>;
  if (!stats) return <p className="empty">Loading…</p>;
  const t = stats.totals;

  return (
    <>
      <div className="tiles">
        <Tile label="Revenue" value={yen(t.revenue_jpy)} hint="cancelled excluded" />
        <Tile label="Orders" value={t.orders} hint={`${t.cancelled_orders} cancelled`} />
        <Tile label="Products" value={t.products} hint={`${t.active_products} active`} />
        <Tile label="Users" value={t.users} hint={`${t.open_cart_lines} open cart lines`} />
        <Tile label="Categories" value={t.categories} />
        <Tile label="Sizes" value={t.sizes} hint={`${t.images} images`} />
      </div>

      <div className="rangebar">
        <span>Range</span>
        {[7, 14, 30, 90].map((d) => (
          <button key={d} className={d === days ? "on" : ""} onClick={() => setDays(d)}>
            {d}d
          </button>
        ))}
      </div>

      <div className="charts">
        <Panel title="Revenue per day">
          <RevenueChart data={stats.orders_by_day} />
        </Panel>
        <Panel title="Orders per day">
          <OrdersChart data={stats.orders_by_day} />
        </Panel>
        <Panel title="Products per category">
          <CategoryChart data={stats.products_by_category} />
        </Panel>
        <Panel title="Unit price distribution">
          <PriceChart data={stats.price_buckets} />
        </Panel>
      </div>

      <Panel title="Top products by revenue">
        {stats.top_products.length === 0 ? (
          <p className="empty">No orders yet.</p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Product</th>
                <th>Units</th>
                <th>Revenue</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_products.map((p, i) => (
                <tr key={i}>
                  <td>{p.product_name}</td>
                  <td>{p.quantity}</td>
                  <td>{yen(p.revenue_jpy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  );
}

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="tile">
      <p className="lbl">{label}</p>
      <p className="val">{value}</p>
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function OrdersTab() {
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.admin
      .orders(status || undefined)
      .then((r) => setOrders(r.orders))
      .catch((e) => setError(e.message));
  }, [status]);

  useEffect(load, [load]);

  async function change(orderNumber: string, next: string) {
    await api.admin.updateOrder(orderNumber, next);
    load();
  }

  return (
    <Panel title={`Orders (${orders.length})`}>
      <div className="rangebar">
        <span>Status</span>
        {["", "confirmed", "pending", "cancelled"].map((s) => (
          <button key={s || "all"} className={s === status ? "on" : ""} onClick={() => setStatus(s)}>
            {s || "all"}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      <table className="tbl">
        <thead>
          <tr>
            <th>Order</th>
            <th>Customer</th>
            <th>Items</th>
            <th>Total</th>
            <th>Placed</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.order_number}>
              <td className="mono">{o.order_number}</td>
              <td>
                {o.user_name}
                <span className="dim"> {o.user_email}</span>
              </td>
              <td title={o.items.map((i) => `${i.product_name} ${i.size_name} ×${i.quantity}`).join("\n")}>
                {o.items.length}
              </td>
              <td>{yen(o.total_jpy)}</td>
              <td className="dim">{new Date(o.created_at).toLocaleDateString()}</td>
              <td>
                <select value={o.status} onChange={(e) => change(o.order_number, e.target.value)}>
                  <option value="pending">pending</option>
                  <option value="confirmed">confirmed</option>
                  <option value="cancelled">cancelled</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {orders.length === 0 && <p className="empty">No orders.</p>}
    </Panel>
  );
}

function ProductsTab() {
  const [products, setProducts] = useState<Product[]>([]);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.admin
      .products(q || undefined)
      .then((r) => setProducts(r.products))
      .catch((e) => setError(e.message));
  }, [q]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  return (
    <Panel title={`Catalog (${products.length})`}>
      <div className="rangebar">
        <input
          className="search"
          placeholder="Filter products…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      {error && <p className="error">{error}</p>}
      <table className="tbl">
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Category</th>
            <th>Base</th>
            <th>Sizes</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {products.map((p) =>
            editing === p.id ? (
              <ProductEditor
                key={p.id}
                product={p}
                onDone={() => {
                  setEditing(null);
                  load();
                }}
              />
            ) : (
              <tr key={p.id}>
                <td className="dim">{p.id}</td>
                <td>{p.name}</td>
                <td className="dim">{p.category.name}</td>
                <td>{yen(p.base_price_jpy)}</td>
                <td className="dim">
                  {p.sizes.map((s) => `${s.size_name} ${yen(s.unit_price_jpy)}`).join(" · ")}
                </td>
                <td>
                  <button onClick={() => setEditing(p.id)}>Edit</button>
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
      {products.length === 0 && <p className="empty">No products.</p>}
      <p className="note">
        Edits are overwritten by the next crawl (it upserts on <code>source_product_id</code>).
      </p>
    </Panel>
  );
}

function ProductEditor({ product, onDone }: { product: Product; onDone: () => void }) {
  const [name, setName] = useState(product.name);
  const [price, setPrice] = useState(String(product.base_price_jpy));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(patch: Parameters<typeof api.admin.updateProduct>[1]) {
    setBusy(true);
    setError(null);
    try {
      await api.admin.updateProduct(product.id, patch);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setBusy(false);
    }
  }

  return (
    <tr className="editing">
      <td className="dim">{product.id}</td>
      <td>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </td>
      <td className="dim">{product.category.name}</td>
      <td>
        <input
          className="num"
          type="number"
          min={0}
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
      </td>
      <td colSpan={2}>
        <div className="rowactions">
          <button
            disabled={busy}
            onClick={() => save({ name: name.trim(), base_price_jpy: Number(price) })}
          >
            Save
          </button>
          <button disabled={busy} onClick={() => save({ is_active: false })}>
            Deactivate
          </button>
          <button disabled={busy} onClick={onDone}>
            Cancel
          </button>
          {error && <span className="error">{error}</span>}
        </div>
      </td>
    </tr>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.admin.users().then((r) => setUsers(r.users)).catch((e) => setError(e.message));
  }, []);

  return (
    <Panel title={`Users (${users.length})`}>
      {error && <p className="error">{error}</p>}
      <table className="tbl">
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>Email</th>
            <th>Cart</th>
            <th>Orders</th>
            <th>Spent</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td className="dim">{u.id}</td>
              <td>
                {u.name}
                {u.is_admin && <em className="badge">admin</em>}
              </td>
              <td className="dim">{u.email}</td>
              <td>{u.cart_lines}</td>
              <td>{u.orders}</td>
              <td>{yen(u.spent_jpy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}
