import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const runtimeUrl = process.env.KEV_RUNTIME_URL ?? "http://127.0.0.1:18009";

const result = spawnSync(
  "pnpm",
  [
    "--filter",
    "@gradiated/gateway",
    "test:integration",
    "test/integration/real-runtime.test.ts",
  ],
  {
    cwd: fileURLToPath(new URL("..", import.meta.url)),
    stdio: "inherit",
    env: {
      ...process.env,
      GATEWAY_REAL_RUNTIME: "kev",
      GATEWAY_REAL_RUNTIME_URL_KEV: runtimeUrl,
      GATEWAY_REAL_KEV_MODEL: "jaredpalmer/kev-9b",
    },
  },
);

if (result.error) console.error(result.error.message);

process.exitCode = result.status ?? 1;
