import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/integration/**/*.test.ts"],
    globalSetup: [
      "../gateway/test/integration/global-setup.ts",
      "test/support/s3.ts",
    ],
    testTimeout: 30_000,
    hookTimeout: 60_000,
    teardownTimeout: 30_000,
  },
});
