import { boot, esc, readResult, renderError, table, yen } from "./ui";

type Item = { product_name: string; size_name: string; quantity: number; subtotal_jpy: number };
type Order = {
  order_number: string; status: string; total_jpy: number; created_at: string;
  user_name: string; user_email: string; shipping_address: string; items: Item[];
};
type Payload = { orders?: Order[]; total?: number };

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const bar = document.getElementById("bar") as HTMLDivElement;
const app = boot("Orders");

let status = "";
bar.innerHTML = ["", "confirmed", "pending", "cancelled"]
  .map((s) => `<button data-status="${s}">${s || "all"}</button>`)
  .join("");

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);
  const orders = data.orders ?? [];
  bar.hidden = false;
  for (const b of Array.from(bar.querySelectorAll<HTMLButtonElement>("button"))) {
    b.setAttribute("aria-pressed", String((b.dataset.status ?? "") === status));
  }
  sub.textContent = `${orders.length} shown${data.total ? ` of ${data.total}` : ""}${status ? ` · ${status}` : ""}`;

  const rows = orders.map((o) => {
    // The line items travel with the order, so a hover reveals them without
    // another round trip.
    const detail = o.items
      .map((i) => `${i.product_name} ${i.size_name} ×${i.quantity}`)
      .join("\n");
    return `<tr>
      <td class="mono">${esc(o.order_number)}</td>
      <td>${esc(o.user_name)}<br><span class="muted">${esc(o.user_email)}</span></td>
      <td class="num" title="${esc(detail)}">${o.items.length}</td>
      <td class="num">${yen(o.total_jpy)}</td>
      <td class="muted">${esc(new Date(o.created_at).toLocaleDateString())}</td>
      <td><span class="pill ${esc(o.status)}">${esc(o.status)}</span></td>
    </tr>`;
  });
  out.innerHTML = table(
    [{ label: "Order" }, { label: "Customer" }, { label: "Items", num: true },
     { label: "Total", num: true }, { label: "Placed" }, { label: "Status" }],
    rows,
  );
}

app.ontoolresult = (r) => render(readResult<Payload>(r));

bar.addEventListener("click", async (e) => {
  const b = (e.target as HTMLElement).closest("button");
  if (!b) return;
  status = b.dataset.status ?? "";
  sub.textContent = "Loading…";
  const r = await app.callServerTool({
    name: "list_orders",
    arguments: status ? { status } : {},
  });
  render(readResult<Payload>(r));
});

app.connect();
