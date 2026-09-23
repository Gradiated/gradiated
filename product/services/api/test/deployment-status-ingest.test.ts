import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";

import type {
  DeploymentStatusReport,
  ModelDeploymentRelease,
} from "@gradiated/contracts";
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
  // The gateway computes this key from ModelDeploymentRelease's serialisation and
  // reads heartbeats under it. Both sides are pinned to the same fixture so an
  // added release field cannot silently split them.
  it("computes the gateway's release digest for every optional field", async () => {
    const fixture = JSON.parse(
      await readFile(
        new URL(
          "../../gateway/test/fixtures/release-digests.json",
          import.meta.url,
        ),
        "utf8",
      ),
    ) as {
      cases: {
        name: string;
        release: ModelDeploymentRelease;
        digest: string;
      }[];
    };

    expect(fixture.cases).toHaveLength(8);
    for (const testCase of fixture.cases) {
      expect(servedReleaseDigest(testCase.release), testCase.name).toBe(
        testCase.digest,
      );
    }
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
