import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import mdx from "@mdx-js/rollup";
import { defineConfig, loadEnv } from "vite";
import type { Plugin } from "vite";
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

/* Job postings come only from Ashby, synced into src/ashby-jobs.generated.ts.
   `pnpm build` syncs before building; the dev server does it on start, so a
   fresh checkout's careers page is not empty. Offline, it carries on with the
   generated file as it is. */
const syncAshbyJobs: Plugin = {
  name: "sync-ashby-jobs",
  apply: "serve",
  buildStart() {
    spawnSync(
      process.execPath,
      [fileURLToPath(new URL("./scripts/sync-ashby-jobs.ts", import.meta.url))],
      { env: { ...process.env, ASHBY_SYNC_OPTIONAL: "1" }, stdio: "inherit" },
    );
  },
};

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
      syncAshbyJobs,
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
  };
});
