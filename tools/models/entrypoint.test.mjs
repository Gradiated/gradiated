import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("bundle entrypoint uses its own Python and only the assigned GPUs", (t) => {
  const root = mkdtempSync(join(tmpdir(), "runtime-entrypoint-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, "python/bin"), { recursive: true });
  for (const file of ["entrypoint", "vllm"]) {
    cpSync(
      `product/inference/bundles/deepseek-v4-1-flash/${file}`,
      join(root, file),
    );
  }
  cpSync(
    "product/inference/images/deepseek-v4-1-flash/start.sh",
    join(root, "start.sh"),
  );
  writeFileSync(
    join(root, "python/bin/python3"),
    `#!/usr/bin/env node
console.log(JSON.stringify({ args: process.argv.slice(2), gpus: process.env.CUDA_VISIBLE_DEVICES }));
`,
    { mode: 0o755 },
  );
  execFileSync("chmod", ["755", join(root, "vllm")]);
  const assigned = "GPU-a,GPU-b,GPU-c,GPU-d";
  const result = JSON.parse(
    execFileSync("bash", [join(root, "entrypoint")], {
      encoding: "utf8",
      env: {
        ...process.env,
        GRADIATED_RUNTIME_ROOT: root,
        NVIDIA_VISIBLE_DEVICES: assigned,
      },
    }),
  );
  assert.equal(result.gpus, assigned);
  assert.deepEqual(result.args.slice(0, 3), [
    "-m",
    "vllm.entrypoints.cli.main",
    "serve",
  ]);
  assert.equal(
    result.args[result.args.indexOf("--tensor-parallel-size") + 1],
    "4",
  );
});
