import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// The host renders Views in a sandboxed iframe with a deny-by-default CSP, so
// every asset must be inlined into one HTML file. vite-plugin-singlefile sets
// `inlineDynamicImports`, which rollup rejects alongside multiple inputs --
// hence one build per View, driven by build.mjs.
export default defineConfig({
  plugins: [viteSingleFile()],
  build: {
    outDir: "dist",
    emptyOutDir: false,
    rollupOptions: { input: process.env.INPUT ?? "dashboard.html" },
  },
});
