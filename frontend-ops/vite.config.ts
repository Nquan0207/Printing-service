import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies to the Go API so the browser sees one origin --
// no CORS, and /media image paths from the API resolve unchanged.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
      "/media": { target: "http://127.0.0.1:8080", changeOrigin: true },
    },
  },
});
