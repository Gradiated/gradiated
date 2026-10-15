import { defineConfig, devices } from "@playwright/test";

const consolePort = process.env.PLAYWRIGHT_CONSOLE_PORT ?? "3000";
const apiPort = process.env.PLAYWRIGHT_API_PORT ?? "3001";
const metricsPort = process.env.PLAYWRIGHT_METRICS_PORT ?? "9464";
const consoleUrl = `http://127.0.0.1:${consolePort}`;
const apiUrl = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  testDir: "./e2e",
  testIgnore: [
    "task-ui.spec.ts",
    "settings-ui.spec.ts",
    "onboarding-ui.spec.ts",
    "members-ui.spec.ts",
  ],
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: consoleUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "pnpm --filter @gradiated/api dev",
      url: `${apiUrl}/health/ready`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        CLICKHOUSE_DATABASE: "gradiated",
        CLICKHOUSE_HOST: "127.0.0.1",
        CLICKHOUSE_PASSWORD: "gradiated",
        CLICKHOUSE_PORT: "8123",
        CLICKHOUSE_SECURE: "false",
        CLICKHOUSE_USERNAME: "gradiated",
        DATABASE_URL:
          process.env.DATABASE_URL ??
          "postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated",
        VALKEY_URL: "redis://127.0.0.1:6379",
        AUTH_TEST_MODE: "true",
        BETTER_AUTH_URL: consoleUrl,
        BETTER_AUTH_SECRET: "local-only-not-secret-change-in-production-0001",
        PORT: apiPort,
        TRUSTED_ORIGINS: consoleUrl,
        NODE_ENV: "test",
        METRICS_PORT: metricsPort,
      },
    },
    {
      command: `pnpm dev --port ${consolePort}`,
      url: `${consoleUrl}/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        CONSOLE_API_PROXY_URL: apiUrl,
      },
    },
  ],
});
