import assert from "node:assert/strict";
import { test } from "node:test";
import {
  waitForDeployment,
  waitForEvaluation,
  renewingToken,
} from "./wait-deployments.mjs";

for (const status of ["failed", "cancelled", "blocked"]) {
  test(`rejects ${status} even when rollback will restore service`, async () => {
    await assert.rejects(
      waitForDeployment("release", {
        signal: new AbortController().signal,
        get: async () => ({ Status: status }),
      }),
      new RegExp(status),
    );
  });
}

test("waits through placement and warmup until health succeeds", async () => {
  const states = ["pending", "running", "successful"];
  const paths = [];
  await waitForDeployment("release", {
    signal: new AbortController().signal,
    get: async (path) => {
      paths.push(path);
      return { Status: states.shift() };
    },
    pause: async () => {},
  });
  assert.equal(paths.length, 3);
  assert.ok(paths.every((path) => path === "/v1/deployment/release"));
});

test("a deployment that never places has a bounded deadline", async () => {
  const controller = new AbortController();
  await assert.rejects(
    waitForDeployment("release", {
      signal: controller.signal,
      get: async () => ({ Status: "running" }),
      pause: async () => controller.abort(),
    }),
    /deadline/,
  );
});

test("an API failure cannot report a healthy deployment", async () => {
  await assert.rejects(
    waitForDeployment("release", {
      signal: new AbortController().signal,
      get: async () => {
        throw new Error("Nomad unavailable");
      },
    }),
    /unavailable/,
  );
});

test("does not miss a deployment created asynchronously after registration", async () => {
  const states = [
    { Status: "pending" },
    { Status: "complete", DeploymentID: "new" },
    { Status: "running" },
    { Status: "successful" },
  ];
  const paths = [];
  await waitForEvaluation("evaluation", "old", {
    signal: new AbortController().signal,
    get: async (path) => {
      paths.push(path);
      return states.shift();
    },
    pause: async () => {},
  });
  assert.deepEqual(paths, [
    "/v1/evaluation/evaluation",
    "/v1/evaluation/evaluation",
    "/v1/deployment/new",
    "/v1/deployment/new",
  ]);
});

test("a no-op registration does not wait on an unchanged deployment", async () => {
  await waitForEvaluation("evaluation", "old", {
    signal: new AbortController().signal,
    get: async (path) => {
      assert.equal(path, "/v1/evaluation/evaluation");
      return { Status: "complete", DeploymentID: "old" };
    },
  });
});

test("long rollout checks renew short-lived credentials once for concurrent readers", async () => {
  let time = 0;
  let renewals = 0;
  const token = renewingToken(
    "initial",
    async () => {
      renewals++;
      return "renewed";
    },
    () => time,
  );
  assert.equal(await token(), "initial");
  time = 45 * 60_000;
  assert.deepEqual(await Promise.all([token(), token()]), [
    "renewed",
    "renewed",
  ]);
  assert.equal(renewals, 1);
});
