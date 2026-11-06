import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
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

const require = createRequire(import.meta.url);
const {
  readReferences,
  referenceFileFor,
  articleCitationsPlugin,
  remarkArticleCitations,
} = require("./scripts/article-citations.cjs") as {
  readReferences(path: string): Record<string, unknown>;
  referenceFileFor(path: string): string;
  articleCitationsPlugin(): Plugin;
  remarkArticleCitations: () => (
    tree: unknown,
    file: { path?: string },
  ) => void;
};
const { renderPost } = require("./scripts/sand-renderer.cjs") as {
  renderPost(
    source: string,
    template: string,
    scenes: string[],
    publication: { publishedThrough: string; footer: string } | undefined,
    sources: Record<string, unknown>,
  ): string;
};

const mdxPlugin = mdx({
  remarkPlugins: [remarkFrontmatter, remarkGfm, remarkArticleCitations],
  rehypePlugins: [[rehypeHighlight, { detect: false, languages: all }]],
});

/* Job postings come only from Ashby, synced into src/ashby-jobs.generated.ts.
   `pnpm build` syncs before building; the dev server does it on start, so a
   fresh checkout's careers page is not empty. Offline, or after 10 seconds, it
   carries on with the generated file as it is. */
const syncAshbyJobs: Plugin = {
  name: "sync-ashby-jobs",
  apply: "serve",
  buildStart() {
    const result = spawnSync(
      process.execPath,
      [fileURLToPath(new URL("./scripts/sync-ashby-jobs.ts", import.meta.url))],
      {
        env: { ...process.env, ASHBY_SYNC_OPTIONAL: "1" },
        stdio: "inherit",
        // A stalled connection to Ashby must not hold up the dev server.
        timeout: 10_000,
      },
    );
    if (result.error) {
      console.warn(
        `Ashby job sync did not finish (${result.error.message}); starting with src/ashby-jobs.generated.ts as it is.`,
      );
    }
  },
};

export default defineConfig(({ command, isSsrBuild, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const apiProxyUrl =
    process.env.WEBSITE_API_PROXY_URL ?? "http://127.0.0.1:3001";
  const consoleOrigin = new URL(
    env.VITE_CONSOLE_BASE_URL || "http://localhost:3000",
  ).origin;
  if (
    process.env.VERCEL_ENV === "production" &&
    !env.VITE_POSTHOG_KEY?.trim()
  ) {
    throw new Error(
      "VITE_POSTHOG_KEY must be set in Vercel's Production environment.",
    );
  }

  return {
    define: {
      "import.meta.env.PREVIEW": JSON.stringify(
        process.env.VERCEL_ENV === "preview",
      ),
    },
    plugins: [
      syncAshbyJobs,
      articleCitationsPlugin(),
      {
        name: "sand-article",
        enforce: "pre",
        load(id) {
          if (!id.endsWith(".md?sand-article")) return;

          const file = id.slice(0, -"?sand-article".length);
          const manifest = join(dirname(file), "scenes.json");
          this.addWatchFile(file);
          this.addWatchFile(manifest);
          const publicationFile = join(dirname(file), "publication.json");
          this.addWatchFile(publicationFile);
          const source = readFileSync(file, "utf8");
          const scenes = JSON.parse(readFileSync(manifest, "utf8"));
          const template = "<!--{{TITLE}}-->{{ARTICLE}}";
          const references = referenceFileFor(file);
          if (existsSync(references)) this.addWatchFile(references);
          const sources = readReferences(file);
          const complete = renderPost(
            source,
            template,
            scenes,
            undefined,
            sources,
          );
          const html =
            command === "serve" || process.env.VERCEL_ENV === "preview"
              ? complete
              : renderPost(
                  source,
                  template,
                  scenes,
                  JSON.parse(readFileSync(publicationFile, "utf8")),
                  sources,
                );
          const contents = Array.from(
            html.matchAll(
              /<section[^>]* id="([^"]+)">\s*<h2>([\s\S]*?)<\/h2>/g,
            ),
            ([, id, heading]) => ({
              id,
              label: heading.replace(/<[^>]*>/g, "").replace(
                /&(amp|lt|gt|quot|#39);/g,
                (entity) =>
                  ({
                    "&amp;": "&",
                    "&lt;": "<",
                    "&gt;": ">",
                    "&quot;": '"',
                    "&#39;": "'",
                  })[entity]!,
              ),
            }),
          );

          return `export const contents = ${JSON.stringify(contents)}; export default ${JSON.stringify(html)};`;
        },
      },
      {
        ...mdxPlugin,
        transform(code, id) {
          // MDX strips query strings before filtering, so bypass custom source loaders.
          if (
            id.includes("?raw") ||
            id.includes("?sand-article") ||
            id.includes("?fabrication-article")
          )
            return;
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
          headers: { origin: consoleOrigin },
          target: apiProxyUrl,
        },
        "/health": apiProxyUrl,
      },
    },
    build: {
      emptyOutDir: !isSsrBuild,
    },
  };
});
