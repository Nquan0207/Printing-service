import { useEffect, useState } from "react";
import { api, yen, type Order } from "../lib/api";

/** A signed-in customer's own order, looked up by number. */
export default function Orders() {
  const [number, setNumber] = useState("");
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const last = localStorage.getItem("stockroom.lastOrder");
    if (last) setNumber(last);
  }, []);

  async function lookup() {
    setError(null);
    setOrder(null);
    try {
      const o = await api.order(number.trim());
      setOrder(o);
      localStorage.setItem("stockroom.lastOrder", o.order_number);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lookup failed");
    }
  }

  return (
    <div className="orders">
      <h1>Find an order</h1>
      <div className="lookup">
        <input
          placeholder="RKS-20260904-0001"
          value={number}
          onChange={(e) => setNumber(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && lookup()}
        />
        <button onClick={lookup} disabled={!number.trim()}>
          Look up
        </button>
      </div>
      {error && <p className="error">{error}</p>}

      {order && (
        <article className="order">
          <header>
            <h2>{order.order_number}</h2>
            <span className={`pill ${order.status}`}>{order.status}</span>
          </header>
          <p className="sub">
            {new Date(order.created_at).toLocaleString()} · {order.shipping_address}
          </p>
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Size</th>
                <th>Qty</th>
                <th>Unit</th>
                <th>Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((i, n) => (
                <tr key={n}>
                  <td>{i.product_name}</td>
                  <td>{i.size_name}</td>
                  <td>{i.quantity}</td>
                  <td>{yen(i.unit_price_jpy)}</td>
                  <td>{yen(i.subtotal_jpy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="total">
            <span>Total</span>
            <strong>{yen(order.total_jpy)}</strong>
          </div>
        </article>
      )}
    </div>
  );
}
