import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// The host renders Views in a sandboxed iframe with a deny-by-default CSP, so
// every asset must be inlined into one HTML file. The Python server reads the
// built file from dist/ and serves it as a ui:// resource.
export default defineConfig({
  plugins: [viteSingleFile()],
  build: { outDir: "dist", rollupOptions: { input: "dashboard.html" } },
});
