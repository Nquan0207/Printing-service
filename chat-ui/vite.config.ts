import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxies to the Python chat service so the browser sees one origin: the
// session cookie is host-only, and /media paths in tool results are relative.
// `/api/chat` streams Server-Sent Events, so buffering must stay off.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "/api": { target: "http://127.0.0.1:3002", changeOrigin: false },
      "/media": { target: "http://127.0.0.1:3002", changeOrigin: false },
      "/healthz": { target: "http://127.0.0.1:3002", changeOrigin: false },
    },
  },
});
