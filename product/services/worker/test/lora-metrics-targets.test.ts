import { describe, expect, it } from "vitest";
import { loraMetricsTargets } from "../src/lora-metrics-targets.js";

describe("LoRA metrics targets", () => {
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
          __metrics_path__: "/alloc/allocation-1/internal/adapters/metrics",
          model: "z-ai/glm-5.3-flash",
          deployment: "allocation-1",
          service: "inference",
        },
      },
    ]);
    expect(loraMetricsTargets([])).toEqual([]);
  });
  it.each([
    "http://host.example/alloc/a",
    "https://secret@host.example/alloc/a",
    "https://host.example/alloc/a?token=secret",
    "https://host.example/alloc/a#fragment",
  ])("rejects unsafe target %s", (serviceUrl) => {
    expect(() =>
      loraMetricsTargets([{ id: "a", modelId: "base", serviceUrl }]),
    ).toThrow("Invalid inference metrics target");
  });
});
