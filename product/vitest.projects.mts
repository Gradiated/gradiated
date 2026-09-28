import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    projects: [
      "packages/*",
      "services/{api,ops-mcp,wizard,worker}",
      "services/console/tests/vitest.config.ts",
    ],
  },
});
