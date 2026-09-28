import { describe, expect, it } from "vitest";

import { reconcileDeployments } from "../src/deployment-reconciliation.js";

const release = JSON.stringify({
  schema_version: 1,
  runtime_revision: "r1",
  model_path: "vendor/model",
  model_revision: "model-revision",
  tokenizer_path: "vendor/tokenizer",
  tokenizer_revision: "tokenizer-revision",
});

const get = async (path: string): Promise<unknown> =>
  ({
    "/v1/jobs?meta=true": [
      { ID: "kev-9b", Meta: { gradiated_model_id: "kev/kev-9b" } },
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
        NodeID: "n1",
        ClientStatus: "running",
        DesiredStatus: "run",
        JobVersion: 0,
      },
    ],
    "/v1/job/kev-9b/versions": {
      Versions: [
        {
          Version: 1,
          Meta: {
            gradiated_model_id: "kev/kev-9b",
            gradiated_release: release,
          },
        },
        {
          Version: 0,
          Meta: { gradiated_model_id: "kev/kev-9b", gradiated_release: "{" },
        },
      ],
    },
  })[path];

describe("deployment reconciliation pass", () => {
  it("counts skipped and unplaced allocations together by reason", async () => {
    const recorded: unknown[] = [];

    await reconcileDeployments({
      get,
      store: {
        reconcile: async (nomad) => {
          const allocations = await nomad.running();
          return {
            written: 0,
            removed: 0,
            unplaced: allocations.map((allocation) => ({
              allocationId: allocation.allocationId,
              modelId: allocation.modelId,
              reason: "node_not_registered" as const,
            })),
          };
        },
      },
      metrics: {
        recordReconciliation: (routed, unrouted) =>
          recorded.push({ routed, unrouted }),
      },
    });

    expect(recorded).toEqual([
      {
        routed: 0,
        unrouted: { invalid_release_meta: 1, node_not_registered: 1 },
      },
    ]);
  });

  it("leaves metrics alone when another worker ran the pass", async () => {
    const recorded: unknown[] = [];

    await reconcileDeployments({
      get,
      store: { reconcile: async () => null },
      metrics: { recordReconciliation: () => recorded.push("called") },
    });

    expect(recorded).toEqual([]);
  });
});
