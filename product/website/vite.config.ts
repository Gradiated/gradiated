import mdx from "@mdx-js/rollup";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import remarkGfm from "remark-gfm";
import remarkFrontmatter from "remark-frontmatter";
import rehypeHighlight from "rehype-highlight";
import { all } from "lowlight";

const mdxPlugin = mdx({
  remarkPlugins: [remarkFrontmatter, remarkGfm],
  rehypePlugins: [[rehypeHighlight, { detect: false, languages: all }]],
});

export default defineConfig(({ isSsrBuild }) => ({
  plugins: [
    {
      ...mdxPlugin,
      transform(code, id) {
        // MDX strips query strings before filtering. Leave raw source imports to Vite.
        if (id.includes("?raw")) return;
        if (typeof mdxPlugin.transform === "function") {
          return mdxPlugin.transform.call(this, code, id);
        }
      },
      enforce: "pre",
    },
    react({ include: /\.(jsx|js|tsx|ts|mdx)$/ }),
    tailwindcss(),
  ],
  server: {
    allowedHosts: ["gradiated-dev.test"],
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
