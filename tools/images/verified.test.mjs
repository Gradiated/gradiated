import assert from "node:assert/strict";
import test from "node:test";
import { trustedRun, validateMetadata } from "./verified.mjs";
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
