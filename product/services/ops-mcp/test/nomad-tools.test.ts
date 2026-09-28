import { afterEach, describe, expect, it } from "vitest";

import { callTool, closeServers } from "./support/mcp.js";

afterEach(closeServers);

const defaults = { namespace: "*", per_page: "100", reverse: "true" };

describe("nomad tool", () => {
  it.each([
    ["jobs", "/v1/jobs"],
    ["allocations", "/v1/allocations"],
    ["deployments", "/v1/deployments"],
    ["evaluations", "/v1/evaluations"],
    ["nodes", "/v1/nodes"],
    ["node_pools", "/v1/node/pools"],
  ])("lists %s stubs from %s across namespaces", async (resource, path) => {
    const { backend } = await callTool("nomad", { resource }, []);

    expect(backend).toHaveBeenCalledWith("nomad", path, defaults);
  });

  it("passes filter expressions, prefixes and node resources", async () => {
    const { backend } = await callTool(
      "nomad",
      {
        resource: "nodes",
        filter: 'Status != "ready"',
        prefix: "a1b2",
        include_resources: true,
        reverse: false,
      },
      [],
    );

    expect(backend).toHaveBeenCalledWith("nomad", "/v1/nodes", {
      ...defaults,
      reverse: "false",
      filter: 'Status != "ready"',
      prefix: "a1b2",
      resources: "true",
    });
  });

  it.each([
    { resource: "jobs/example" },
    { resource: "jobs", prefix: "../agent/self" },
    { resource: "jobs", namespace: "default&index=1" },
  ])("rejects %o", async (args) => {
    const { backend, isError } = await callTool("nomad", args);

    expect(isError).toBe(true);
    expect(backend).not.toHaveBeenCalled();
  });
});
