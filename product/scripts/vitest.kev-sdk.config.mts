import { defineConfig } from "vitest/config";

// The SDK harness targets an already provisioned gateway; it provisions nothing
// itself, so it deliberately has no global setup. The ledger setup file is inert
// unless the E2E launcher sets KEV_E2E_RESPONSE_LEDGER.
export default defineConfig({
  test: {
    include: ["scripts/test-kev-gateway.test.ts"],
    setupFiles: ["scripts/kev-e2e-ledger.ts"],
    testTimeout: 30_000,
  },
});
