import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/integration/**/*.test.ts"],
    globalSetup: [
      "test/support/valkey.ts",
      "test/support/clickhouse.ts",
      "../../packages/control/test/support/postgres.ts",
    ],
    testTimeout: 30_000,
    hookTimeout: 60_000,
    fileParallelism: false,
  },
});
