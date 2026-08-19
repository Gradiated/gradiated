import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "pnpm --filter @gradiated/api dev",
      url: "http://127.0.0.1:3001/health/ready",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        DATABASE_URL:
          "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated",
        VALKEY_URL: "redis://127.0.0.1:6379",
        AUTH_TEST_MODE: "true",
        BETTER_AUTH_URL: "http://localhost:3000",
        BETTER_AUTH_SECRET: "local-only-not-secret-change-in-production-0001",
        PORT: "3001",
        TRUSTED_ORIGINS: "http://localhost:3000,http://127.0.0.1:3000",
        NODE_ENV: "test",
      },
    },
    {
      command: "pnpm dev",
      url: "http://127.0.0.1:3000/login",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
