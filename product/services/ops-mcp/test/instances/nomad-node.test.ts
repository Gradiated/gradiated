import { describe, expect, it, vi } from "vitest";

import { UpstreamError } from "../../src/backend.js";
import {
  nomadNodeReader,
  waitForNomadNode,
  type NomadNode,
} from "../../src/instances/nomad-node.js";

describe("waiting for the Nomad node", () => {
  const node = (Status: string, instance = "instance-1"): NomadNode => ({
    ID: "node-1",
    Name: "runpod-pod1",
    Status,
    Meta: { gradiated_instance_id: instance },
  });
  const clock = () => {
    let time = 0;
    return {
      now: () => time,
      sleep: async (ms: number) => {
        time += ms;
      },
    };
  };

  it("returns once the node has joined and is ready", async () => {
    const states = [null, node("initializing"), node("ready")];

    await expect(
      waitForNomadNode(async () => states.shift() ?? null, {
        nomadNodeId: "node-1",
        instanceId: "instance-1",
        timeoutMs: 60_000,
        ...clock(),
      }),
    ).resolves.toMatchObject({ Status: "ready" });
  });

  it("rejects a node that carries another instance's metadata", async () => {
    await expect(
      waitForNomadNode(async () => node("ready", "instance-2"), {
        nomadNodeId: "node-1",
        instanceId: "instance-1",
        timeoutMs: 60_000,
        ...clock(),
      }),
    ).rejects.toThrow("belongs to instance instance-2, not instance-1");
  });

  it("gives up with the last status it saw", async () => {
    await expect(
      waitForNomadNode(async () => node("down"), {
        nomadNodeId: "node-1",
        instanceId: "instance-1",
        timeoutMs: 10_000,
        ...clock(),
      }),
    ).rejects.toThrow("was not ready after 10s (last status: down)");
  });
});

describe("reading a Nomad node", () => {
  it("reads the node through the Nomad client", async () => {
    const node = { ID: "node-1", Name: "runpod-pod1", Status: "ready" };
    const backend = vi.fn(async () => ({ data: node, next_token: null }));

    await expect(nomadNodeReader(backend)("node-1")).resolves.toEqual(node);
    expect(backend).toHaveBeenCalledWith("nomad", "/v1/node/node-1");
  });

  it("treats a node Nomad does not know yet as absent", async () => {
    const backend = vi.fn(async () => {
      throw new UpstreamError(404);
    });

    await expect(nomadNodeReader(backend)("node-1")).resolves.toBeNull();
  });

  it("surfaces every other failure", async () => {
    const backend = vi.fn(async () => {
      throw new UpstreamError(403);
    });

    await expect(nomadNodeReader(backend)("node-1")).rejects.toThrow(
      "upstream_failed",
    );
  });
});
