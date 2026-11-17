import { describe, expect, it } from "vitest";
import {
  loraMetricsTargets,
  runtimeMetricsTargets,
} from "../src/lora-metrics-targets.js";

describe("LoRA metrics targets", () => {
  it("discovers the private runtime metrics endpoint independently of adapter metrics", () => {
    expect(
      runtimeMetricsTargets([
        { id: "a", modelId: "glm", serviceUrl: "https://host.example/alloc/a" },
      ])[0]?.labels.__metrics_path__,
    ).toBe("/alloc/a/internal/runtime-metrics");
    expect(() =>
      runtimeMetricsTargets([
        {
          id: "a",
          modelId: "glm",
          serviceUrl: "https://secret@host.example/alloc/a",
        },
      ]),
    ).toThrow();
  });
  it("uses the allocation's existing host route without disclosing credentials", () => {
    expect(
      loraMetricsTargets([
        {
          id: "allocation-1",
          modelId: "z-ai/glm-5.3-flash",
          serviceUrl: "https://host.example/alloc/allocation-1/",
        },
      ]),
    ).toEqual([
      {
        targets: ["host.example"],
        labels: {
          __scheme__: "https",
          __metrics_path__: "/alloc/allocation-1/internal/adapters/metrics",
          model: "z-ai/glm-5.3-flash",
          deployment: "allocation-1",
          service: "inference",
        },
      },
    ]);
    expect(loraMetricsTargets([])).toEqual([]);
  });
  it("discovers public and canonical private allocations together", () => {
    const id = "00000000-0000-4000-8000-000000000001";
    const host = `gpu-${id}.tailscale-inference.svc.cluster.local:8888`;
    const targets = loraMetricsTargets([
      { id, modelId: "base", serviceUrl: `http://${host}/alloc/${id}` },
      {
        id: "public",
        modelId: "base",
        serviceUrl: "https://host.example/alloc/public",
      },
    ]);
    expect(targets[0]).toMatchObject({
      targets: [host],
      labels: {
        __scheme__: "http",
        __metrics_path__: `/alloc/${id}/internal/adapters/metrics`,
      },
    });
    expect(targets[1]?.labels.__scheme__).toBe("https");
  });
  it.each([
    "http://host.example/alloc/a",
    "http://gpu-00000000-0000-4000-8000-000000000001.tailscale-inference.svc.cluster.local.evil:8888/alloc/00000000-0000-4000-8000-000000000001",
    "http://gpu-00000000-0000-4000-8000-000000000001.tailscale-inference.svc.cluster.local:9999/alloc/00000000-0000-4000-8000-000000000001",
    "https://secret@host.example/alloc/a",
    "https://host.example/alloc/a?token=secret",
    "https://host.example/alloc/a#fragment",
  ])("rejects unsafe target %s", (serviceUrl) => {
    expect(() =>
      loraMetricsTargets([{ id: "a", modelId: "base", serviceUrl }]),
    ).toThrow("Invalid inference metrics target");
  });
});
