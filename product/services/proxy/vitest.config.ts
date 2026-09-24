import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/e2e/**/*.test.ts"],
    // The gateway suite's stack: PostgreSQL, Valkey and a real gateway binary.
    globalSetup: ["../gateway/test/integration/global-setup.ts"],
    testTimeout: 30_000,
    hookTimeout: 60_000,
    teardownTimeout: 30_000,
    fileParallelism: true,
  },
});
