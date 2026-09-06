import { App } from "@modelcontextprotocol/ext-apps";
import { areaChart, barChart, card, empty, rowChart } from "./charts";

/** Shape returned by GET /api/v1/admin/stats, via the get_dashboard tool. */
type Stats = {
  totals?: {
    products: number; active_products: number; categories: number; sizes: number;
    images: number; users: number; orders: number; revenue_jpy: number;
    open_cart_lines: number; cancelled_orders: number;
  };
  products_by_category?: { slug: string; name: string; count: number }[];
  orders_by_day?: { date: string; orders: number; revenue_jpy: number }[];
  top_products?: { product_id: number; product_name: string; quantity: number; revenue_jpy: number }[];
  price_buckets?: { label: string; count: number }[];
  error?: { code: string; message: string };
};

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const range = document.getElementById("range") as HTMLDivElement;

const yen = (n: number) => "¥" + n.toLocaleString("ja-JP");
/** "2026-09-06" -> "09-06". The year is in the range selector, not on 90 ticks. */
const shortDate = (iso: string) => iso.slice(5);
const esc = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

let days = 30;

const app = new App({ name: "Stockroom ops", version: "0.1.0" });

function tile(label: string, value: string | number, hint?: string) {
  return `<div class="tile"><div class="lbl">${esc(label)}</div>
    <div class="val">${esc(String(value))}</div>
    ${hint ? `<div class="hint">${esc(hint)}</div>` : ""}</div>`;
}

function render(stats: Stats) {
  if (stats.error) {
    // A blank iframe is the worst failure mode; say what went wrong.
    out.innerHTML = `<div class="err"><b>${esc(stats.error.code)}</b><br>${esc(stats.error.message)}</div>`;
    sub.textContent = "Could not load figures";
    return;
  }
  const t = stats.totals;
  if (!t) {
    out.innerHTML = `<p class="muted">No data returned.</p>`;
    return;
  }
  range.hidden = false;
  for (const b of Array.from(range.querySelectorAll<HTMLButtonElement>("button"))) {
    b.setAttribute("aria-pressed", String(Number(b.dataset.days) === days));
  }
  const cats = stats.products_by_category ?? [];
  const byDay = stats.orders_by_day ?? [];
  const top = stats.top_products ?? [];
  const buckets = stats.price_buckets ?? [];
  sub.textContent = `${t.products} products · ${t.categories} categories · last ${days} days`;

  const rows = top
    .map(
      (p) => `<tr>
        <td>${esc(p.product_name)}</td>
        <td class="num">${p.quantity}</td>
        <td class="num">${esc(yen(p.revenue_jpy))}</td>
      </tr>`,
    )
    .join("");

  out.innerHTML = `<div class="tiles">
    ${tile("Revenue", yen(t.revenue_jpy), "cancelled excluded")}
    ${tile("Orders", t.orders, `${t.cancelled_orders} cancelled`)}
    ${tile("Products", t.products, `${t.active_products} active`)}
    ${tile("Users", t.users, `${t.open_cart_lines} open cart lines`)}
    ${tile("Categories", t.categories, cats[0] ? `top: ${cats[0].name}` : undefined)}
    ${tile("Sizes", t.sizes, `${t.images} images`)}
  </div>

  <div class="grids">
    ${card(
      "Revenue per day",
      areaChart(byDay.map((d) => ({ label: shortDate(d.date), value: d.revenue_jpy }))),
    )}
    ${card(
      "Orders per day",
      barChart(
        byDay.map((d) => ({
          label: shortDate(d.date),
          value: d.orders,
          hint: `${d.orders} order${d.orders === 1 ? "" : "s"} · ${yen(d.revenue_jpy)}`,
        })),
      ),
    )}
    ${card(
      "Products per category",
      rowChart(cats.map((c) => ({ label: c.name, value: c.count }))),
    )}
    ${card(
      "Unit price distribution",
      barChart(
        buckets.map((b) => ({ label: b.label, value: b.count, hint: `${b.count} sizes` })),
        (n) => String(n),
        "warn",
      ),
    )}
  </div>

  ${card(
    "Top products by revenue",
    rows
      ? `<table><thead><tr><th>Product</th><th class="num">Units</th><th class="num">Revenue</th></tr></thead>
         <tbody>${rows}</tbody></table>`
      : empty("Nothing sold in this range."),
  )}`;
}

function readResult(result: unknown): Stats {
  const r = result as { structuredContent?: Stats; content?: { type: string; text?: string }[] };
  if (r?.structuredContent) return r.structuredContent;
  const text = r?.content?.find((c) => c.type === "text")?.text;
  try {
    return text ? (JSON.parse(text) as Stats) : {};
  } catch {
    return { error: { code: "parse_error", message: text ?? "Unreadable tool result" } };
  }
}

// The host pushes the first result when it renders the View.
app.ontoolresult = (result) => render(readResult(result));

// Range buttons call the tool again from inside the iframe -- no model round trip.
range.addEventListener("click", async (event) => {
  const button = (event.target as HTMLElement).closest("button");
  if (!button) return;
  days = Number(button.dataset.days);
  sub.textContent = "Loading…";
  const result = await app.callServerTool({ name: "get_dashboard", arguments: { days } });
  render(readResult(result));
});

app.connect();
