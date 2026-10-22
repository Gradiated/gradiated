import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    // The PostgreSQL sync test uses the control package's database setup.
    globalSetup: ["../../packages/control/test/support/postgres.ts"],
  },
});
