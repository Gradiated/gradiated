import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  server: {
    allowedHosts: ["gradiated-dev.test"],
    port: 3000,
    strictPort: true,
    proxy: {
      "/api/": process.env.CONSOLE_API_PROXY_URL ?? "http://127.0.0.1:3001",
      "/health": process.env.CONSOLE_API_PROXY_URL ?? "http://127.0.0.1:3001",
      "/v1/": "http://127.0.0.1:3002",
    },
  },
});
