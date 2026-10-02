import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  chmodSync,
  rmSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("tools/deployment/commit-release.sh");
const metadata =
  "infra/environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml";
const fixture = (t) => {
  const root = mkdtempSync(path.join(os.tmpdir(), "release-push-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const remote = path.join(root, "origin.git");
  const checkout = path.join(root, "checkout");
  const git = (cwd, ...args) =>
    execFileSync("git", args, { cwd, encoding: "utf8", stdio: "pipe" }).trim();
  git(root, "init", "--bare", "--initial-branch=main", remote);
  git(root, "clone", remote, checkout);
  git(checkout, "config", "user.name", "Fixture");
  git(checkout, "config", "user.email", "fixture@example.invalid");
  const files = readFileSync(script, "utf8")
    .match(/  infra\/[^\n]+/g)
    .map((line) => line.trim());
  for (const file of [...files, "tools/deployment/release-order.mjs"]) {
    mkdirSync(path.dirname(path.join(checkout, file)), { recursive: true });
    copyFileSync(file, path.join(checkout, file));
  }
  writeFileSync(
    path.join(checkout, metadata),
    'data:\n  sourceRevision: "unreleased"\n',
  );
  git(checkout, "add", ".");
  git(checkout, "commit", "-m", "Source passed CI");
  git(checkout, "push", "origin", "main");
  const source = git(checkout, "rev-parse", "HEAD");
  const run = () =>
    spawnSync("bash", [script], {
      cwd: checkout,
      encoding: "utf8",
      env: { ...process.env, SOURCE_SHA: source },
    });
  const change = () =>
    writeFileSync(
      path.join(checkout, metadata),
      `data:\n  sourceRevision: "${source}"\n`,
    );
  const writer = () => {
    const directory = path.join(root, "writer");
    git(root, "clone", remote, directory);
    git(directory, "config", "user.name", "Other writer");
    git(directory, "config", "user.email", "other@example.invalid");
    return directory;
  };
  return { root, remote, checkout, git, source, run, change, writer };
};

test("records a release directly on main and prevents a recursive CI cycle", (t) => {
  const f = fixture(t);
  f.change();
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  const head = f.git(f.checkout, "rev-parse", "HEAD");
  assert.equal(f.git(f.root, "--git-dir", f.remote, "rev-parse", "main"), head);
  assert.match(
    f.git(f.checkout, "log", "-1", "--format=%s"),
    /^deploy\(prod\): release [a-f0-9]{12} \[skip ci\]$/,
  );
  assert.equal(
    f.git(f.checkout, "diff", "--name-only", "HEAD^", "HEAD"),
    metadata,
  );
  assert.equal(
    f.git(f.root, "--git-dir", f.remote, "branch", "--format=%(refname:short)"),
    "main",
  );
});

test("rebases the release over concurrent source changes without dropping them", (t) => {
  const f = fixture(t);
  f.change();
  const writer = f.writer();
  writeFileSync(path.join(writer, "source.txt"), "concurrent source change\n");
  f.git(writer, "add", ".");
  f.git(writer, "commit", "-m", "Concurrent source change");
  const concurrent = f.git(writer, "rev-parse", "HEAD");
  f.git(writer, "push", "origin", "main");
  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    readFileSync(path.join(f.checkout, "source.txt"), "utf8"),
    "concurrent source change\n",
  );
  assert.equal(f.git(f.checkout, "rev-parse", "HEAD^"), concurrent);
});

test("refuses to overwrite a newer release that was recorded while building", (t) => {
  const f = fixture(t);
  f.change();
  const writer = f.writer();
  writeFileSync(path.join(writer, "source.txt"), "newer source\n");
  f.git(writer, "add", ".");
  f.git(writer, "commit", "-m", "Newer source");
  const newer = f.git(writer, "rev-parse", "HEAD");
  writeFileSync(
    path.join(writer, metadata),
    `data:\n  sourceRevision: "${newer}"\n`,
  );
  f.git(writer, "add", ".");
  f.git(writer, "commit", "-m", "Newer release");
  const release = f.git(writer, "rev-parse", "HEAD");
  f.git(writer, "push", "origin", "main");
  const result = f.run();
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /newer release was recorded/);
  assert.equal(
    f.git(f.root, "--git-dir", f.remote, "rev-parse", "main"),
    release,
  );
});

test("rejects pre-staged unrelated changes and makes matching releases a no-op", (t) => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  assert.equal(f.git(f.checkout, "rev-parse", "HEAD"), f.source);
  f.change();
  writeFileSync(path.join(f.checkout, "unrelated.txt"), "must not publish\n");
  f.git(f.checkout, "add", "unrelated.txt");
  const result = f.run();
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /already has staged changes/);
  assert.equal(
    f.git(f.root, "--git-dir", f.remote, "rev-parse", "main"),
    f.source,
  );
});

test("retries a rejected push without creating another release commit", (t) => {
  const f = fixture(t);
  f.change();
  const hook = path.join(f.remote, "hooks", "pre-receive");
  writeFileSync(
    hook,
    `#!/bin/bash
marker="$(dirname "$0")/rejected-once"
if [[ ! -f "$marker" ]]; then
  touch "$marker"
  exit 1
fi
`,
  );
  chmodSync(hook, 0o755);

  const result = f.run();
  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    f.git(f.checkout, "rev-list", "--count", `${f.source}..HEAD`),
    "1",
  );
  assert.equal(
    f.git(f.root, "--git-dir", f.remote, "rev-parse", "main"),
    f.git(f.checkout, "rev-parse", "HEAD"),
  );
});
