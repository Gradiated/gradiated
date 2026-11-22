import { defineConfig } from "vitest/config";
import { createRequire } from "node:module";
import type { Plugin } from "vite";

const { articleCitationsPlugin } = createRequire(import.meta.url)(
  "../scripts/article-citations.cjs",
) as { articleCitationsPlugin(): Plugin };

export default defineConfig({
  root: import.meta.dirname,
  resolve: { dedupe: ["react", "react-dom", "gsap", "lucide-react"] },
  plugins: [articleCitationsPlugin()],
  test: { include: ["*.test.{ts,mjs}"] },
});
