import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import mdx from "@mdx-js/rollup";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import remarkGfm from "remark-gfm";
import remarkFrontmatter from "remark-frontmatter";
import rehypeHighlight from "rehype-highlight";
import { all } from "lowlight";

const require = createRequire(import.meta.url);
const { renderPost } = require("./scripts/sand-renderer.cjs") as {
  renderPost(source: string, template: string, scenes: string[]): string;
};

const mdxPlugin = mdx({
  remarkPlugins: [remarkFrontmatter, remarkGfm],
  rehypePlugins: [[rehypeHighlight, { detect: false, languages: all }]],
});

export default defineConfig(({ isSsrBuild, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  if (
    process.env.VERCEL_ENV === "production" &&
    !env.VITE_POSTHOG_KEY?.trim()
  ) {
    throw new Error(
      "VITE_POSTHOG_KEY must be set in Vercel's Production environment.",
    );
  }

  return {
    plugins: [
      {
        name: "sand-article",
        enforce: "pre",
        load(id) {
          if (!id.endsWith(".md?sand-article")) return;

          const file = id.slice(0, -"?sand-article".length);
          const manifest = join(dirname(file), "scenes.json");
          this.addWatchFile(file);
          this.addWatchFile(manifest);
          const html = renderPost(
            readFileSync(file, "utf8"),
            "<!--{{TITLE}}-->{{ARTICLE}}",
            JSON.parse(readFileSync(manifest, "utf8")),
          );
          return `export default ${JSON.stringify(html)};`;
        },
      },
      {
        ...mdxPlugin,
        transform(code, id) {
          // MDX strips query strings before filtering, so bypass custom source loaders.
          if (id.includes("?raw") || id.includes("?sand-article")) return;
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
  };
});
