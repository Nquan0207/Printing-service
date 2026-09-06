/**
 * Inline SVG charts.
 *
 * No chart library on purpose. The View is inlined into one HTML file for a
 * deny-by-default iframe CSP, and recharts + React would roughly triple the
 * bundle to draw five simple shapes. Every chart here is a string of SVG, so
 * there is nothing to hydrate and nothing to load.
 *
 * Interactivity is a native <title> per shape: the host renders it as a
 * tooltip with no JS, no positioning maths, and no way to escape the iframe.
 */

const esc = (s: unknown) =>
  String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export const yen = (n: number) => "¥" + Number(n ?? 0).toLocaleString("ja-JP");

/** Compact yen for axis labels, where ¥1,002,770 would collide with its neighbour. */
export function shortYen(n: number): string {
  if (n >= 1_000_000) return "¥" + (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + "M";
  if (n >= 1_000) return "¥" + Math.round(n / 1_000) + "k";
  return "¥" + n;
}

/** A "nice" axis maximum, so gridlines land on 200/500/1000 rather than 187. */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => value <= s * magnitude)! * magnitude;
  return step;
}

export function card(title: string, body: string): string {
  return `<section class="chart">
    <div class="lbl">${esc(title)}</div>
    ${body}
  </section>`;
}

export function empty(message = "No data for this range."): string {
  return `<p class="muted" style="margin:14px 0">${esc(message)}</p>`;
}

type Series = { label: string; value: number; hint?: string };

const W = 560;
const H = 190;
const PAD = { top: 12, right: 10, bottom: 26, left: 52 };

function gridlines(max: number, fmt: (n: number) => string): string {
  const plotH = H - PAD.top - PAD.bottom;
  return [0, 0.25, 0.5, 0.75, 1]
    .map((f) => {
      const y = PAD.top + plotH * (1 - f);
      return `<line x1="${PAD.left}" x2="${W - PAD.right}" y1="${y}" y2="${y}" class="grid" />
        <text x="${PAD.left - 6}" y="${y + 3}" class="axis" text-anchor="end">${esc(fmt(max * f))}</text>`;
    })
    .join("");
}

/** Every N-th label, so a 90-day range does not overprint its own axis. */
function everyNth(count: number): number {
  return Math.max(1, Math.ceil(count / 8));
}

/** Filled line chart -- revenue over time. */
export function areaChart(points: Series[], fmt = shortYen): string {
  if (points.length === 0) return empty();
  const max = niceMax(Math.max(...points.map((p) => p.value), 1));
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? plotW / 2 : (plotW * i) / (points.length - 1));
  const y = (v: number) => PAD.top + plotH * (1 - v / max);

  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const area = `${line}L${x(points.length - 1).toFixed(1)},${PAD.top + plotH}L${x(0).toFixed(1)},${PAD.top + plotH}Z`;
  const step = everyNth(points.length);

  // Dots carry the <title>: a 1px line is far too thin to hover.
  const dots = points
    .map(
      (p, i) =>
        `<circle cx="${x(i).toFixed(1)}" cy="${y(p.value).toFixed(1)}" r="7" fill="transparent">
          <title>${esc(p.label)} — ${esc(p.hint ?? fmt(p.value))}</title>
        </circle>`,
    )
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" class="svg" role="img">
    ${gridlines(max, fmt)}
    <path d="${area}" class="area" />
    <path d="${line}" class="line" fill="none" />
    ${dots}
    ${points
      .map((p, i) =>
        i % step ? "" : `<text x="${x(i).toFixed(1)}" y="${H - 8}" class="axis" text-anchor="middle">${esc(p.label)}</text>`,
      )
      .join("")}
  </svg>`;
}

/** Vertical bars -- orders per day, price distribution. */
export function barChart(points: Series[], fmt = (n: number) => String(n), accent = "ok"): string {
  if (points.length === 0) return empty();
  const max = niceMax(Math.max(...points.map((p) => p.value), 1));
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / points.length;
  const width = Math.max(3, Math.min(38, slot * 0.62));
  const step = everyNth(points.length);

  return `<svg viewBox="0 0 ${W} ${H}" class="svg" role="img">
    ${gridlines(max, fmt)}
    ${points
      .map((p, i) => {
        const h = (plotH * p.value) / max;
        const cx = PAD.left + slot * (i + 0.5);
        // Zero still gets a hover target, otherwise a quiet day is unreadable.
        return `<rect x="${(cx - width / 2).toFixed(1)}" y="${(PAD.top + plotH - h).toFixed(1)}"
                      width="${width.toFixed(1)}" height="${Math.max(h, 0).toFixed(1)}"
                      rx="2" class="bar ${accent}" />
          <rect x="${(cx - slot / 2).toFixed(1)}" y="${PAD.top}" width="${slot.toFixed(1)}"
                height="${plotH}" fill="transparent">
            <title>${esc(p.label)} — ${esc(p.hint ?? fmt(p.value))}</title>
          </rect>`;
      })
      .join("")}
    ${points
      .map((p, i) =>
        i % step ? "" : `<text x="${(PAD.left + slot * (i + 0.5)).toFixed(1)}" y="${H - 8}" class="axis" text-anchor="middle">${esc(p.label)}</text>`,
      )
      .join("")}
  </svg>`;
}

/** Horizontal bars -- category names are far too long for an x-axis. */
export function rowChart(points: Series[], fmt = (n: number) => String(n)): string {
  if (points.length === 0) return empty();
  const max = Math.max(...points.map((p) => p.value), 1);
  return `<div class="rows">
    ${points
      .map(
        (p) => `<div class="row" title="${esc(p.label)} — ${esc(p.hint ?? fmt(p.value))}">
          <span class="name">${esc(p.label)}</span>
          <span class="track"><span class="fill" style="width:${((p.value / max) * 100).toFixed(1)}%"></span></span>
          <span class="val">${esc(fmt(p.value))}</span>
        </div>`,
      )
      .join("")}
  </div>`;
}
