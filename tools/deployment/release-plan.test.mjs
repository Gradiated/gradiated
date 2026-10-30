import assert from "node:assert/strict";
import test from "node:test";
import {
  releasePlan,
  requireVerifiedPrevious,
  applyDispatch,
  deploymentRuns,
} from "./release-plan.mjs";
const before = "a".repeat(40);
const after = "b".repeat(40);
const metadata = `  sourceRevision: "${before}"\n  consoleRevision: "${before}"`;
test("frontend-only releases keep backend promotion and rollout out of their critical path", () => {
  const result = releasePlan(
    after,
    metadata,
    () => [{ tag: "same" }],
    () => true,
  );
  assert.deepEqual(result, {
    backend: false,
    console: true,
    console_sha: after,
  });
});
test("backend-only releases preserve the actual console revision", () => {
  const result = releasePlan(
    after,
    metadata,
    (sha) => [{ tag: sha }],
    () => false,
  );
  assert.deepEqual(result, {
    backend: true,
    console: false,
    console_sha: before,
  });
});
test("an uninitialized release validates and publishes all components", () => {
  assert.deepEqual(
    releasePlan(
      after,
      "sourceRevision: unreleased",
      () => {
        throw Error("unexpected");
      },
      () => false,
    ),
    { backend: true, console: true, console_sha: after },
  );
});

const jobs = (stage, rollout, publish) => [
  { name: "Stage verified console", conclusion: stage },
  { name: "Wait for Argo rollout", conclusion: rollout },
  { name: "Publish console and verify production", conclusion: publish },
];
test("a failed backend deployment does not require an unchanged console artifact", () => {
  const candidate = { backend: true, console: false, console_sha: before };
  assert.deepEqual(
    requireVerifiedPrevious(
      candidate,
      after,
      false,
      jobs("skipped", "failure", "skipped"),
    ),
    candidate,
  );
});
test("staged but unpublished console is retried after a failed rollout", () => {
  assert.deepEqual(
    requireVerifiedPrevious(
      { backend: false, console: false, console_sha: before },
      after,
      false,
      jobs("success", "failure", "skipped"),
    ),
    { backend: true, console: true, console_sha: after },
  );
});
test("a console publish failure does not repeat a successful backend rollout", () => {
  assert.deepEqual(
    requireVerifiedPrevious(
      { backend: false, console: false, console_sha: before },
      after,
      false,
      jobs("success", "success", "failure"),
    ),
    { backend: false, console: true, console_sha: after },
  );
});
test("verified deployments keep component selection and unknown state fails closed", () => {
  const candidate = { backend: false, console: false, console_sha: before };
  assert.deepEqual(requireVerifiedPrevious(candidate, after, true), candidate);
  assert.throws(
    () => requireVerifiedPrevious(candidate, after, false),
    /Cannot establish/,
  );
});

test("manual publication applies changed public build configuration without a backend rollout", () => {
  const candidate = { backend: false, console: false, console_sha: before };
  assert.deepEqual(applyDispatch(candidate, after, "workflow_dispatch"), {
    backend: false,
    console: true,
    console_sha: after,
  });
  assert.deepEqual(applyDispatch(candidate, after, "push"), candidate);
});

test("manifest-only changes require backend release verification", () => {
  assert.deepEqual(
    releasePlan(
      after,
      metadata,
      () => [{ tag: "same" }],
      () => false,
      () => true,
    ),
    { backend: true, console: false, console_sha: before },
  );
});
test("manifest detection retains source changes and ignores generated release pins", async () => {
  const { execFileSync } = await import("node:child_process");
  const { mkdtemp, mkdir, writeFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const directory = await mkdtemp(`${tmpdir()}/backend-manifests-`);
  const git = (...args) =>
    execFileSync("git", args, { cwd: directory, encoding: "utf8" }).trim();
  const commit = (message) => {
    git("add", ".");
    git(
      "-c",
      "user.name=Test",
      "-c",
      "user.email=test@example.com",
      "commit",
      "-qm",
      message,
    );
    return git("rev-parse", "HEAD");
  };
  const module = new URL("./release-plan.mjs", import.meta.url).href;
  const changed = (base, head) =>
    execFileSync(
      process.execPath,
      [
        "--input-type=module",
        "-e",
        `import {backendManifestChanges} from ${JSON.stringify(module)}; process.stdout.write(String(backendManifestChanges(process.argv[1],process.argv[2])));`,
        base,
        head,
      ],
      { cwd: directory, encoding: "utf8" },
    ) === "true";
  try {
    git("init", "-q");
    const workloads = `${directory}/infra/environments/prod/us-east-1/kubernetes/workloads`;
    await mkdir(workloads, { recursive: true });
    await writeFile(`${workloads}/proxy.yaml`, "replicas: 2\nimage: old\n");
    const base = commit("source");
    await writeFile(`${workloads}/proxy.yaml`, "replicas: 2\nimage: new\n");
    commit(`deploy(prod): release ${base.slice(0, 12)} [skip ci]`);
    await writeFile(`${directory}/console-source`, "frontend");
    const frontend = commit("frontend-only source");
    assert.equal(changed(base, frontend), false);
    await writeFile(`${workloads}/proxy.yaml`, "replicas: 3\nimage: new\n");
    assert.equal(changed(base, commit("change proxy configuration")), true);
    await writeFile(`${workloads}/public-api.yaml`, "service: public-api");
    assert.equal(
      changed(frontend, commit("change public API configuration")),
      true,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("dispatch recovery uses the recorded run even when its ref SHA differs from selected source", async () => {
  const calls = [];
  const run = {
    id: 123,
    head_sha: after,
    path: ".github/workflows/application-deployment.yml",
    event: "workflow_dispatch",
    status: "completed",
    conclusion: "failure",
  };
  assert.deepEqual(
    await deploymentRuns(
      metadata + '\n  deploymentRunId: "123"',
      before,
      async (path) => {
        calls.push(path);
        return run;
      },
    ),
    [run],
  );
  assert.deepEqual(calls, ["actions/runs/123"]);
});
test("legacy release history still looks up the source, and unrelated recorded workflows fail closed", async () => {
  await deploymentRuns(metadata, before, async (path) => {
    assert.match(path, new RegExp(`head_sha=${before}`));
    return { workflow_runs: [] };
  });
  await assert.rejects(
    deploymentRuns(
      metadata + '\n  deploymentRunId: "123"',
      before,
      async () => ({ path: ".github/workflows/other.yml" }),
    ),
    /not an application deployment/,
  );
});
