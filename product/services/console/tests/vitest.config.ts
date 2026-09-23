import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "../vite.config.ts";

export default mergeConfig(
  viteConfig,
  defineConfig({
    root: import.meta.dirname,
    test: { include: ["*.test.ts"] },
  }),
);
