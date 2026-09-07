import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// The host renders this View in a sandboxed iframe under a deny-by-default
// CSP, so every asset must end up inline in one HTML file.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: "dist",
    // The plugin's recommended config turns this off, which makes vite inject
    // the stylesheet from JavaScript at runtime. A real <style> tag needs no
    // script to have run first, so keep it on and let the plugin inline the
    // emitted stylesheet instead.
    cssCodeSplit: true,
    rollupOptions: { input: "storefront.html" },
  },
});
