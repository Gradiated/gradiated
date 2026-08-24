import mdx from "@mdx-js/rollup";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import remarkGfm from "remark-gfm";

export default defineConfig({
  plugins: [
    { ...mdx({ remarkPlugins: [remarkGfm] }), enforce: "pre" },
    react({ include: /\.(jsx|js|tsx|ts|mdx)$/ }),
    tailwindcss(),
  ],
});
