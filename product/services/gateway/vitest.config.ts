import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/integration/**/*.test.ts"],
    globalSetup: ["test/integration/global-setup.ts"],
    testTimeout: 30_000,
    hookTimeout: 60_000,
    teardownTimeout: 30_000,
    // The shared gateway and Valkey are safe to share: every case has its own
    // tenant, model and runtime, and settlement reads filter by organization.
    fileParallelism: true,
  },
});
