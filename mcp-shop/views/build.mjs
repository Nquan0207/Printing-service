import { rmSync } from "node:fs";
import { build } from "vite";

// vite-plugin-singlefile sets `inlineDynamicImports`, which rollup rejects
// alongside multiple inputs -- so each View gets its own build rather than one
// build with three entries.
const VIEWS = ["storefront", "orders", "cart"];

rmSync("dist", { recursive: true, force: true });
for (const name of VIEWS) {
  process.env.INPUT = `${name}.html`;
  await build();
}
console.log(`built ${VIEWS.length} views`);
