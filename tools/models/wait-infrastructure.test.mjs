import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  infrastructureRevision,
  waitForTerraform,
} from "./wait-infrastructure.mjs";

test("a superseding model-only commit retains its infrastructure prerequisite", () => {
  const cwd = mkdtempSync(join(tmpdir(), "infrastructure-gate-"));
  const git = (...args) =>
    execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  const commit = (path, content) => {
    mkdirSync(join(cwd, path, ".."), { recursive: true });
    writeFileSync(join(cwd, path), content);
    git("add", path);
    git(
      "-c",
      "user.name=Test",
      "-c",
      "user.email=test@example.invalid",
      "commit",
      "-m",
      path,
    );
    return git("rev-parse", "HEAD");
  };

  try {
    git("init");
    const infrastructure = commit("infra/modules/example/main.tf", "first");
    const model = commit("product/inference/model", "first");
    const successor = commit("product/inference/model", "second");
    assert.equal(infrastructureRevision(model, cwd), infrastructure);
    assert.equal(infrastructureRevision(successor, cwd), infrastructure);

    const later = commit("tools/terraform/apply.sh", "second");
    assert.equal(infrastructureRevision(later, cwd), later);
    assert.equal(infrastructureRevision(successor, cwd), infrastructure);
  } finally {
    rmSync(cwd, { recursive: true, force: true });
  }
});

test("waits for a prerequisite still applying and ignores unrelated successful runs", async () => {
  let calls = 0;
  let waits = 0;
  await waitForTerraform("prerequisite", {
    fetchRuns: async (revision) => {
      assert.equal(revision, "prerequisite");
      calls++;
      return [
        {
          id: 10,
          head_sha: "other",
          status: "completed",
          conclusion: "success",
        },
        {
          id: 1,
          head_sha: revision,
          status: calls < 3 ? "in_progress" : "completed",
          conclusion: "success",
        },
      ];
    },
    wait: async () => {
      waits++;
    },
  });
  assert.equal(waits, 2);
});

for (const conclusion of ["failure", "cancelled", "skipped"]) {
  test(`a ${conclusion} prerequisite blocks deployment`, async () => {
    await assert.rejects(
      waitForTerraform("required", {
        fetchRuns: async () => [
          { id: 1, head_sha: "required", status: "completed", conclusion },
        ],
      }),
      /Terraform did not succeed/,
    );
  });
}

test("a missing prerequisite run has a bounded wait", async () => {
  let now = 0;
  await assert.rejects(
    waitForTerraform("missing", {
      fetchRuns: async () => [],
      now: () => now,
      wait: async () => {
        now += 90 * 60 * 1000;
      },
    }),
    /within 90 minutes/,
  );
});
