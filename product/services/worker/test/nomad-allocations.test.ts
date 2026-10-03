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
  it("reads version metadata after observing a rebound allocation", async () => {
    let observed = false;
    const result = await readModelAllocations(
      async (path) => {
        if (path === "/v1/jobs?meta=true")
          return [{ ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } }];
        if (path.endsWith("/allocations")) {
          await Promise.resolve();
          observed = true;
          return [
            {
              ID: "retained",
              NodeID: "n1",
              JobVersion: 3,
              ClientStatus: "running",
              DesiredStatus: "run",
            },
          ];
        }
        if (path.endsWith("/versions"))
          return {
            Versions: observed
              ? [
                  {
                    Version: 3,
                    Meta: {
                      gradiated_model_id: "kev/kev-9b",
                      gradiated_release: release("v3"),
                    },
                  },
                ]
              : [],
          };
        throw new Error(path);
      },
      () => {},
    );
    expect(result).toHaveLength(1);
    expect(result[0]?.release.runtime_revision).toBe("v3");
  });

  it.each([
    { CreateIndex: 1, runtime: "v1", pending: false },
    { CreateIndex: 30, runtime: "v1", pending: true },
    { CreateIndex: 1, runtime: "changed", pending: true },
  ])(
    "restores only retained qualified rollback allocations ($CreateIndex, $runtime)",
    async ({ CreateIndex, runtime, pending }) => {
      const metadata = {
        gradiated_model_id: "kev/kev-9b",
        gradiated_release: release("v1"),
        gradiated_sdk_verification: "true",
      };
      const result = await readModelAllocations(
        nomad({
          "/v1/jobs?meta=true": [{ ID: "kev-9b", Meta: metadata }],
          "/v1/job/kev-9b/versions": {
            Versions: [
              { Version: 1, Meta: metadata },
              {
                Version: 3,
                Meta: { ...metadata, gradiated_release: release(runtime) },
              },
            ],
          },
          "/v1/job/kev-9b/deployments": [
            { JobVersion: 1, Status: "successful", CreateIndex: 2 },
            { JobVersion: 2, Status: "failed", CreateIndex: 20 },
            { JobVersion: 3, Status: "running", CreateIndex: 25 },
          ],
          "/v1/job/kev-9b/allocations": [
            {
              ID: "retained",
              NodeID: "n1",
              Name: "kev-9b.replicas[0]",
              JobVersion: 3,
              CreateIndex,
              ClientStatus: "running",
              DesiredStatus: "run",
              DeploymentStatus: null,
            },
          ],
        }),
        () => {},
      );
      expect(result[0]?.verificationPending ?? false).toBe(pending);
    },
  );

  it.each(["pending", "unknown"])(
    "withdraws explicitly stopped allocations even while their client status is %s",
    async (ClientStatus) => {
      const result = await readModelAllocations(
        nomad({
          "/v1/jobs?meta=true": [
            { ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } },
          ],
          "/v1/job/kev-9b/versions": kevVersions,
          "/v1/job/kev-9b/allocations": [
            {
              ID: "stopping",
              NodeID: "n1",
              JobVersion: 0,
              ClientStatus,
              DesiredStatus: "stop",
            },
          ],
        }),
        () => {},
      );
      expect(result).toHaveLength(1);
      expect(result[0]?.draining).toBe(true);
    },
  );
  it.each(["running", "failed"])(
    "does not revive a superseded allocation when the newer deployment is %s",
    async (status) => {
      const metadata = {
        gradiated_model_id: "kev/kev-9b",
        gradiated_sdk_verification: "true",
        gradiated_replica_parent: "kev-9b",
        gradiated_replica_slot: "0",
        gradiated_release: release("v1"),
      };
      const result = await readModelAllocations(
        nomad({
          "/v1/jobs?meta=true": [{ ID: "kev-replica-0", Meta: metadata }],
          "/v1/job/kev-replica-0/versions": {
            Versions: [0, 1, 2, 3].map((Version) => ({
              Version,
              Meta: metadata,
            })),
          },
          "/v1/job/kev-replica-0/deployments": [
            { JobVersion: 1, Status: "successful" },
            { JobVersion: 2, Status: status },
            { JobVersion: 3, Status: "running" },
          ],
          "/v1/job/kev-replica-0/allocations": [
            {
              ID: "current",
              NodeID: "n1",
              JobVersion: 1,
              CreateIndex: 20,
              ClientStatus: "running",
              DesiredStatus: "run",
              DeploymentStatus: { Healthy: true },
            },
            {
              ID: "rebound-old",
              NodeID: "n2",
              JobVersion: 2,
              CreateIndex: status === "running" ? 10 : 25,
              ClientStatus: "pending",
              DesiredStatus: "run",
              DeploymentStatus: { Healthy: null },
            },
            {
              ID: "warming",
              NodeID: "n3",
              JobVersion: 3,
              CreateIndex: 30,
              ClientStatus: "running",
              DesiredStatus: "run",
              DeploymentStatus: { Canary: true, Healthy: null },
            },
          ],
        }),
        () => {},
      );
      expect(
        result.find((a) => a.allocationId === "rebound-old")?.draining,
      ).toBe(true);
      expect(result.find((a) => a.allocationId === "warming")?.draining).toBe(
        false,
      );
      expect(
        result
          .filter((a) => !a.draining && !a.verificationPending)
          .map((a) => a.allocationId),
      ).toEqual(["current"]);
    },
  );

  it.each([false, true])(
    "cuts over only the verified replica slot (%s)",
    async (healthy) => {
      const parentMeta = {
        gradiated_model_id: "kev/kev-9b",
        gradiated_sdk_verification: "true",
        gradiated_release: release("v1"),
      };
      const childMeta = {
        ...parentMeta,
        gradiated_replica_parent: "kev-9b",
        gradiated_replica_slot: "1",
      };
      const base = {
        NodeID: "n1",
        ClientStatus: "running",
        DesiredStatus: "run",
        JobVersion: 0,
      };
      const result = await readModelAllocations(
        nomad({
          "/v1/jobs?meta=true": [
            { ID: "kev-9b", Meta: parentMeta },
            { ID: "kev-9b-replica-1", Meta: childMeta },
          ],
          "/v1/job/kev-9b/versions": {
            Versions: [{ Version: 0, Meta: parentMeta }],
          },
          "/v1/job/kev-9b/deployments": [
            { JobVersion: 0, Status: "successful" },
          ],
          "/v1/job/kev-9b/allocations": [0, 1].map((index) => ({
            ...base,
            ID: `old-${index}`,
            Name: `kev-9b.replicas[${index}]`,
          })),
          "/v1/job/kev-9b-replica-1/versions": {
            Versions: [{ Version: 0, Meta: childMeta }],
          },
          "/v1/job/kev-9b-replica-1/deployments": [
            { JobVersion: 0, Status: "running" },
          ],
          "/v1/job/kev-9b-replica-1/allocations": [
            {
              ...base,
              ID: "new-1",
              Name: "kev-9b-replica-1.replicas[0]",
              DeploymentStatus: { Canary: false, Healthy: healthy },
            },
          ],
        }),
        () => {},
      );
      expect(
        result
          .filter((a) => !a.draining && !a.verificationPending)
          .map((a) => a.allocationId),
      ).toEqual(healthy ? ["old-0", "new-1"] : ["old-0", "old-1"]);
      expect(result.find((a) => a.allocationId === "old-1")?.draining).toBe(
        healthy,
      );
    },
  );

  it("selects one verified child while Nomad is still stopping the previous allocation", async () => {
    const metadata = {
      gradiated_model_id: "kev/kev-9b",
      gradiated_sdk_verification: "true",
      gradiated_release: release("v1"),
      gradiated_replica_parent: "kev-9b",
      gradiated_replica_slot: "0",
    };
    const result = await readModelAllocations(
      nomad({
        "/v1/jobs?meta=true": [{ ID: "kev-9b-replica-0", Meta: metadata }],
        "/v1/job/kev-9b-replica-0/versions": {
          Versions: [0, 1].map((Version) => ({ Version, Meta: metadata })),
        },
        "/v1/job/kev-9b-replica-0/deployments": [
          { JobVersion: 0, Status: "successful" },
          { JobVersion: 1, Status: "successful" },
        ],
        "/v1/job/kev-9b-replica-0/allocations": [0, 1].map((JobVersion) => ({
          ID: `v${JobVersion}`,
          Name: "kev-9b-replica-0.replicas[0]",
          NodeID: "n1",
          ClientStatus: "running",
          DesiredStatus: "run",
          JobVersion,
        })),
      }),
      () => {},
    );
    expect(
      result.filter((a) => !a.draining).map((a) => a.allocationId),
    ).toEqual(["v1"]);
  });

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

  it("reads active allocations with their own releases and keeps pending allocations unavailable", async () => {
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
      {
        allocationId: "a2",
        nodeId: "n1",
        modelId: "kev/kev-9b",
        release: JSON.parse(release("v2")),
        draining: false,
        verificationPending: true,
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

  it.each(["pending", "unknown"])(
    "retires an unlisted allocation explicitly stopped with client status %s",
    async (ClientStatus) => {
      await expect(
        allocationIsGone(
          answering({ ClientStatus, DesiredStatus: "stop" }),
          "a1",
        ),
      ).resolves.toBe(true);
      await expect(
        allocationIsGone(
          answering({ ClientStatus, DesiredStatus: "run" }),
          "a1",
        ),
      ).resolves.toBe(false);
    },
  );

  it("retires an unlisted stopped allocation while its client still drains", async () => {
    await expect(
      allocationIsGone(
        answering({ ClientStatus: "running", DesiredStatus: "stop" }),
        "a1",
      ),
    ).resolves.toBe(true);
  });

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
