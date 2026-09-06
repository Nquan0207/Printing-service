import { boot, esc, readResult, renderError, table, yen } from "./ui";

type Item = { product_name: string; size_name: string; quantity: number; subtotal_jpy: number };
type Order = {
  order_number: string; status: string; total_jpy: number; created_at: string;
  user_name: string; user_email: string; shipping_address: string;
  items: Item[]; item_count: number; total_quantity: number;
};
/** What the server actually filtered on. Absent keys mean "not filtered", so
 *  the panel can show the filters in force rather than the ones it believes it
 *  sent -- the model's call and a click inside the panel both land here. */
type Applied = {
  statuses?: string[];
  min_total?: number; max_total?: number;
  min_quantity?: number; max_quantity?: number;
  from?: string; to?: string;
};
type Payload = { orders?: Order[]; total?: number; applied?: Applied };

const STATUSES = ["pending", "confirmed", "cancelled"] as const;

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const bar = document.getElementById("bar") as HTMLDivElement;
const app = boot("Orders");

/** Mirrors `applied` from the last result; every refetch is built from it, so
 *  a status toggle never silently drops the price or date filter the prompt
 *  asked for. */
let applied: Applied = {};

function args(): Record<string, unknown> {
  const a: Record<string, unknown> = {};
  if (applied.statuses?.length) a.status = applied.statuses.join(",");
  if (applied.min_total) a.min_total = applied.min_total;
  if (applied.max_total) a.max_total = applied.max_total;
  if (applied.min_quantity) a.min_quantity = applied.min_quantity;
  if (applied.max_quantity) a.max_quantity = applied.max_quantity;
  if (applied.from) a.date_from = applied.from;
  if (applied.to) a.date_to = applied.to;
  return a;
}

/** The non-status filters, as removable pills. Status has its own toggles, so
 *  showing it twice would just be two ways to disagree. */
function conditions(): { key: keyof Applied; label: string }[] {
  const c: { key: keyof Applied; label: string }[] = [];
  if (applied.min_total) c.push({ key: "min_total", label: `≥ ${yen(applied.min_total)}` });
  if (applied.max_total) c.push({ key: "max_total", label: `≤ ${yen(applied.max_total)}` });
  if (applied.min_quantity) c.push({ key: "min_quantity", label: `≥ ${applied.min_quantity} units` });
  if (applied.max_quantity) c.push({ key: "max_quantity", label: `≤ ${applied.max_quantity} units` });
  if (applied.from) c.push({ key: "from", label: `from ${applied.from}` });
  if (applied.to) c.push({ key: "to", label: `to ${applied.to}` });
  return c;
}

function renderBar() {
  const selected = new Set(applied.statuses ?? []);
  const chips = STATUSES.map(
    (s) => `<button data-status="${s}" aria-pressed="${selected.has(s)}">${s}</button>`,
  ).join("");

  // Each carries "×" because a filter you cannot lift is a dead end -- the
  // same trap the catalog's "All" used to be.
  const pills = conditions()
    .map(
      (c) =>
        `<button data-clear="${c.key}" aria-pressed="true"
                 title="Remove this filter">${esc(c.label)} ×</button>`,
    )
    .join("");

  const any = selected.size || conditions().length;
  bar.innerHTML = `
    <button data-status="" aria-pressed="${!any}" title="Every order">All</button>
    ${chips}${pills}`;
  bar.hidden = false;
}

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);

  applied = data.applied ?? {};
  renderBar();

  const orders = data.orders ?? [];
  const units = orders.reduce((n, o) => n + o.total_quantity, 0);
  const value = orders.reduce((n, o) => n + o.total_jpy, 0);
  sub.textContent =
    `${orders.length} of ${data.total ?? orders.length} orders · ` +
    `${units} units · ${yen(value)}`;

  const rows = orders.map((o) => {
    // The line items travel with the order, so a hover reveals them without
    // another round trip.
    const detail = o.items
      .map((i) => `${i.product_name} ${i.size_name} ×${i.quantity}`)
      .join("\n");
    return `<tr>
      <td class="mono">${esc(o.order_number)}</td>
      <td>${esc(o.user_name)}<br><span class="muted">${esc(o.user_email)}</span></td>
      <td class="num" title="${esc(detail)}">${o.total_quantity}
          <span class="muted">/ ${o.item_count}</span></td>
      <td class="num">${yen(o.total_jpy)}</td>
      <td class="muted">${esc(new Date(o.created_at).toLocaleDateString())}</td>
      <td><span class="pill ${esc(o.status)}">${esc(o.status)}</span></td>
    </tr>`;
  });
  out.innerHTML = table(
    [{ label: "Order" }, { label: "Customer" }, { label: "Units / lines", num: true },
     { label: "Total", num: true }, { label: "Placed" }, { label: "Status" }],
    rows,
  );
}

async function refetch() {
  sub.textContent = "Loading…";
  render(readResult<Payload>(await app.callServerTool({ name: "list_orders", arguments: args() })));
}

bar.addEventListener("click", (e) => {
  const b = (e.target as HTMLElement).closest("button");
  if (!b) return;

  if (b.dataset.clear) {
    delete applied[b.dataset.clear as keyof Applied];
  } else {
    const status = b.dataset.status ?? "";
    if (status === "") {
      applied = {}; // "All" clears every filter, not just the statuses.
    } else {
      const set = new Set(applied.statuses ?? []);
      set.has(status) ? set.delete(status) : set.add(status);
      applied.statuses = [...set];
    }
  }
  refetch();
});

app.ontoolresult = (r) => render(readResult<Payload>(r));
app.connect();
