import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const website = fileURLToPath(new URL("..", import.meta.url));
const config = JSON.parse(readFileSync(join(website, "vercel.json"), "utf8"));
const git = (root, ...args) => {
  const result = spawnSync(
    "git",
    [
      "-c",
      "core.hooksPath=/dev/null",
      "-c",
      "commit.gpgsign=false",
      "-c",
      "user.name=Build fixture",
      "-c",
      "user.email=fixture@example.invalid",
      ...args,
    ],
    { cwd: root, encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr);
};
const put = (root, path, text) => {
  mkdirSync(dirname(join(root, path)), { recursive: true });
  writeFileSync(join(root, path), text);
};

test("hardware publishing and workspace changes cannot skip a website deployment", () => {
  const root = mkdtempSync(join(tmpdir(), "hardware-build-inputs-"));
  try {
    git(root, "init", "-q");
    put(
      root,
      "product/website/scripts/ashby-jobs-unchanged.ts",
      "process.exit(Number(process.env.TEST_JOBS_EXIT || 0));\n",
    );
    put(root, "README.md", "fixture\n");
    git(root, "add", ".");
    git(root, "commit", "-qm", "fixture base");
    const run = (jobs = 0) =>
      spawnSync("sh", ["-c", config.ignoreCommand], {
        cwd: join(root, "product/website"),
        env: { ...process.env, TEST_JOBS_EXIT: String(jobs) },
        encoding: "utf8",
      });
    for (const path of [
      "hardware/publishing/sand-to-thought/articles/fpga/script.md",
      "hardware/publishing/sand-to-thought/articles/sand/figures/runtime/main.js",
      "hardware/publishing/package.json",
      "product/website/src/main.tsx",
      "product/pnpm-lock.yaml",
      "product/pnpm-workspace.yaml",
      "product/package.json",
    ]) {
      put(
        root,
        path,
        path.endsWith(".json") ? '{"fixture":"changed"}\n' : "changed\n",
      );
      git(root, "add", ".");
      git(root, "commit", "-qm", "fixture change");
      assert.notEqual(run().status, 0, `${path} must build`);
    }
    put(root, "hardware/research/inference/README.md", "research only\n");
    git(root, "add", ".");
    git(root, "commit", "-qm", "unrelated fixture");
    assert.equal(
      run().status,
      0,
      "research-only changes may skip when jobs are unchanged",
    );
    assert.notEqual(run(1).status, 0, "changed jobs must build");
    assert.notEqual(
      run(2).status,
      0,
      "a failed jobs check must not suppress a build",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("hardware edits invalidate the website cache without adding an external workspace", () => {
  const root = mkdtempSync(join(tmpdir(), "hardware-cache-inputs-"));
  try {
    git(root, "init", "-q");
    put(
      root,
      "product/package.json",
      JSON.stringify({
        name: "build-fixture",
        private: true,
        packageManager: "pnpm@10.34.5",
      }),
    );
    put(
      root,
      "product/website/package.json",
      JSON.stringify({
        name: "gradiated-com",
        version: "0.0.0",
        scripts: { build: "echo fixture" },
      }),
    );
    put(
      root,
      "product/pnpm-workspace.yaml",
      readFileSync(join(website, "../pnpm-workspace.yaml"), "utf8"),
    );
    put(
      root,
      "product/turbo.json",
      readFileSync(join(website, "../turbo.json"), "utf8"),
    );
    put(
      root,
      "product/pnpm-lock.yaml",
      "lockfileVersion: '9.0'\nimporters:\n  .: {}\n  website: {}\n",
    );
    put(root, "hardware/publishing/article.md", "original prose\n");
    const binary = createRequire(import.meta.url).resolve("turbo/bin/turbo");
    const inspect = () => {
      const result = spawnSync(
        process.execPath,
        [binary, "run", "build", "--filter=gradiated-com", "--dry=json"],
        {
          cwd: join(root, "product"),
          encoding: "utf8",
          env: {
            ...process.env,
            TURBO_TELEMETRY_DISABLED: "1",
            DO_NOT_TRACK: "1",
          },
        },
      );
      assert.equal(result.status, 0, result.stderr);
      return JSON.parse(result.stdout).tasks.find(
        (task) => task.taskId === "gradiated-com#build",
      );
    };
    const before = inspect();
    assert.ok(before.inputs["../../hardware/publishing/article.md"]);
    put(root, "hardware/publishing/article.md", "changed prose\n");
    assert.notEqual(inspect().hash, before.hash);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
