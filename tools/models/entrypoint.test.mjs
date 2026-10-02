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
  assert.equal(result.args[0], "-c");
  assert.match(result.args[1], /site\.addsitedir/);
  assert.match(result.args[1], /vllm\.entrypoints\.cli\.main/);
  assert.equal(result.args[2], "serve");
  assert.equal(
    result.args[result.args.indexOf("--tensor-parallel-size") + 1],
    "4",
  );
});

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

test("GLM exposes only its assigned pair on a shared GPU host", (t) => {
  const root = mkdtempSync(join(tmpdir(), "glm-entrypoint-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, "python/bin"), { recursive: true });
  cpSync(
    "product/inference/bundles/glm-5-3-flash/entrypoint",
    join(root, "entrypoint"),
  );
  writeFileSync(
    join(root, "python/bin/python3"),
    `#!/usr/bin/env node
console.log(JSON.stringify({ args: process.argv.slice(2), gpus: process.env.CUDA_VISIBLE_DEVICES }));
`,
    { mode: 0o755 },
  );
  const assigned = "GPU-e,GPU-f";
  const result = JSON.parse(
    execFileSync("bash", [join(root, "entrypoint")], {
      encoding: "utf8",
      env: {
        ...process.env,
        GRADIATED_RUNTIME_ROOT: root,
        NVIDIA_VISIBLE_DEVICES: assigned,
        RUNTIME_PORT: "23456",
        WARMUP_PORT: "23457",
      },
    }),
  );
  assert.equal(result.gpus, assigned);
  assert.equal(
    result.args[result.args.indexOf("--tensor-parallel-size") + 1],
    "2",
  );
  assert.equal(result.args[result.args.indexOf("--port") + 1], "23456");
});
