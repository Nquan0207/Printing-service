import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// The host renders Views in a sandboxed iframe under a deny-by-default CSP, so
// every asset must be inlined into one HTML file. vite-plugin-singlefile sets
// `inlineDynamicImports`, which rollup rejects alongside multiple inputs --
// hence one build per View, driven by build.mjs.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: "dist",
    emptyOutDir: false,
    // The plugin's recommended config turns this off, which makes vite inject
    // the stylesheet from JavaScript at runtime. A real <style> tag needs no
    // script to have run first, so keep it on.
    cssCodeSplit: true,
    rollupOptions: { input: process.env.INPUT ?? "dashboard.html" },
  },
});
