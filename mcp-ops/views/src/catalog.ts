import { boot, esc, readResult, renderError, table, yen } from "./ui";

type Size = { size_name: string; unit_price_jpy: number };
type Product = {
  id: number; name: string; brand: string | null; base_price_jpy: number;
  category: { slug: string; name: string }; sizes: Size[]; images: string[];
};
type Payload = { products?: Product[]; count?: number };

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const bar = document.getElementById("bar") as HTMLDivElement;
const app = boot("Catalog");

bar.innerHTML = `<input id="q" placeholder="Search products…" />`;
const search = bar.querySelector<HTMLInputElement>("#q")!;

function render(data: Payload & { error?: { code: string; message: string } }) {
  if (data.error) return renderError(out, data.error);
  const products = data.products ?? [];
  bar.hidden = false;
  sub.textContent = `${products.length} product${products.length === 1 ? "" : "s"}`;

  const rows = products.map((p) => {
    // Sizes arrive ordered by price adjustment, so S/M/L reads correctly.
    const ladder = p.sizes
      .map((s) => `${esc(s.size_name)} ${yen(s.unit_price_jpy)}`)
      .join(" · ");
    const thumb = p.images[0]
      ? `<img src="${esc(p.images[0])}" alt="" width="34" height="34"
              style="object-fit:contain;border-radius:4px;background:var(--bg)" />`
      : "";
    return `<tr>
      <td class="muted mono">${p.id}</td>
      <td>${thumb}</td>
      <td>${esc(p.name)}${p.brand ? `<br><span class="muted">${esc(p.brand)}</span>` : ""}</td>
      <td class="muted">${esc(p.category.name)}</td>
      <td class="num">${yen(p.base_price_jpy)}</td>
      <td class="muted">${ladder}</td>
    </tr>`;
  });
  out.innerHTML = table(
    [{ label: "ID" }, { label: "" }, { label: "Product" }, { label: "Category" },
     { label: "Base", num: true }, { label: "Sizes" }],
    rows,
  );
}

app.ontoolresult = (r) => render(readResult<Payload>(r));

// Debounced so typing does not fire a tool call per keystroke.
let timer: number | undefined;
search.addEventListener("input", () => {
  window.clearTimeout(timer);
  timer = window.setTimeout(async () => {
    sub.textContent = "Loading…";
    const q = search.value.trim();
    const r = await app.callServerTool({ name: "list_products", arguments: q ? { q } : {} });
    render(readResult<Payload>(r));
  }, 300);
});

app.connect();
