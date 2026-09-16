import { randomUUID } from "node:crypto";

import type { DeploymentStatusReport } from "@gradiated/contracts";
import {
  servedReleaseDigest,
  type DeploymentStatusService,
} from "@gradiated/control";
import { describe, expect, it } from "vitest";

import {
  createDeploymentStatusIngestApp,
  parseDeploymentStatusTokens,
} from "../src/deployment-status-ingest.js";

const token = "runpod-test-token-with-at-least-32-characters";

const report = (): DeploymentStatusReport => ({
  schema_version: 1,
  deployment_id: randomUUID(),
  runtime_revision: "vllm-revision",
  healthy: true,
  accepting_requests: true,
  reason_code: null,
});

describe("deployment status ingestion", () => {
  it("uses the same stable release digest as the gateway", () => {
    expect(
      servedReleaseDigest({
        schema_version: 1,
        runtime_revision: "sglang-local-test-revision",
        model_path: "mlx-community/Qwen3-0.6B-4bit",
        model_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
        tokenizer_path: "mlx-community/Qwen3-0.6B-4bit",
        tokenizer_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
      }),
    ).toBe(
      "sha256:e4a74e6c4981b6176e08acc9fa391ca5fe5562485b5df96fdf088c48ae406eda",
    );
  });

  it("maps each secret token to one provider", () => {
    const tokens = parseDeploymentStatusTokens(
      JSON.stringify({ runpod: token }),
    );
    expect(tokens.get("runpod")).toBe(token);
  });

  it("rejects a missing provider token", async () => {
    const service: DeploymentStatusService = { report: async () => undefined };
    const response = await createDeploymentStatusIngestApp({
      tokens: new Map([["runpod", token]]),
      service,
    }).request("/v1/deployment-status", {
      method: "POST",
      body: JSON.stringify(report()),
    });
    expect(response.status).toBe(401);
  });

  it("accepts a valid current status", async () => {
    const reports: Array<[string, DeploymentStatusReport]> = [];
    const service: DeploymentStatusService = {
      report: async (provider, value) => {
        reports.push([provider, value]);
      },
    };
    const payload = report();
    const response = await createDeploymentStatusIngestApp({
      tokens: new Map([["runpod", token]]),
      service,
    }).request("/v1/deployment-status", {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    expect(response.status).toBe(204);
    expect(reports).toEqual([["runpod", payload]]);
  });
});
