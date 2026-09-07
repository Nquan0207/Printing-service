import { boot, esc, readResult, renderError, table, yen } from "./ui";

type User = {
  id: number; name: string; email: string; created_at: string; is_admin: boolean;
  cart_lines: number; orders: number; spent_jpy: number;
};
/** What the server actually filtered on -- the same contract as the order
 *  list. The panel renders itself from this, which is what makes the controls
 *  arrive pre-filled from the prompt. */
type Applied = {
  q?: string; role?: "admin" | "customer"; has_cart?: boolean;
  min_orders?: number; max_orders?: number;
  min_spent?: number; max_spent?: number;
  from?: string; to?: string;
};
type Payload = { users?: User[]; total?: number; applied?: Applied };

/** Field id -> the tool argument it fills. */
const FIELDS = {
  q: "q",
  min_orders: "min_orders",
  max_orders: "max_orders",
  min_spent: "min_spent",
  max_spent: "max_spent",
  from: "date_from",
  to: "date_to",
} as const;
type Field = keyof typeof FIELDS;

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const bar = document.getElementById("bar") as HTMLDivElement;
const app = boot("Users");

let applied: Applied = {};

// Built ONCE: re-rendering the bar on every result would take the caret away
// mid-keystroke. Results only update values and pressed states.
const num = `style="min-width:0;width:92px"`;
bar.innerHTML = `
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;width:100%">
    <button data-role="" title="Clear every filter">All</button>
    <button data-role="admin">admins</button>
    <button data-role="customer">customers</button>
    <button data-cart="1" title="Accounts with something left in the basket">has cart</button>
    <input id="q" style="min-width:0;width:190px" placeholder="Name or email…" />
  </div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;width:100%">
    <span class="muted">orders</span>
    <input id="min_orders" type="number" min="0" ${num} placeholder="min" />
    <input id="max_orders" type="number" min="0" ${num} placeholder="max" />
    <span class="muted">spent ¥</span>
    <input id="min_spent" type="number" min="0" ${num} placeholder="min" />
    <input id="max_spent" type="number" min="0" ${num} placeholder="max" />
    <span class="muted">joined</span>
    <input id="from" type="date" style="min-width:0" />
    <input id="to" type="date" style="min-width:0" />
  </div>`;

const field = (id: Field) => document.getElementById(id) as HTMLInputElement;

function syncBar() {
  for (const id of Object.keys(FIELDS) as Field[]) {
    const value = applied[id];
    field(id).value = value === undefined ? "" : String(value);
  }
  const none = !Object.keys(applied).length;
  for (const b of Array.from(bar.querySelectorAll<HTMLButtonElement>("button"))) {
    const pressed = b.dataset.cart
      ? Boolean(applied.has_cart)
      : (b.dataset.role ?? "") === "" ? none : b.dataset.role === applied.role;
    b.setAttribute("aria-pressed", String(pressed));
  }
  bar.hidden = false;
}

function args(): Record<string, unknown> {
  const a: Record<string, unknown> = {};
  if (applied.role) a.role = applied.role;
  if (applied.has_cart) a.has_cart = true;
  for (const [id, arg] of Object.entries(FIELDS) as [Field, string][]) {
    const value = applied[id];
    if (value === undefined || value === "") continue;
    // 0 is a real filter on orders ("never ordered"), so it must survive here
    // even though 0 means "unset" for every money field.
    if (value === 0 && id !== "max_orders" && id !== "min_orders") continue;
    a[arg] = value;
  }
  return a; // an omitted max_orders falls through to the tool's -1 = "no maximum"

}

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);

  applied = data.applied ?? {};
  syncBar();

  const users = data.users ?? [];
  const spent = users.reduce((n, u) => n + u.spent_jpy, 0);
  const orders = users.reduce((n, u) => n + u.orders, 0);
  sub.textContent =
    `${users.length} of ${data.total ?? users.length} accounts · ${orders} orders · ${yen(spent)}`;

  const rows = users.map((u) => `<tr>
    <td class="muted mono">${u.id}</td>
    <td>${esc(u.name)}${u.is_admin ? ' <span class="pill off">admin</span>' : ""}</td>
    <td class="muted">${esc(u.email)}</td>
    <td class="num">${u.cart_lines}</td>
    <td class="num">${u.orders}</td>
    <td class="num">${yen(u.spent_jpy)}</td>
    <td class="muted">${esc(new Date(u.created_at).toLocaleDateString())}</td>
  </tr>`);
  out.innerHTML = table(
    [{ label: "ID" }, { label: "Name" }, { label: "Email" },
     { label: "Cart", num: true }, { label: "Orders", num: true },
     { label: "Spent", num: true }, { label: "Joined" }],
    rows,
  );
}

async function refetch() {
  sub.textContent = "Loading…";
  render(readResult<Payload>(await app.callServerTool({ name: "list_users", arguments: args() })));
}

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
  if (b.dataset.cart) {
    applied.has_cart = !applied.has_cart;
    readBar();
  } else {
    const role = b.dataset.role ?? "";
    if (role === "") {
      applied = {}; // "All" clears everything, not just the role.
    } else {
      // Roles are mutually exclusive; clicking the active one clears it.
      applied.role = applied.role === role ? undefined : (role as "admin" | "customer");
      if (!applied.role) delete applied.role;
      readBar();
    }
  }
  window.clearTimeout(timer);
  refetch();
});

bar.addEventListener("input", (e) => {
  schedule((e.target as HTMLInputElement).type === "date" ? 0 : 350);
});
bar.addEventListener("change", () => schedule(0));

app.ontoolresult = (r) => render(readResult<Payload>(r));
app.connect();
