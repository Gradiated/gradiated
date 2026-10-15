import { defineConfig } from "@playwright/test";

const port = process.env.PLAYWRIGHT_CONSOLE_PORT ?? "3017";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: [
    "task-ui.spec.ts",
    "settings-ui.spec.ts",
    "onboarding-ui.spec.ts",
    "members-ui.spec.ts",
  ],
  outputDir: "../../../.agents/runtime/task-ui-browser-output",
  use: { baseURL, headless: true },
  webServer: {
    command: `pnpm dev --port ${port} --force`,
    url: baseURL,
    reuseExistingServer: false,
    env: {
      VITE_POSTHOG_KEY: "local-test-key",
      VITE_POSTHOG_HOST: baseURL,
      VITE_FEATURE_FLAGS: "",
    },
  },
});
