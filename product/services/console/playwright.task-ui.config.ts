import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "task-ui.spec.ts",
  outputDir: "../../../.agents/runtime/task-ui-browser-output",
  use: { baseURL: "http://127.0.0.1:3017", headless: true },
  webServer: {
    command: "pnpm dev --port 3017 --force",
    url: "http://127.0.0.1:3017",
    reuseExistingServer: false,
    env: {
      VITE_POSTHOG_KEY: "local-test-key",
      VITE_POSTHOG_HOST: "http://127.0.0.1:3017",
      VITE_FEATURE_FLAGS: "",
    },
  },
});
