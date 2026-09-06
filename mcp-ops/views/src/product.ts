import { boot, esc, readResult, renderError, yen } from "./ui";

type Size = { size_name: string; price_adjustment_jpy: number; unit_price_jpy: number };
type Product = {
  id: number; name: string; brand: string | null; description: string | null;
  base_price_jpy: number; category: { name: string }; sizes: Size[]; images: string[];
  /** Present when the name matched more than one product. Offered rather than
   *  silently resolved: picking one row out of eight is how you show the
   *  wrong product. */
  other_matches?: { id: number; name: string }[];
};

const out = document.getElementById("out")!;
const sub = document.getElementById("sub")!;
const app = boot("Product");

function render(p: Product & { error?: { code: string; message: string } }) {
  if (p.error) return renderError(out, p.error);
  if (!p?.id) {
    out.innerHTML = `<p class="muted">No product returned.</p>`;
    return;
  }
  sub.textContent = `#${p.id} · ${p.category?.name ?? ""}${p.brand ? ` · ${p.brand}` : ""}`;

  // Images are absolute URLs at the Go service; the View's CSP names that
  // origin, otherwise the sandbox would block them.
  const gallery = p.images.length
    ? `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
        ${p.images
          .map(
            (src) =>
              `<img src="${esc(src)}" alt="" width="120" height="120"
                    style="object-fit:contain;border-radius:8px;background:var(--card);
                           border:1px solid var(--line)" />`,
          )
          .join("")}
       </div>`
    : `<p class="muted">No images.</p>`;

  const sizes = p.sizes
    .map(
      (s) => `<tr>
        <td>${esc(s.size_name)}</td>
        <td class="num muted">${s.price_adjustment_jpy >= 0 ? "+" : ""}${yen(s.price_adjustment_jpy)}</td>
        <td class="num"><b>${yen(s.unit_price_jpy)}</b></td>
      </tr>`,
    )
    .join("");

  out.innerHTML = `
    ${gallery}
    <p style="margin:0 0 4px"><b>${esc(p.name)}</b></p>
    ${p.description ? `<p class="muted" style="margin:0 0 12px">${esc(p.description)}</p>` : ""}
    <table>
      <thead><tr><th>Size</th><th class="num">Adjustment</th><th class="num">Unit price</th></tr></thead>
      <tbody>${sizes}</tbody>
    </table>
    <p class="sub" style="margin-top:8px">Base ${yen(p.base_price_jpy)} · unit price = base + adjustment</p>
    ${
      p.other_matches?.length
        ? `<p class="muted" style="margin-top:10px">Also matched:
             ${p.other_matches.map((m) => `#${m.id} ${esc(m.name)}`).join(" · ")}</p>`
        : ""
    }`;
}

app.ontoolresult = (r) => render(readResult<Product>(r));
app.connect();
