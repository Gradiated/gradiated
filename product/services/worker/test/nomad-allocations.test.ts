import { describe, expect, it } from "vitest";

import {
  allocationIsGone,
  readModelAllocations,
} from "../src/nomad-allocations.js";

const release = (runtimeRevision: string) =>
  JSON.stringify({
    schema_version: 1,
    runtime_revision: runtimeRevision,
    model_path: "vendor/model",
    model_revision: "model-revision",
    tokenizer_path: "vendor/tokenizer",
    tokenizer_revision: "tokenizer-revision",
  });

const nomad =
  (responses: Record<string, unknown>) =>
  async (path: string): Promise<unknown> => {
    if (!(path in responses)) throw new Error(`unexpected Nomad path ${path}`);
    return responses[path];
  };

const kevVersions = {
  Versions: [
    {
      Version: 1,
      Meta: {
        gradiated_model_id: "kev/kev-9b",
        gradiated_release: release("v2"),
      },
    },
    {
      Version: 0,
      Meta: {
        gradiated_model_id: "kev/kev-9b",
        gradiated_release: release("v1"),
      },
    },
  ],
};

describe("reading model allocations from Nomad", () => {
  it.each([true, false])(
    "marks only opted-in unpromoted canaries as pending verification (%s)",
    async (canary) => {
      const allocations = await readModelAllocations(
        nomad({
          "/v1/jobs?meta=true": [
            { ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } },
          ],
          "/v1/job/kev-9b/deployments": [],
          "/v1/job/kev-9b/allocations": [
            {
              ID: "a1",
              NodeID: "n1",
              ClientStatus: "running",
              DesiredStatus: "run",
              JobVersion: 1,
              DeploymentStatus: { Canary: canary },
            },
          ],
          "/v1/job/kev-9b/versions": {
            Versions: [
              {
                ...kevVersions.Versions[0],
                Meta: {
                  ...kevVersions.Versions[0]!.Meta,
                  gradiated_sdk_verification: "true",
                },
              },
            ],
          },
        }),
        () => {},
      );
      expect(allocations[0]?.verificationPending ?? false).toBe(canary);
    },
  );

  it.each(["pending", "running", "paused", "successful", "failed"])(
    "keeps unverified deployments unrouted and allows recovery only after success (%s)",
    async (status) => {
      const allocations = await readModelAllocations(
        nomad({
          "/v1/jobs?meta=true": [
            { ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } },
          ],
          "/v1/job/kev-9b/deployments": [{ JobVersion: 1, Status: status }],
          "/v1/job/kev-9b/allocations": [
            {
              ID: "a1",
              NodeID: "n1",
              ClientStatus: "running",
              DesiredStatus: "run",
              JobVersion: 1,
              DeploymentStatus: { Canary: false },
            },
          ],
          "/v1/job/kev-9b/versions": {
            Versions: [
              {
                ...kevVersions.Versions[0],
                Meta: {
                  ...kevVersions.Versions[0]!.Meta,
                  gradiated_sdk_verification: "true",
                },
              },
            ],
          },
        }),
        () => {},
      );
      expect(allocations[0]?.verificationPending ?? false).toBe(
        status !== "successful",
      );
    },
  );

  it.each(["running", "paused", "failed"])(
    "routes qualified rolling replacements only during active updates (%s)",
    async (status) => {
      const allocations = await readModelAllocations(
        nomad({
          "/v1/jobs?meta=true": [
            { ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } },
          ],
          "/v1/job/kev-9b/deployments": [{ JobVersion: 1, Status: status }],
          "/v1/job/kev-9b/allocations": [
            {
              ID: "qualified",
              NodeID: "n1",
              ClientStatus: "running",
              DesiredStatus: "run",
              JobVersion: 1,
              DeploymentStatus: { Canary: false, Healthy: true },
            },
            {
              ID: "warming",
              NodeID: "n2",
              ClientStatus: "running",
              DesiredStatus: "run",
              JobVersion: 1,
              DeploymentStatus: { Canary: false, Healthy: null },
            },
            {
              ID: "canary",
              NodeID: "n3",
              ClientStatus: "running",
              DesiredStatus: "run",
              JobVersion: 1,
              DeploymentStatus: { Canary: true, Healthy: true },
            },
            {
              ID: "rejected",
              NodeID: "n4",
              ClientStatus: "running",
              DesiredStatus: "run",
              JobVersion: 1,
              DeploymentStatus: { Canary: false, Healthy: false },
            },
            {
              ID: "previous",
              NodeID: "n5",
              ClientStatus: "running",
              DesiredStatus: "run",
              JobVersion: 0,
            },
          ],
          "/v1/job/kev-9b/versions": {
            Versions: kevVersions.Versions.map((version) => ({
              ...version,
              Meta: { ...version.Meta, gradiated_sdk_verification: "true" },
            })),
          },
        }),
        () => {},
      );

      expect(
        allocations.map((allocation) => [
          allocation.allocationId,
          allocation.verificationPending ?? false,
        ]),
      ).toEqual([
        ["qualified", status !== "running"],
        ["warming", true],
        ["canary", true],
        ["rejected", true],
        ["previous", false],
      ]);
    },
  );

  it("returns running allocations of model jobs with their own version's release", async () => {
    const allocations = await readModelAllocations(
      nomad({
        "/v1/jobs?meta=true": [
          { ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } },
          { ID: "host-proxy", Meta: null },
        ],
        "/v1/job/kev-9b/allocations": [
          {
            ID: "a1",
            NodeID: "n1",
            ClientStatus: "running",
            DesiredStatus: "run",
            JobVersion: 1,
          },
          {
            ID: "a0",
            NodeID: "n2",
            ClientStatus: "running",
            DesiredStatus: "stop",
            JobVersion: 0,
          },
          {
            ID: "a2",
            NodeID: "n1",
            ClientStatus: "pending",
            DesiredStatus: "run",
            JobVersion: 1,
          },
          {
            ID: "a3",
            NodeID: "n1",
            ClientStatus: "complete",
            DesiredStatus: "stop",
            JobVersion: 0,
          },
        ],
        "/v1/job/kev-9b/versions": kevVersions,
      }),
      () => {},
    );

    expect(allocations).toEqual([
      {
        allocationId: "a1",
        nodeId: "n1",
        modelId: "kev/kev-9b",
        release: JSON.parse(release("v2")),
        draining: false,
      },
      {
        allocationId: "a0",
        nodeId: "n2",
        modelId: "kev/kev-9b",
        release: JSON.parse(release("v1")),
        draining: true,
      },
    ]);
  });

  it("skips a job with a malformed release instead of failing every model", async () => {
    const skipped: string[] = [];

    const allocations = await readModelAllocations(
      nomad({
        "/v1/jobs?meta=true": [
          { ID: "broken", Meta: { gradiated_model_id: "vendor/broken" } },
          { ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } },
        ],
        "/v1/job/broken/allocations": [
          {
            ID: "b1",
            NodeID: "n1",
            ClientStatus: "running",
            DesiredStatus: "run",
            JobVersion: 0,
          },
        ],
        "/v1/job/broken/versions": {
          Versions: [
            {
              Version: 0,
              Meta: {
                gradiated_model_id: "vendor/broken",
                gradiated_release: "{not json",
              },
            },
          ],
        },
        "/v1/job/kev-9b/allocations": [
          {
            ID: "a1",
            NodeID: "n1",
            ClientStatus: "running",
            DesiredStatus: "run",
            JobVersion: 1,
          },
        ],
        "/v1/job/kev-9b/versions": kevVersions,
      }),
      (allocationId, modelId) => skipped.push(`${allocationId}:${modelId}`),
    );

    expect(allocations.map((a) => a.allocationId)).toEqual(["a1"]);
    expect(skipped).toEqual(["b1:vendor/broken"]);
  });
});

describe("confirming an allocation is gone", () => {
  const answering = (result: unknown) => async (): Promise<unknown> => {
    if (result instanceof Error) throw result;
    return result;
  };

  it.each(["complete", "failed", "lost"])(
    "treats a %s allocation as gone",
    async (status) => {
      await expect(
        allocationIsGone(answering({ ClientStatus: status }), "a1"),
      ).resolves.toBe(true);
    },
  );

  it("removes a legacy or collected allocation ID confirmed absent by Nomad", async () => {
    await expect(
      allocationIsGone(
        answering(Object.assign(new Error("missing"), { code: "404" })),
        "0ae67510-9c6d-4142-ac11-9472608ad4c5",
      ),
    ).resolves.toBe(true);
  });

  it("keeps a running allocation Nomad did not list", async () => {
    await expect(
      allocationIsGone(answering({ ClientStatus: "running" }), "a1"),
    ).resolves.toBe(false);
  });

  it("fails rather than guessing when Nomad refuses", async () => {
    await expect(
      allocationIsGone(
        answering(Object.assign(new Error("denied"), { code: "403" })),
        "a1",
      ),
    ).rejects.toMatchObject({ code: "403" });
  });
});
