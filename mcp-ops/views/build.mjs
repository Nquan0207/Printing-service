import { rmSync } from "node:fs";
import { build } from "vite";

const VIEWS = ["dashboard", "orders", "catalog", "product", "users"];

rmSync("dist", { recursive: true, force: true });
for (const name of VIEWS) {
  process.env.INPUT = `${name}.html`;
  await build();
}
console.log(`built ${VIEWS.length} views`);
