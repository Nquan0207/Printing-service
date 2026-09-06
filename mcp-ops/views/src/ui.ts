/**
 * Shared View toolkit.
 *
 * Everything here is inlined into each single-file bundle: the host renders
 * ui:// resources in a sandboxed iframe under a deny-by-default CSP, so no
 * stylesheet or script may be loaded from outside the document.
 */
import { App } from "@modelcontextprotocol/ext-apps";

export const CSS = `
:root { color-scheme: light dark; --ink:#1f2933; --dim:#6b7684; --line:#e6e9ee;
        --card:#fff; --bg:#f7f8fa; --brand:#ef1f1f; --ok:#12b5a5; --warn:#f0a500; }
@media (prefers-color-scheme: dark) {
  :root { --ink:#e8eaed; --dim:#9aa4b2; --line:#2b3138; --card:#1b1f24; --bg:#14171a; }
}
* { box-sizing: border-box; }
body { margin:0; padding:16px; background:var(--bg); color:var(--ink);
       font:13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI",
            "Hiragino Sans","Noto Sans JP",sans-serif; }
h1 { font-size:15px; margin:0 0 2px; }
.sub { color:var(--dim); font-size:11px; margin:0 0 14px; }
.bar { display:flex; gap:6px; align-items:center; margin-bottom:12px; flex-wrap:wrap; }
.bar button { border:1px solid var(--line); background:var(--card); color:var(--dim);
              border-radius:7px; padding:4px 11px; font:inherit; cursor:pointer; }
.bar button[aria-pressed="true"] { border-color:var(--brand); color:var(--brand); font-weight:600; }
.bar input { border:1px solid var(--line); background:var(--card); color:inherit;
             border-radius:7px; padding:5px 10px; font:inherit; min-width:200px; }
table { border-collapse:collapse; width:100%; background:var(--card);
        border:1px solid var(--line); border-radius:9px; overflow:hidden; }
th { text-align:left; font-size:10px; text-transform:uppercase; letter-spacing:.05em;
     color:var(--dim); font-weight:600; padding:8px 10px; border-bottom:1px solid var(--line); }
td { padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
tr:last-child td { border-bottom:0; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px; }
.pill { display:inline-block; border-radius:999px; padding:1px 8px; font-size:10px; font-weight:600; }
.pill.confirmed { background:rgba(18,181,165,.15); color:var(--ok); }
.pill.cancelled { background:rgba(239,31,31,.13); color:var(--brand); }
.pill.pending   { background:rgba(240,165,0,.16); color:var(--warn); }
.pill.off       { background:rgba(107,118,132,.16); color:var(--dim); }
.err { background:rgba(239,31,31,.1); color:var(--brand); border-radius:8px;
       padding:10px; font-size:12px; }
.muted { color:var(--dim); }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(132px,1fr)); gap:10px; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:9px; padding:11px; }
.tile .lbl { font-size:10px; text-transform:uppercase; letter-spacing:.05em; color:var(--dim); }
.tile .val { font-size:20px; font-weight:700; margin-top:2px; }
.tile .hint { font-size:10px; color:var(--dim); margin-top:1px; }
`;

export const yen = (n: number) => "¥" + Number(n ?? 0).toLocaleString("ja-JP");

export const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export type ToolError = { error?: { code: string; message: string } };

/** Unwrap a tool result into its structured payload. */
export function readResult<T>(result: unknown): T & ToolError {
  const r = result as { structuredContent?: T; content?: { type: string; text?: string }[] };
  if (r?.structuredContent) return r.structuredContent as T & ToolError;
  const text = r?.content?.find((c) => c.type === "text")?.text;
  try {
    return (text ? JSON.parse(text) : {}) as T & ToolError;
  } catch {
    return { error: { code: "parse_error", message: text ?? "Unreadable tool result" } } as T & ToolError;
  }
}

/** A blank iframe looks like a host bug, so failures always render. */
export function renderError(el: HTMLElement, err: { code: string; message: string }) {
  el.innerHTML = `<div class="err"><b>${esc(err.code)}</b><br>${esc(err.message)}</div>`;
}

export function boot(name: string) {
  const app = new App({ name, version: "0.1.0" });
  const style = document.createElement("style");
  style.textContent = CSS;
  document.head.appendChild(style);
  return app;
}

export function table(headers: { label: string; num?: boolean }[], rows: string[]): string {
  if (rows.length === 0) return `<p class="muted">Nothing to show.</p>`;
  const head = headers
    .map((h) => `<th${h.num ? ' class="num"' : ""}>${esc(h.label)}</th>`)
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}
