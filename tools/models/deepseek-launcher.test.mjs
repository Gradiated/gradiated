import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("DeepSeek launcher processes bundled package paths and preserves CLI arguments", () => {
  const root = mkdtempSync(path.join(os.tmpdir(), "deepseek-launcher-"));
  try {
    const packages = path.join(root, "python/lib/python3.12/site-packages");
    mkdirSync(path.join(root, "python/bin"), { recursive: true });
    mkdirSync(path.join(packages, "vllm/entrypoints/cli"), { recursive: true });
    mkdirSync(path.join(packages, "dsl-packages"));
    const python = execFileSync(
      "python3",
      ["-c", "import sys; print(sys.executable)"],
      { encoding: "utf8" },
    ).trim();
    symlinkSync(python, path.join(root, "python/bin/python3"));
    writeFileSync(
      path.join(packages, "dsl-packages/cutlass_fixture.py"),
      "ready = True\n",
    );
    writeFileSync(path.join(packages, "cutlass.pth"), "dsl-packages\n");
    writeFileSync(
      path.join(packages, "vllm/entrypoints/cli/main.py"),
      "import cutlass_fixture, json, sys\nassert cutlass_fixture.ready\nprint(json.dumps(sys.argv[1:]))\n",
    );
    const args = [
      "serve",
      "deepseek-ai/DeepSeek-V4.1-Flash",
      "--tensor-parallel-size",
      "4",
    ];
    const launcher = fileURLToPath(
      new URL(
        "../../product/inference/bundles/deepseek-v4-1-flash/vllm",
        import.meta.url,
      ),
    );
    const { PYTHONHOME, ...environment } = process.env;
    const result = spawnSync("bash", [launcher, ...args], {
      env: {
        ...environment,
        GRADIATED_RUNTIME_ROOT: root,
        PYTHONPATH: packages,
      },
      encoding: "utf8",
      timeout: 10_000,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(result.stdout), args);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
