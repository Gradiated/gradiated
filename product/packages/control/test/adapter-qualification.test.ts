import { describe, expect, it, vi } from "vitest";
import type { ModelDeploymentRelease } from "@gradiated/contracts";
import {
  createAdapterQualifier,
  servesAdapter,
  type AdapterProbe,
  type AdapterProbeTarget,
  type AdapterQualificationResult,
} from "../src/training/qualification.js";
import type { TaskVersionRecord } from "../src/training/records.js";

const release = (
  overrides: Partial<ModelDeploymentRelease> = {},
): ModelDeploymentRelease => ({
  schema_version: 1,
  runtime_revision: "glm-sglang-1",
  model_path: "vendor/model",
  model_revision: "serving",
  tokenizer_path: "vendor/model",
  tokenizer_revision: "serving",
  lora_enabled: true,
  lora_base_model_revision: "training",
  ...overrides,
});
const target = (
  id: string,
  overrides: Partial<ModelDeploymentRelease> = {},
): AdapterProbeTarget => ({
  id,
  modelId: "z-ai/glm-5.3-flash",
  serviceUrl: `http://gpu.example:8888/alloc/${id}`,
  release: release(overrides),
});
const version = {
  id: "0195f2a0-0000-7000-8000-000000000001",
  workspaceId: "0195f2a0-0000-7000-8000-000000000002",
  taskId: "0195f2a0-0000-7000-8000-000000000003",
  baseModelId: "z-ai/glm-5.3-flash",
  status: "unavailable",
  adapter: {
    format: "peft_lora",
    artifact_uri: "s3://bucket/a.tar.gz",
    sha256: "a".repeat(64),
    size_bytes: 1,
    rank: 2,
    base_model_revision: "declared",
    validated_base_model_revision: "training",
  },
} as TaskVersionRecord;

const qualifier = (
  targets: AdapterProbeTarget[],
  probe: AdapterProbe,
  maxAttempts?: number,
) => {
  const reports: AdapterQualificationResult[] = [];
  let clock = 1_000;
  return {
    reports,
    qualify: createAdapterQualifier({
      targets: async () => targets,
      probe,
      report: (result) => reports.push(result),
      order: (items) => [...items],
      now: () => (clock += 250),
      ...(maxAttempts ? { maxAttempts } : {}),
    }),
  };
};

describe("servesAdapter", () => {
  it("matches the gateway's LoRA deployment rule", () => {
    expect(servesAdapter(release(), "training")).toBe(true);
    expect(servesAdapter(release(), "serving")).toBe(false);
    expect(servesAdapter(release(), undefined)).toBe(false);
    expect(
      servesAdapter(
        release({ lora_base_model_revision: undefined }),
        "serving",
      ),
    ).toBe(true);
    expect(servesAdapter(release({ lora_enabled: false }), "training")).toBe(
      false,
    );
    expect(servesAdapter(release({ protocol: "system_one" }), "training")).toBe(
      false,
    );
    expect(
      servesAdapter(release({ runtime_revision: "native-kev" }), "training"),
    ).toBe(false);
  });
});

describe("createAdapterQualifier", () => {
  it("probes the validated revision's allocations and reports success", async () => {
    const probe = vi.fn<AdapterProbe>(async () => ({ ok: true }));
    const { qualify, reports } = qualifier(
      [target("wrong", { lora_base_model_revision: "declared" }), target("a")],
      probe,
    );

    await qualify(version);

    expect(probe).toHaveBeenCalledOnce();
    expect(probe.mock.calls[0]![0].id).toBe("a");
    expect(probe.mock.calls[0]![1]).toEqual({
      workspaceId: version.workspaceId,
      versionId: version.id,
    });
    expect(reports).toEqual([
      {
        outcome: "passed",
        attempts: 1,
        deploymentId: "a",
        durationMs: 250,
        modelId: version.baseModelId,
        workspaceId: version.workspaceId,
        versionId: version.id,
      },
    ]);
  });

  it("stops after the attempt limit and treats a thrown probe as an allocation failure", async () => {
    const probe = vi.fn<AdapterProbe>(async () => {
      throw new Error("socket closed");
    });
    const { qualify, reports } = qualifier(
      [target("a"), target("b"), target("c"), target("d")],
      probe,
      3,
    );

    await expect(qualify(version)).rejects.toMatchObject({
      code: "unavailable",
    });

    expect(probe).toHaveBeenCalledTimes(3);
    expect(reports).toMatchObject([
      {
        outcome: "failed",
        attempts: 3,
        deploymentId: "c",
        reason: "probe_error",
      },
    ]);
  });

  it("reports a rejection even when a later allocation fails differently", async () => {
    const probe = vi
      .fn<AdapterProbe>()
      .mockResolvedValueOnce({
        ok: false,
        rejected: true,
        reason: "invalid_adapter",
      })
      .mockResolvedValueOnce({
        ok: false,
        rejected: false,
        reason: "probe_timeout",
      });
    const { qualify, reports } = qualifier([target("a"), target("b")], probe);

    await expect(qualify(version)).rejects.toMatchObject({ code: "conflict" });
    expect(reports).toMatchObject([
      {
        outcome: "rejected",
        attempts: 2,
        deploymentId: "a",
        reason: "invalid_adapter",
      },
    ]);
  });

  it("reports no capacity when no allocation serves the revision", async () => {
    const probe = vi.fn<AdapterProbe>();
    const { qualify, reports } = qualifier(
      [target("a", { lora_enabled: false })],
      probe,
    );

    await expect(qualify(version)).rejects.toMatchObject({
      code: "unavailable",
    });
    expect(probe).not.toHaveBeenCalled();
    expect(reports).toMatchObject([{ outcome: "no_capacity", attempts: 0 }]);
  });
});
