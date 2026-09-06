import { boot, esc, readResult, renderError, yen } from "./ui";

type Size = { size_name: string; unit_price_jpy: number };
type Product = {
  id: number; name: string; brand: string | null; base_price_jpy: number;
  description?: string | null; sizes: Size[]; images: string[];
};
type Group = { category: { slug: string; name: string }; count: number; products: Product[] };
type Payload = {
  groups?: Group[];
  count?: number;
  selected_categories?: string[];
  unmatched_categories?: string[];
};

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const bar = document.getElementById("bar") as HTMLDivElement;
const app = boot("Catalog");

/** Slugs currently selected. Empty means "all categories". */
let selected = new Set<string>();
let query = "";
/** Rows expanded in place. The payload already carries every product's
 *  description, sizes and images, so drilling in needs no extra tool call. */
const expanded = new Set<number>();
let lastGroups: Group[] = [];

function detailRow(p: Product) {
  const shots = p.images.length
    ? p.images
        .map(
          (src) =>
            `<img src="${esc(src)}" alt="" width="96" height="96"
                  style="object-fit:contain;border-radius:6px;background:var(--bg);
                         border:1px solid var(--line)" />`,
        )
        .join("")
    : `<span class="muted">No images.</span>`;
  const ladder = p.sizes
    .map(
      (s) =>
        `<tr><td>${esc(s.size_name)}</td><td class="num"><b>${yen(s.unit_price_jpy)}</b></td></tr>`,
    )
    .join("");
  return `<tr><td colspan="5" style="background:var(--bg)">
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">${shots}</div>
    ${p.description ? `<p class="muted" style="margin:0 0 8px">${esc(p.description)}</p>` : ""}
    <table style="max-width:260px"><tbody>${ladder}</tbody></table>
  </td></tr>`;
}

function rows(products: Product[]) {
  return products
    .map((p) => {
      // Sizes arrive ordered by price adjustment, so S/M/L reads correctly.
      const ladder = p.sizes
        .map((s) => `${esc(s.size_name)} ${yen(s.unit_price_jpy)}`)
        .join(" · ");
      const thumb = p.images[0]
        ? `<img src="${esc(p.images[0])}" alt="" width="32" height="32"
                style="object-fit:contain;border-radius:4px;background:var(--bg)" />`
        : "";
      const open = expanded.has(p.id);
      return `<tr data-product="${p.id}" style="cursor:pointer"
                  title="Click for photos and description">
        <td class="muted mono">${open ? "▾" : "▸"} ${p.id}</td>
        <td>${thumb}</td>
        <td>${esc(p.name)}${p.brand ? `<br><span class="muted">${esc(p.brand)}</span>` : ""}</td>
        <td class="num">${yen(p.base_price_jpy)}</td>
        <td class="muted">${ladder}</td>
      </tr>${open ? detailRow(p) : ""}`;
    })
    .join("");
}

// Chips come from the groups on screen, nothing more. Listing the categories
// you did not ask for would mean fetching them, and asking for two categories
// should cost exactly one request for two categories.
function renderChips(groups: Group[]) {
  const chips = groups
    .map(
      (g) =>
        // Unfiltered, the chips are every category and none reads as pressed:
        // clicking one narrows to it. Filtered, they are the selection itself,
        // and clicking one drops it.
        `<button data-slug="${esc(g.category.slug)}" aria-pressed="${selected.has(g.category.slug)}"
                 title="${esc(g.category.slug)}">${esc(g.category.name)} <span class="muted">${g.count}</span></button>`,
    )
    .join("");

  bar.innerHTML = `
    <input id="q" placeholder="Search products…" value="${esc(query)}" />
    <button data-slug="" aria-pressed="${selected.size === 0}"
            title="Every category">All</button>
    ${chips}`;
  bar.hidden = false;
}

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);

  // Update the selection BEFORE painting chips: renderChips reads `selected`,
  // so doing it the other way round highlights the previous request's
  // categories, which then disagree with the data on screen.
  selected = new Set(data.selected_categories ?? []);

  const groups = data.groups ?? [];
  lastGroups = groups;
  renderChips(groups);

  const shown = selected.size
    ? `${groups.length} ${groups.length === 1 ? "category" : "categories"}`
    : "all categories";
  sub.textContent = `${data.count ?? 0} products · ${shown}`;

  if (data.unmatched_categories?.length) {
    sub.textContent += ` · no match for: ${data.unmatched_categories.join(", ")}`;
  }
  paint(groups);
}

function paint(groups: Group[]) {
  if (groups.length === 0) {
    out.innerHTML = `<p class="muted">No products match.</p>`;
    return;
  }

  out.innerHTML = groups
    .map(
      (g) => `<section style="margin-bottom:18px">
        <h2 style="font-size:12px;margin:0 0 6px;display:flex;gap:7px;align-items:center">
          ${esc(g.category.name)}
          <span class="pill off">${g.count}</span>
        </h2>
        <table>
          <thead><tr><th>ID</th><th></th><th>Product</th><th class="num">Base</th><th>Sizes</th></tr></thead>
          <tbody>${rows(g.products)}</tbody>
        </table>
      </section>`,
    )
    .join("");
}

async function refetch() {
  sub.textContent = "Loading…";
  const args: Record<string, unknown> = {};
  if (selected.size) args.categories = [...selected];
  if (query) args.q = query;
  render(readResult<Payload>(await app.callServerTool({ name: "list_products", arguments: args })));
}

bar.addEventListener("click", (e) => {
  const b = (e.target as HTMLElement).closest("button");
  if (!b) return;
  const slug = b.dataset.slug ?? "";
  if (slug === "") {
    selected.clear(); // "All"
  } else if (selected.has(slug)) {
    selected.delete(slug);
  } else {
    selected.add(slug);
  }
  refetch();
});

let timer: number | undefined;
bar.addEventListener("input", (e) => {
  if ((e.target as HTMLElement).id !== "q") return;
  query = (e.target as HTMLInputElement).value.trim();
  window.clearTimeout(timer);
  timer = window.setTimeout(refetch, 300);
});

// Expanding a row is pure presentation: re-render from the payload we already
// have rather than calling the server again.
out.addEventListener("click", (e) => {
  const row = (e.target as HTMLElement).closest<HTMLElement>("tr[data-product]");
  if (!row) return;
  const id = Number(row.dataset.product);
  if (expanded.has(id)) expanded.delete(id);
  else expanded.add(id);
  paint(lastGroups);
});

app.ontoolresult = (r) => render(readResult<Payload>(r));
app.connect();
