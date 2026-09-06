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
  available_categories?: { slug: string; name: string; count: number }[];
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
/** Reveals the categories filtered out of the chip row. */
let showAllChips = false;
let lastGroups: Group[] = [];
let lastAvailable: Payload["available_categories"] = [];

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

function renderChips(available: Payload["available_categories"]) {
  const all = available ?? [];
  // With a filter on, show only the categories in play. The full set is one
  // click away behind "＋", so narrowing does not strand you.
  const visible = selected.size && !showAllChips ? all.filter((c) => selected.has(c.slug)) : all;

  const chips = visible
    .map(
      (c) =>
        `<button data-slug="${esc(c.slug)}" aria-pressed="${selected.has(c.slug)}"
                 title="${esc(c.slug)}">${esc(c.name)} <span class="muted">${c.count}</span></button>`,
    )
    .join("");

  const hidden = all.length - visible.length;
  const more = hidden
    ? `<button data-more="1" title="Show the other categories">＋${hidden}</button>`
    : "";

  bar.innerHTML = `
    <input id="q" placeholder="Search products…" value="${esc(query)}" />
    <button data-slug="" aria-pressed="${selected.size === 0}">All</button>
    ${chips}${more}`;
  bar.hidden = false;
}

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);

  // Update the selection BEFORE painting chips: renderChips reads `selected`,
  // so doing it the other way round highlights the previous request's
  // categories, which then disagree with the data on screen.
  selected = new Set(data.selected_categories ?? []);
  lastAvailable = data.available_categories ?? [];
  // A new result collapses the chip row back to the active selection.
  showAllChips = false;
  // The response always carries the full category list, so "＋" can reveal
  // the rest without another call.
  renderChips(lastAvailable);

  const groups = data.groups ?? [];
  lastGroups = groups;
  const shown = selected.size ? `${selected.size} of ${(data.available_categories ?? []).length} categories` : "all categories";
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
  if (b.dataset.more) {
    // Pure presentation -- no refetch needed to show more chips.
    showAllChips = true;
    renderChips(lastAvailable);
    return;
  }
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
