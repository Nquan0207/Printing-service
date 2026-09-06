import { boot, esc, readResult, renderError, table, yen } from "./ui";

type Item = { product_name: string; size_name: string; quantity: number; subtotal_jpy: number };
type Order = {
  order_number: string; status: string; total_jpy: number; created_at: string;
  user_name: string; user_email: string; shipping_address: string;
  items: Item[]; item_count: number; total_quantity: number;
};
/** What the server actually filtered on. Absent keys mean "not filtered".
 *  The panel renders itself from this rather than from what it believes it
 *  sent, so a prompt-driven filter and a typed one land in the same place --
 *  which is what makes the controls arrive pre-filled. */
type Applied = {
  q?: string;
  statuses?: string[];
  min_total?: number; max_total?: number;
  min_quantity?: number; max_quantity?: number;
  from?: string; to?: string;
};
type Payload = { orders?: Order[]; total?: number; applied?: Applied };

const STATUSES = ["pending", "confirmed", "cancelled"] as const;
/** Field id -> the tool argument it fills. Everything except status is a plain
 *  input, so one table drives both reading and writing them. */
const FIELDS = {
  q: "q",
  min_total: "min_total",
  max_total: "max_total",
  min_quantity: "min_quantity",
  max_quantity: "max_quantity",
  from: "date_from",
  to: "date_to",
} as const;
type Field = keyof typeof FIELDS;

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const bar = document.getElementById("bar") as HTMLDivElement;
const app = boot("Orders");

let applied: Applied = {};

// The bar is built ONCE. Re-rendering it on every result would blow away the
// caret mid-keystroke, so results only ever update values and pressed states.
const num = `style="min-width:0;width:92px"`;
bar.innerHTML = `
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;width:100%">
    <button data-status="" title="Clear every filter">All</button>
    ${STATUSES.map((s) => `<button data-status="${s}">${s}</button>`).join("")}
    <input id="q" style="min-width:0;width:190px" placeholder="Order # or customer…" />
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;width:100%">
    <span class="muted">¥</span>
    <input id="min_total" type="number" min="0" ${num} placeholder="min" />
    <input id="max_total" type="number" min="0" ${num} placeholder="max" />
    <span class="muted">units</span>
    <input id="min_quantity" type="number" min="0" ${num} placeholder="min" />
    <input id="max_quantity" type="number" min="0" ${num} placeholder="max" />
    <span class="muted">placed</span>
    <input id="from" type="date" style="min-width:0" />
    <input id="to" type="date" style="min-width:0" />
  </div>`;

const field = (id: Field) => document.getElementById(id) as HTMLInputElement;

/** Push `applied` into the controls, so the panel opens showing the filters
 *  the prompt produced. */
function syncBar() {
  for (const id of Object.keys(FIELDS) as Field[]) {
    const value = applied[id];
    field(id).value = value === undefined ? "" : String(value);
  }
  const selected = new Set(applied.statuses ?? []);
  for (const b of Array.from(bar.querySelectorAll<HTMLButtonElement>("button[data-status]"))) {
    const s = b.dataset.status ?? "";
    b.setAttribute("aria-pressed", String(s === "" ? !Object.keys(applied).length : selected.has(s)));
  }
  bar.hidden = false;
}

function args(): Record<string, unknown> {
  const a: Record<string, unknown> = {};
  if (applied.statuses?.length) a.status = applied.statuses.join(",");
  for (const [id, arg] of Object.entries(FIELDS) as [Field, string][]) {
    const value = applied[id];
    if (value !== undefined && value !== "" && value !== 0) a[arg] = value;
  }
  return a;
}

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);

  applied = data.applied ?? {};
  syncBar();

  const orders = data.orders ?? [];
  const units = orders.reduce((n, o) => n + o.total_quantity, 0);
  const value = orders.reduce((n, o) => n + o.total_jpy, 0);
  sub.textContent =
    `${orders.length} of ${data.total ?? orders.length} orders · ${units} units · ${yen(value)}`;

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

/** Read the controls back into `applied`. The server is the authority on what
 *  was applied, but until it answers these are the pending values. */
function readBar() {
  for (const id of Object.keys(FIELDS) as Field[]) {
    const raw = field(id).value.trim();
    if (raw === "") delete applied[id];
    else if (field(id).type === "number") (applied[id] as number) = Number(raw);
    else (applied[id] as string) = raw;
  }
}

let timer: number | undefined;
function schedule(delay: number) {
  window.clearTimeout(timer);
  timer = window.setTimeout(() => {
    readBar();
    refetch();
  }, delay);
}

bar.addEventListener("click", (e) => {
  const b = (e.target as HTMLElement).closest("button");
  if (!b) return;
  const status = b.dataset.status ?? "";
  if (status === "") {
    applied = {}; // "All" clears everything, not just the statuses.
  } else {
    const set = new Set(applied.statuses ?? []);
    set.has(status) ? set.delete(status) : set.add(status);
    applied.statuses = [...set];
    readBar(); // a chip must not discard what is typed in the other fields
  }
  window.clearTimeout(timer);
  refetch();
});

// Typing waits; picking a date or leaving a field does not.
bar.addEventListener("input", (e) => {
  schedule((e.target as HTMLInputElement).type === "date" ? 0 : 350);
});
bar.addEventListener("change", () => schedule(0));

app.ontoolresult = (r) => render(readResult<Payload>(r));
app.connect();
