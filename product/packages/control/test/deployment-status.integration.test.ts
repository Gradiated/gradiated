import { randomUUID } from "node:crypto";

import { eq } from "drizzle-orm";

import type { DeploymentStatusReport } from "@gradiated/contracts";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { modelDeployments } from "../src/db/schema/index.js";
import { createCatalogService } from "../src/catalog/service.js";
import {
  createDeploymentStatusService,
  DeploymentStatusError,
  servedReleaseDigest,
  type DeploymentStatusService,
} from "../src/deployment-status/service.js";
import {
  deploymentInput,
  deploymentRelease,
  modelInput,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

type ValkeyCall =
  | { command: "hSet"; key: string; field: string; value: unknown }
  | { command: "expire"; key: string; seconds: number };

const recordingValkey = () => {
  const calls: ValkeyCall[] = [];

  return {
    calls,
    hSet: async (key: string, field: string, value: string) => {
      calls.push({ command: "hSet", key, field, value: JSON.parse(value) });
    },
    expire: async (key: string, seconds: number) => {
      calls.push({ command: "expire", key, seconds });
    },
  };
};

describe("deployment status reports", () => {
  let testDatabase: TestDatabase;
  let deploymentId: string;
  let valkey: ReturnType<typeof recordingValkey>;
  let service: DeploymentStatusService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();

    const catalog = createCatalogService(testDatabase.database);
    const model = await catalog.upsertModel(modelInput());
    const deployment = await catalog.upsertModelDeployment(
      deploymentInput(model.id),
    );
    deploymentId = deployment.id;
  });

  beforeEach(() => {
    valkey = recordingValkey();
    service = createDeploymentStatusService(testDatabase.database, valkey);
  });

  afterAll(() => testDatabase.dispose());

  const report = (
    overrides: Partial<DeploymentStatusReport> = {},
  ): DeploymentStatusReport => ({
    schema_version: 1,
    deployment_id: deploymentId,
    runtime_revision: deploymentRelease().runtime_revision,
    healthy: true,
    accepting_requests: true,
    reason_code: null,
    ...overrides,
  });

  it.each([
    [
      "deployment_not_found",
      "runpod",
      () => report({ deployment_id: randomUUID() }),
    ],
    ["provider_mismatch", "lambda", () => report()],
    [
      "runtime_revision_mismatch",
      "runpod",
      () => report({ runtime_revision: "other-revision" }),
    ],
  ] as const)(
    "rejects a report with %s",
    async (code, provider, buildReport) => {
      const result = service.report(provider, buildReport());

      await expect(result).rejects.toBeInstanceOf(DeploymentStatusError);
      await expect(result).rejects.toMatchObject({ code });
      expect(valkey.calls).toEqual([]);
    },
  );

  it("writes the report under the served release key for 30 seconds", async () => {
    const key = `deployment-status:{${servedReleaseDigest(deploymentRelease())}}`;

    await service.report("runpod", report({ healthy: false }));

    expect(valkey.calls).toEqual([
      {
        command: "hSet",
        key,
        field: deploymentId,
        value: {
          ...report({ healthy: false }),
          received_at: expect.any(String),
        },
      },
      { command: "expire", key, seconds: 30 },
    ]);
  });
  it("rejects corrupt stored release JSON before recording a heartbeat", async () => {
    const catalog = createCatalogService(testDatabase.database);
    const model = await catalog.upsertModel(modelInput());
    const deployment = await catalog.upsertModelDeployment(
      deploymentInput(model.id),
    );
    await testDatabase.database
      .update(modelDeployments)
      .set({
        release: { ...deployment.release, schema_version: 2 as 1 },
      })
      .where(eq(modelDeployments.id, deployment.id));

    await expect(
      service.report("runpod", report({ deployment_id: deployment.id })),
    ).rejects.toMatchObject({ name: "ZodError" });
    expect(valkey.calls).toEqual([]);
  });
});
