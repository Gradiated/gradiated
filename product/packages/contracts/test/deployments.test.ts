import { describe, expect, it } from "vitest";

import {
  DeploymentStatusReportSchema,
  GatewayModelDeploymentSchema,
  ModelDeploymentReleaseSchema,
} from "../src/index.js";

const release = {
  schema_version: 1,
  runtime_revision: "runtime-1",
  model_path: "s3://models/small",
  model_revision: "rev-1",
  tokenizer_path: "s3://tokenizers/small",
  tokenizer_revision: "rev-1",
};

const statusReport = {
  schema_version: 1,
  deployment_id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  runtime_revision: "runtime-1",
  healthy: true,
  accepting_requests: true,
  reason_code: null,
};

const deployment = {
  id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  status: "available",
  provider: "runpod",
  region: "us-east-1",
  fault_domain: "us-east-1a",
  service_url: "https://runtime.example.test",
  release,
};

describe("DeploymentStatusReportSchema", () => {
  it("strips unknown keys", () => {
    expect(
      DeploymentStatusReportSchema.parse({ ...statusReport, uptime: 12 }),
    ).toEqual(statusReport);
  });

  it("rejects a reason code outside snake case", () => {
    expect(
      DeploymentStatusReportSchema.safeParse({
        ...statusReport,
        reason_code: "Bad-Code",
      }).success,
    ).toBe(false);
  });
});

describe("ModelDeploymentReleaseSchema", () => {
  it("rejects an unknown key", () => {
    expect(
      ModelDeploymentReleaseSchema.safeParse({ ...release, extra: true })
        .success,
    ).toBe(false);
  });
});

describe("GatewayModelDeploymentSchema", () => {
  it("accepts an HTTPS deployment", () => {
    expect(GatewayModelDeploymentSchema.safeParse(deployment).success).toBe(
      true,
    );
  });

  it.each([
    ["a non-HTTP service URL", { service_url: "ftp://x" }],
    ["an uppercase provider", { provider: "Runpod" }],
  ])("rejects %s", (_, overrides) => {
    expect(
      GatewayModelDeploymentSchema.safeParse({ ...deployment, ...overrides })
        .success,
    ).toBe(false);
  });
});

it("accepts Nomad allocation IDs in status and gateway deployments", () => {
  const id = "a4d51466-8782-bf13-3b97-b8a07ad79c26";
  expect(
    DeploymentStatusReportSchema.safeParse({
      ...statusReport,
      deployment_id: id,
    }).success,
  ).toBe(true);
  expect(
    GatewayModelDeploymentSchema.safeParse({ ...deployment, id }).success,
  ).toBe(true);
  expect(
    DeploymentStatusReportSchema.safeParse({
      ...statusReport,
      deployment_id: "not-an-id",
    }).success,
  ).toBe(false);
});
