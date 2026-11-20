import assert from "node:assert/strict";
import test from "node:test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parentRevision, trustedRun, validateMetadata } from "./verified.mjs";
test("only a successful CI workflow from the same repository qualifies an artifact", () => {
  const run = {
    status: "completed",
    conclusion: "success",
    event: "pull_request",
    path: ".github/workflows/tests.yml",
    head_repository: { full_name: "owner/repo" },
  };
  assert.equal(trustedRun(run, "owner/repo"), true);
  for (const override of [
    { conclusion: "failure" },
    { status: "in_progress" },
    { event: "push" },
    { path: ".github/workflows/other.yml" },
    { head_repository: { full_name: "fork/repo" } },
  ])
    assert.equal(trustedRun({ ...run, ...override }, "owner/repo"), false);
});
test("input identity and archive integrity must both match", () => {
  const image = { name: "product", tag: "inputs" };
  const record = {
    schema: 1,
    name: "product",
    tag: "inputs",
    verificationKey: "policy",
    archiveSha256: "archive",
  };
  assert.doesNotThrow(() =>
    validateMetadata(record, image, "policy", "archive"),
  );
  assert.throws(() =>
    validateMetadata(record, image, "different-policy", "archive"),
  );
  assert.throws(() =>
    validateMetadata(record, image, "policy", "different-bytes"),
  );
  assert.throws(() =>
    validateMetadata(
      { ...record, name: "gateway" },
      image,
      "policy",
      "archive",
    ),
  );
});

test("the parent revision is a full SHA that plan() accepts", () => {
  // A throwaway repository, so the test works in shallow CI checkouts.
  const directory = mkdtempSync(join(tmpdir(), "parent-revision-"));
  const git = (...args) =>
    execFileSync("git", ["-C", directory, ...args], {
      encoding: "utf8",
    }).trim();
  try {
    git("init", "-q");
    for (const message of ["first", "second"])
      git(
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        message,
      );
    const head = git("rev-parse", "HEAD");
    const parent = parentRevision(head, directory);
    assert.match(parent, /^[0-9a-f]{40}$/);
    assert.equal(parent, git("rev-parse", "HEAD^"));
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
