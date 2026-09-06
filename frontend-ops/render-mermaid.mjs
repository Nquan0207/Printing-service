/**
 * Render docs/diagrams/*.mmd to PNG with the local mermaid package.
 *
 * Not mermaid-cli: that pulls its own chromium. This drives the system Chrome
 * we already use for render-check, and serves mermaid from node_modules so
 * nothing is fetched from a CDN.
 */
import { createServer } from "node:http";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { join, basename } from "node:path";
import { chromium } from "playwright";

const ROOT = new URL("..", import.meta.url).pathname;
const DIAGRAMS = join(ROOT, "docs/diagrams");
const DIST = join(ROOT, "frontend-ops/node_modules/mermaid/dist");
const SCALE = 2; // rendered at the diagram's natural size, then 2x for zooming

const server = createServer(async (req, res) => {
  // Serve the whole dist: the ESM build lazy-loads diagram chunks by
  // relative path, so a single-file handler leaves every renderer missing.
  if (req.url.startsWith("/dist/")) {
    try {
      const body = await readFile(join(DIST, req.url.slice(6)));
      res.writeHead(200, { "Content-Type": "text/javascript" });
      return res.end(body);
    } catch {
      res.writeHead(404);
      return res.end("no");
    }
  }
  res.writeHead(200, { "Content-Type": "text/html" });
  res.end(`<!doctype html><html><head><meta charset="utf-8">
    <style>body{margin:0;background:#fff;font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
    #d{display:inline-block;padding:20px}</style></head>
    <body><div id="d"></div>
    <script type="module">
      import mermaid from "/dist/mermaid.esm.min.mjs";
      window.draw = async (src, theme) => {
        mermaid.initialize({ startOnLoad:false, theme, fontFamily:'-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif' });
        const { svg } = await mermaid.render("g" + Math.random().toString(36).slice(2), src);
        document.getElementById("d").innerHTML = svg;
        return true;
      };
    </script></body></html>`);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}/`;

const browser = await chromium.launch({ channel: "chrome" });
const files = (await readdir(DIAGRAMS)).filter((f) => f.endsWith(".mmd"));
let failed = 0;

for (const file of files) {
  const src = await readFile(join(DIAGRAMS, file), "utf8");
  const page = await browser.newPage({ deviceScaleFactor: SCALE });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e).split("\n")[0]));
  await page.goto(base);
  try {
    await page.waitForFunction(() => typeof window.draw === "function", { timeout: 15000 });
    await page.evaluate(([s, t]) => window.draw(s, t), [src, "default"]);
  } catch (e) {
    console.log(`  FAIL ${file}:\n${String(e).split("\n").slice(0,8).join("\n")}`);
    failed++;
    await page.close();
    continue;
  }
  // mermaid caps the svg with a max-width, so a 3x scale factor would just
  // upscale a 300px render. Blow it out to the viewBox's natural size first.
  await page.evaluate(() => {
    const svg = document.querySelector("#d svg");
    const [, , w, h] = svg.getAttribute("viewBox").split(/[\s,]+/).map(Number);
    svg.style.maxWidth = "none";
    svg.setAttribute("width", w);
    svg.setAttribute("height", h);
  });
  const out = join(DIAGRAMS, basename(file, ".mmd") + ".png");
  // Screenshot the wrapper, not the svg: mermaid caps the svg's CSS width,
  // so its bounding box reports 300px however large the diagram really is.
  const buf = await page.locator("#d").screenshot({ path: out });
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  console.log(`  ok   ${basename(file, ".mmd").padEnd(14)} ${w}x${h} px${errs.length ? "  errors=" + errs.join("|") : ""}`);
  await page.close();
}
await browser.close();
server.close();
process.exit(failed ? 1 : 0);
