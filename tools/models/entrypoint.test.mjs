import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("Kev entrypoint serves the adapter on its assigned GPU and loopback port", (t) => {
  const root = mkdtempSync(join(tmpdir(), "kev-entrypoint-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, "python/bin"), { recursive: true });
  cpSync(
    "product/inference/bundles/kev-9b/entrypoint",
    join(root, "entrypoint"),
  );
  writeFileSync(
    join(root, "python/bin/python3"),
    `#!/usr/bin/env node
console.log(JSON.stringify({ args: process.argv.slice(2), gpus: process.env.CUDA_VISIBLE_DEVICES }));
`,
    { mode: 0o755 },
  );
  const result = JSON.parse(
    execFileSync("bash", [join(root, "entrypoint")], {
      encoding: "utf8",
      env: {
        ...process.env,
        GRADIATED_RUNTIME_ROOT: root,
        NVIDIA_VISIBLE_DEVICES: "GPU-a",
        RUNTIME_PORT: "23456",
      },
    }),
  );
  assert.equal(result.gpus, "GPU-a");
  assert.deepEqual(result.args, [
    join(root, "adapter.py"),
    "--host",
    "127.0.0.1",
    "--port",
    "23456",
  ]);
});
