import mdx from "@mdx-js/rollup";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

export default defineConfig(({ isSsrBuild }) => ({
  plugins: [
    {
      ...mdx({
        remarkPlugins: [remarkGfm],
        rehypePlugins: [[rehypeHighlight, { detect: false }]],
      }),
      enforce: "pre",
    },
    react({ include: /\.(jsx|js|tsx|ts|mdx)$/ }),
    tailwindcss(),
  ],
  server: {
    proxy: {
      "/api/": {
        changeOrigin: true,
        headers: { origin: "http://localhost:3000" },
        target: "http://127.0.0.1:3001",
      },
      "/health": "http://127.0.0.1:3001",
    },
  },
  build: {
    emptyOutDir: !isSsrBuild,
  },
}));
