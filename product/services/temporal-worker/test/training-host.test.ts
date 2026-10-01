import { randomUUID } from "node:crypto";
import { expect, it, vi } from "vitest";
import {
  createTrainingHosts,
  trainingHostJob,
} from "../src/training/nomad-host.js";

const runId = randomUUID();
const nodeId = randomUUID();
const allocationId = randomUUID();
const config = {
  bundleUrl: `s3::https://test.s3.us-east-1.amazonaws.com/bundles/sha256/${"a".repeat(64)}.tar.gz`,
  bundleSha256: "a".repeat(64),
  baseId: "base-test",
  gpuType: "H100",
};

it("keeps placement within the registered pool and disables scheduler replacement", () => {
  const job = trainingHostJob(runId, 1, [{ nodeId, podId: "pod1" }], config);
  expect(job.Constraints).toContainEqual({
    LTarget: "${node.unique.id}",
    Operand: "regexp",
    RTarget: `^(${nodeId})$`,
  });
  expect(job.TaskGroups[0]).toMatchObject({
    RestartPolicy: { Attempts: 0, Mode: "fail" },
    ReschedulePolicy: { Attempts: 0, Unlimited: false },
    Disconnect: { Replace: false },
  });
  expect(JSON.stringify(job)).not.toContain("TEMPORAL");
});

it.each([false, true])(
  "requests shutdown without reading allocation death; request fails: %s",
  async (fails) => {
    const request = vi.fn(
      async (path: string, method?: string): Promise<unknown> => {
        if (path.startsWith("/v1/jobs?"))
          return [{ ID: `training-${runId}-1` }];
        if (method === "DELETE") {
          if (fails) throw new Error("Nomad unreachable");
          return {};
        }
        throw new Error("Must not poll for a dead host");
      },
    );
    const hosts = createTrainingHosts({
      request,
      nodes: async () => [{ nodeId, podId: "pod1" }],
      config,
      token: "test",
    });
    if (fails)
      await expect(hosts.release(runId)).rejects.toThrow("Nomad unreachable");
    else await hosts.release(runId);
    expect(request.mock.calls).toEqual([
      [`/v1/jobs?prefix=training-${runId}-`],
      [`/v1/job/training-${runId}-1?purge=false`, "DELETE"],
    ]);
  },
);

it("requests shutdown for every attempt even when an earlier request fails", async () => {
  const request = vi.fn(async (path: string): Promise<unknown> => {
    if (path.startsWith("/v1/jobs?"))
      return [{ ID: `training-${runId}-1` }, { ID: `training-${runId}-2` }];
    if (path.endsWith("-1?purge=false")) throw new Error("Request failed");
    return {};
  });
  const hosts = createTrainingHosts({
    request,
    nodes: async () => [],
    config,
    token: "test",
  });
  await expect(hosts.release(runId)).rejects.toThrow("Request failed");
  expect(request).toHaveBeenCalledWith(
    `/v1/job/training-${runId}-2?purge=false`,
    "DELETE",
  );
});

it("returns pending capacity without occupying an activity slot", async () => {
  const request = vi.fn(async (path: string): Promise<unknown> =>
    path.endsWith("allocations?all=true") ? [] : {},
  );
  const hosts = createTrainingHosts({
    request,
    nodes: async () => [{ nodeId, podId: "pod1" }],
    config,
    token: "test",
  });
  expect(await hosts.allocate(runId, 1)).toBeNull();
  expect(request).toHaveBeenCalledTimes(2);
});

it.each(["running", "lost"])(
  "renews only a running exact allocation: %s",
  async (status) => {
    const http = vi.fn(async () => Response.json({ renewed: true }));
    const hosts = createTrainingHosts({
      request: async () => [
        { ID: allocationId, NodeID: nodeId, ClientStatus: status },
      ],
      nodes: async () => [{ nodeId, podId: "pod1" }],
      config,
      token: "test",
      fetch: http,
    });
    const host = {
      allocationId,
      jobId: `training-${runId}-1`,
      url: "https://trainer.test",
    };
    if (status === "lost") {
      await expect(hosts.renew(host)).rejects.toThrow("no longer running");
      expect(http).not.toHaveBeenCalled();
    } else {
      await hosts.renew(host);
      expect(http).toHaveBeenCalledWith(
        "https://trainer.test/reservation",
        expect.objectContaining({
          body: JSON.stringify({ allocation_id: allocationId }),
        }),
      );
      await expect(
        hosts.renew({ ...host, allocationId: randomUUID() }),
      ).rejects.toThrow("no longer running");
    }
  },
);

it("waits when every training node is absent", async () => {
  const request = vi.fn(async () => ({}));
  const hosts = createTrainingHosts({
    request,
    nodes: async () => [],
    config,
    token: "test",
  });
  expect(await hosts.allocate(runId, 1)).toBeNull();
  expect(request).not.toHaveBeenCalled();
});
