import { readFile } from "node:fs/promises";
import { describe, expect, it, vi } from "vitest";

import {
  enrollmentSchemaFiles,
  renderSchema,
  schemaPath,
} from "../scripts/enrollment-schemas.js";
import {
  ENROLL_COMMAND,
  enroll,
  enrollmentPayload,
} from "../src/enrollment.js";
import type { RunSsh } from "../src/ssh.js";

const instance = {
  provider: "runpod",
  providerAccountId: "account",
  providerInstanceId: "pod1",
  region: "US-TX-1",
  faultDomain: "runpod:machine",
  sku: "4x NVIDIA B300 SXM6 AC",
};
const fields = {
  instance_id: "019d5a4a-0000-7000-8000-000000000001",
  management_token: "private_management_" + "x".repeat(24),
  auth_key: "tskey-auth-kPrivate-0123",
  api_endpoint: "100.64.0.1",
  host_bundle: {
    sha256: "a".repeat(64),
    base_id: "ubuntu24-cuda13-amd64-v2",
    url: "https://artifacts.example/host.tar.gz?X-Amz-Signature=private",
  },
};
const target = {
  host: "100.64.0.9",
  port: 22,
  hostKeySha256: ["0".repeat(64)],
};
const result = {
  version: 1,
  tailscale_ip: "100.101.172.112",
  gpu_count: 4,
  gpu_product: "B300",
  cpu: 57,
  memory_gib: 880,
  promotion: true,
};

describe("GPU enrollment contract", () => {
  it("matches the JSON Schemas the GPU base image validates against", async () => {
    // Regenerate with: pnpm exec tsx scripts/enrollment-schemas.ts
    for (const [name, schema] of Object.entries(enrollmentSchemaFiles))
      expect(await readFile(schemaPath(name), "utf8")).toBe(
        await renderSchema(schema),
      );
  });

  it("builds a payload only for qualified hosts", () => {
    expect(enrollmentPayload(instance, fields)).toEqual({
      version: 1,
      ...fields,
    });
    expect(() =>
      enrollmentPayload(
        { ...instance, sku: "8x NVIDIA H100 80GB HBM3" },
        fields,
      ),
    ).toThrow("GPU enrollment supports B300, H200 and RTX PRO 6000 hosts");
    expect(() =>
      enrollmentPayload(instance, { ...fields, api_endpoint: "10.40.1.1" }),
    ).toThrow();
  });

  it("sends credentials on stdin only and parses the host's result", async () => {
    const run = vi.fn<RunSsh>(async () => `${JSON.stringify(result)}\n`);
    const payload = enrollmentPayload(instance, fields);
    await expect(enroll(run, target, payload)).resolves.toEqual(result);
    const [, command, input, timeout] = run.mock.calls[0]!;
    expect(command).toBe(ENROLL_COMMAND);
    expect(command).not.toMatch(/private|tskey/);
    expect(JSON.parse(input!)).toEqual(payload);
    expect(timeout).toBe(30 * 60 * 1000);
  });

  it("enrolls a two-H200 host without treating it as a B300", async () => {
    const payload = enrollmentPayload(
      { ...instance, sku: "2x NVIDIA H200" },
      fields,
    );
    const inventory = { ...result, gpu_count: 2, gpu_product: "H200" };
    await expect(
      enroll(
        vi.fn<RunSsh>(async () => JSON.stringify(inventory)),
        target,
        payload,
      ),
    ).resolves.toEqual(inventory);
    expect(() =>
      enrollmentPayload({ ...instance, sku: "2x NVIDIA GH200" }, fields),
    ).toThrow();
    expect(() =>
      enrollmentPayload({ ...instance, sku: "2x NVIDIA H2000" }, fields),
    ).toThrow();
  });

  it("rejects a malformed result without echoing it", async () => {
    for (const output of [
      "not json private_management",
      JSON.stringify({ ...result, gpu_product: "H100" }),
      JSON.stringify({ ...result, extra: "private_management" }),
    ]) {
      await expect(
        enroll(
          vi.fn<RunSsh>(async () => output),
          target,
          enrollmentPayload(instance, fields),
        ),
      ).rejects.toThrow(/^gradiated-host enroll returned an invalid result$/);
    }
  });
});
