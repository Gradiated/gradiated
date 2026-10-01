import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  chmodSync,
  rmSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const run = ({
  event,
  pr = "",
  discovered = "",
  files = "",
  lookupFails = false,
}) => {
  const directory = mkdtempSync(path.join(os.tmpdir(), "release-checks-"));
  try {
    const output = path.join(directory, "output");
    writeFileSync(output, "");
    writeFileSync(
      path.join(directory, "yq"),
      `#!/bin/bash\ncase "$1" in\n  *jobs*) echo verify;;\n  *needs*) echo verify;;\n  *) echo 'infra/**';;\nesac\n`,
    );
    writeFileSync(
      path.join(directory, "gh"),
      `#!/bin/bash\nif [[ "$*" == *'/files'* ]]; then\n  echo "$TEST_FILES"\nelse\n  [[ "$LOOKUP_FAILS" != true ]] || exit 1\n  echo "$DISCOVERED_PR"\nfi\n`,
    );
    for (const name of ["yq", "gh"])
      chmodSync(path.join(directory, name), 0o755);
    const result = spawnSync("bash", [".github/actions/relevant/relevant.sh"], {
      encoding: "utf8",
      env: {
        ...process.env,
        PATH: `${directory}:${process.env.PATH}`,
        EVENT: event,
        PULL_REQUEST: pr,
        BRANCH: "deploy/release-test",
        REPOSITORY: "owner/repo",
        WORKFLOW: "test.yml",
        GITHUB_OUTPUT: output,
        DISCOVERED_PR: discovered,
        TEST_FILES: files,
        LOOKUP_FAILS: String(lookupFails),
      },
    });
    return { status: result.status, output: readFileSync(output, "utf8") };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
};

test("dispatched release checks use the open PR's changed paths", () => {
  assert.equal(
    run({
      event: "workflow_dispatch",
      discovered: "42",
      files: "infra/workloads/api.yaml",
    }).output,
    "relevant=true\n",
  );
  assert.equal(
    run({
      event: "workflow_dispatch",
      discovered: "42",
      files: "docs/README.md",
    }).output,
    "relevant=false\n",
  );
});

test("dispatches without a pull request still run all checks", () => {
  assert.equal(run({ event: "workflow_dispatch" }).output, "relevant=true\n");
});

test("a failed PR lookup fails the check instead of silently skipping", () => {
  const result = run({ event: "workflow_dispatch", lookupFails: true });
  assert.notEqual(result.status, 0);
  assert.equal(result.output, "");
});

test("normal pull requests and main pushes keep their existing filtering", () => {
  assert.equal(
    run({ event: "pull_request", pr: "42", files: "docs/README.md" }).output,
    "relevant=false\n",
  );
  assert.equal(run({ event: "push" }).output, "relevant=true\n");
});
