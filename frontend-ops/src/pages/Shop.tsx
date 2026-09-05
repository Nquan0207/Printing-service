import { useCallback, useEffect, useMemo, useState } from "react";
import { api, yen, type Cart, type Category, type Product, type ProductList } from "../lib/api";

export default function Shop() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [list, setList] = useState<ProductList | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cartOpen, setCartOpen] = useState(false);

  const refreshCart = useCallback(async () => setCart(await api.cart()), []);

  useEffect(() => {
    api.categories().then((r) => setCategories(r.categories)).catch(() => {});
    refreshCart().catch(() => {});
  }, [refreshCart]);

  // Debounced so typing does not fire a request per keystroke.
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      api
        .products({ q: query, category, max_price: maxPrice, limit: 60, per_category: 8 })
        .then(setList)
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [query, category, maxPrice]);

  return (
    <div className="shop">
      <div className="filters">
        <input
          className="search"
          placeholder="Search products…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.slug}>
              {c.name}
            </option>
          ))}
        </select>
        <input
          className="price"
          type="number"
          min={0}
          placeholder="Max ¥"
          value={maxPrice}
          onChange={(e) => setMaxPrice(e.target.value)}
        />
        <button className="cartbtn" onClick={() => setCartOpen(true)}>
          Cart {cart && cart.item_count > 0 ? `(${cart.item_count})` : ""}
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && !list && <p className="empty">Loading…</p>}

      {list && list.count === 0 && (
        <div className="empty big">
          <h2>No products match</h2>
          <p>Try a different search or clear the filters.</p>
        </div>
      )}

      {list?.groups.map((g) => (
        <section key={g.category.id} className="group">
          <h2>
            {g.category.name} <span>{g.count}</span>
          </h2>
          <div className="grid">
            {g.products.map((p) => (
              <ProductCard key={p.id} product={p} onAdded={refreshCart} />
            ))}
          </div>
        </section>
      ))}

      {cartOpen && (
        <CartDrawer cart={cart} onClose={() => setCartOpen(false)} onChanged={refreshCart} />
      )}
    </div>
  );
}

function ProductCard({ product, onAdded }: { product: Product; onAdded: () => Promise<void> }) {
  const [sizeId, setSizeId] = useState(product.sizes[0]?.id ?? 0);
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const size = useMemo(
    () => product.sizes.find((s) => s.id === sizeId) ?? product.sizes[0],
    [product.sizes, sizeId],
  );

  async function add() {
    if (!size) return;
    setBusy(true);
    try {
      await api.addToCart(product.id, size.id, qty);
      await onAdded();
      setDone(true);
      setTimeout(() => setDone(false), 1200);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="card">
      <div className="thumb">
        {product.images[0] ? (
          <img src={product.images[0]} alt={product.name} loading="lazy" />
        ) : (
          <div className="noimg">No image</div>
        )}
      </div>
      <h3 title={product.name}>{product.name}</h3>
      {product.brand && <p className="brand">{product.brand}</p>}

      <div className="sizes">
        {product.sizes.map((s) => (
          <button
            key={s.id}
            className={s.id === sizeId ? "on" : ""}
            onClick={() => setSizeId(s.id)}
            title={yen(s.unit_price_jpy)}
          >
            {s.size_name}
          </button>
        ))}
      </div>

      <div className="buy">
        <strong>{size ? yen(size.unit_price_jpy) : "—"}</strong>
        <input
          type="number"
          min={1}
          value={qty}
          onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))}
        />
        <button onClick={add} disabled={busy || !size}>
          {done ? "Added ✓" : busy ? "…" : "Add"}
        </button>
      </div>
      {size && qty > 1 && <p className="line">{qty} × = {yen(size.unit_price_jpy * qty)}</p>}
    </article>
  );
}

function CartDrawer({
  cart,
  onClose,
  onChanged,
}: {
  cart: Cart | null;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const [address, setAddress] = useState("東京都渋谷区1-2-3");
  const [placing, setPlacing] = useState(false);
  const [placed, setPlaced] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function checkout() {
    setPlacing(true);
    setError(null);
    try {
      const order = await api.placeOrder(address);
      setPlaced(order.order_number);
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Checkout failed");
    } finally {
      setPlacing(false);
    }
  }

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Your cart</h2>
          <button onClick={onClose}>✕</button>
        </header>

        {placed ? (
          <div className="placed">
            <h3>Order placed</h3>
            <p className="num">{placed}</p>
            <p>Your cart has been cleared.</p>
            <button onClick={onClose}>Keep shopping</button>
          </div>
        ) : !cart || cart.items.length === 0 ? (
          <p className="empty">Your cart is empty.</p>
        ) : (
          <>
            <ul className="lines">
              {cart.items.map((i) => (
                <li key={i.id}>
                  {i.image ? <img src={i.image} alt="" /> : <div className="noimg sm" />}
                  <div className="meta">
                    <p className="nm">{i.product_name}</p>
                    <p className="sub">
                      Size {i.size_name} · {i.quantity} × {yen(i.unit_price_jpy)}
                    </p>
                  </div>
                  <strong>{yen(i.subtotal_jpy)}</strong>
                  <button
                    className="rm"
                    title="Remove"
                    onClick={async () => {
                      await api.removeCartItem(i.id);
                      await onChanged();
                    }}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>

            <div className="total">
              <span>Total</span>
              <strong>{yen(cart.total_jpy)}</strong>
            </div>
            <p className="note">Mock pricing — no tax, shipping, or volume discounts.</p>

            <label className="addr">
              Shipping address
              <textarea value={address} onChange={(e) => setAddress(e.target.value)} rows={2} />
            </label>

            {error && <p className="error">{error}</p>}
            <button className="primary" onClick={checkout} disabled={placing || !address.trim()}>
              {placing ? "Placing…" : `Place order · ${yen(cart.total_jpy)}`}
            </button>
          </>
        )}
      </aside>
    </div>
  );
}
