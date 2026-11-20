import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    // Integration tests read a migrated PostgreSQL through the control package.
    globalSetup: ["../../packages/control/test/support/postgres.ts"],
  },
});
