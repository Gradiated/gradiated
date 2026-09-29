import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import test from "node:test";
import { assertReleaseSource } from "./release-source.mjs";

const fixture = (t) => {
  const root = mkdtempSync(join(tmpdir(), "nomad-source-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const git = (...args) =>
    execFileSync("git", args, {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  git("init", "-b", "main");
  git("config", "user.name", "Test");
  git("config", "user.email", "test@example.invalid");
  const commit = (file, value) => {
    mkdirSync(dirname(join(root, file)), { recursive: true });
    writeFileSync(join(root, file), value);
    git("add", ".");
    git("commit", "-m", "change");
    git("update-ref", "refs/remotes/origin/main", "HEAD");
    return git("rev-parse", "HEAD");
  };
  return { root, git, commit };
};

for (const file of [
  "product/inference/nomad/jobs/kev-9b.vars.hcl",
  "product/inference/nomad/client.hcl",
  "product/inference/runtimes/kev/adapter.py",
  "tools/models/release.mjs",
]) {
  test(`a stale workflow cannot overwrite ${file}`, (t) => {
    const { root, commit } = fixture(t);
    const old = commit(file, "before");
    const current = commit(file, "after");
    assert.throws(() => assertReleaseSource(old, root), /stale rollout/);
    assertReleaseSource(current, root);
    const revert = commit(file, "before");
    assertReleaseSource(revert, root);
  });
}

test("unrelated changes do not invalidate the deployment source", (t) => {
  const { root, commit } = fixture(t);
  const source = commit(
    "product/inference/nomad/jobs/kev-9b.vars.hcl",
    "replicas=2",
  );
  commit("docs/unrelated.md", "documentation");
  assertReleaseSource(source, root);
});

test("unmerged and invalid sources fail closed", (t) => {
  const { root, git, commit } = fixture(t);
  const main = commit("README.md", "main");
  git("checkout", "-b", "unmerged");
  const source = commit("README.md", "branch");
  git("update-ref", "refs/remotes/origin/main", main);
  assert.throws(() => assertReleaseSource(source, root), /ancestor/);
  assert.throws(() => assertReleaseSource("invalid", root), /Invalid source/);
});
