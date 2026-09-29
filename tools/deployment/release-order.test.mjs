import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { releaseOrder } from "./release-order.mjs";

const fixture = (t) => {
  const root = mkdtempSync(path.join(os.tmpdir(), "release-order-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const git = (...args) =>
    execFileSync("git", args, {
      cwd: root,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  git("init", "-b", "main");
  git("config", "user.name", "Release test");
  git("config", "user.email", "release@example.invalid");
  const file = path.join(
    root,
    "infra/environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml",
  );
  mkdirSync(path.dirname(file), { recursive: true });
  const commit = (label) => {
    git("add", ".");
    git("commit", "--allow-empty", "-m", label);
    git("update-ref", "refs/remotes/origin/main", "HEAD");

    return git("rev-parse", "HEAD");
  };
  const record = (source) => {
    writeFileSync(file, `data:\n  sourceRevision: "${source}"\n`);
    return commit("release " + source);
  };
  const first = record("unreleased");
  record(first);
  const second = commit("new source");

  return { root, git, commit, record, first, second };
};

test("a delayed old workflow skips while current and newer sources can deploy", (t) => {
  const { root, first, second, record } = fixture(t);
  assert.equal(releaseOrder(first, root).deploy, true);
  assert.equal(releaseOrder(second, root).deploy, true);
  record(second);
  assert.equal(releaseOrder(first, root).deploy, false);
  assert.equal(releaseOrder(second, root).deploy, true);
});

test("an unmerged source cannot deploy", (t) => {
  const { root, git, first, second } = fixture(t);
  git("checkout", "-b", "unmerged", first);
  git("commit", "--allow-empty", "-m", "unmerged change");
  const branch = git("rev-parse", "HEAD");
  git("update-ref", "refs/remotes/origin/main", second);
  assert.throws(() => releaseOrder(branch, root), /not on main/);
});

test("a Git revert is a newer source and can roll back code", (t) => {
  const { root, second, record, commit } = fixture(t);
  record(second);
  const reverted = commit("revert source change");
  assert.equal(releaseOrder(reverted, root).deploy, true);
});

test("invalid release history fails closed", (t) => {
  const { root, second, record } = fixture(t);
  record("invalid");
  assert.throws(() => releaseOrder(second, root), /Invalid recorded/);
  assert.throws(() => releaseOrder("not-a-sha", root), /Invalid source/);
});
