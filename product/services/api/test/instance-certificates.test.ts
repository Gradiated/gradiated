import { generateKeyPairSync, X509Certificate } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import {
  CertificateAuthorizationError,
  CertificateRateLimitError,
  type InstanceCertificateService,
} from "@gradiated/control";
import { hostProfile, issueCertificate } from "@gradiated/nomad-pki";
import { localSigner, testCa } from "@gradiated/nomad-pki/testing";
import { ApiMetrics } from "../src/metrics.js";
import { createApp } from "../src/app.js";
import { unservedDependencies } from "../src/openapi.js";
const token = "t".repeat(43);
const instance = "019d5a4a-0000-7000-8000-000000000001";
const node = "3f1e5a52-8d4b-4c1e-9a55-111111111111";
const setup = async () => {
  const keys = generateKeyPairSync("ec", { namedCurve: "P-256" });
  const publicKey = keys.publicKey
    .export({ type: "spki", format: "pem" })
    .toString();
  const current = await issueCertificate(
    testCa.certificate,
    localSigner,
    hostProfile,
  );
  const issue = vi.fn(
    async (
      _id: string,
      _node: string,
      _token: string,
      sign: () => Promise<string>,
    ) => sign(),
  );
  const observe = vi.fn(async () => {});
  const audit = vi.fn();
  const app = createApp({
    ...unservedDependencies(),
    hostCertificates: {
      credentials: async () =>
        ({ issue, observe }) as unknown as InstanceCertificateService,
      caCertificate: async () => testCa.certificate,
      signer: localSigner,
      audit,
    },
  });
  const call = async (body: unknown, authorization = `Bearer ${token}`) => {
    const response = await app.request(
      `/api/internal/v1/instances/${instance}/nomad-certificates`,
      {
        method: "POST",
        headers: { authorization, "content-type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    return { status: response.status, body: await response.text() };
  };
  return {
    app,
    call,
    body: {
      nomad_node_id: node,
      public_key: publicKey,
      certificate: current.certificate,
    },
    keys,
    issue,
    observe,
    audit,
  };
};
describe("GPU certificate endpoint", () => {
  it("leaves health, documentation, and unrelated routes accessible when enabled", async () => {
    const h = await setup();
    for (const path of ["/health/live", "/api/openapi.json", "/docs"]) {
      expect((await h.app.request(path)).status).toBe(200);
    }
    expect((await h.app.request("/missing")).status).toBe(404);
    expect(h.issue).not.toHaveBeenCalled();
    expect(h.observe).not.toHaveBeenCalled();
  });
  it("signs only the host public key with a fixed role and 30-day lifetime", async () => {
    const h = await setup();
    const result = await h.call(h.body);
    expect(result.status).toBe(201);
    const payload = JSON.parse(result.body);
    expect(Object.keys(payload)).toEqual(["certificate"]);
    const c = new X509Certificate(payload.certificate);
    expect(c.checkPrivateKey(h.keys.privateKey)).toBe(true);
    expect(c.verify(new X509Certificate(testCa.certificate).publicKey)).toBe(
      true,
    );
    expect(c.checkHost("client.global.nomad")).toBe("client.global.nomad");
    expect(Date.parse(c.validTo) - Date.parse(c.validFrom)).toBe(
      (30 * 86400 + 300) * 1000,
    );
    expect(h.issue).toHaveBeenCalledWith(
      instance,
      node,
      token,
      expect.any(Function),
    );
    expect(JSON.stringify(h.audit.mock.calls)).not.toContain(token);
    expect(JSON.stringify(h.audit.mock.calls)).not.toContain(h.body.public_key);
  });
  it("accepts a heartbeat without issuing a certificate", async () => {
    const h = await setup();
    expect(
      (await h.call({ nomad_node_id: node, certificate: h.body.certificate }))
        .status,
    ).toBe(200);
    expect(h.observe).toHaveBeenCalledWith(
      instance,
      node,
      token,
      new Date(new X509Certificate(h.body.certificate).validTo),
      new Date(new X509Certificate(h.body.certificate).validFrom),
    );
    expect(h.issue).not.toHaveBeenCalled();
  });
  it("reports the normal renewal deadline after two thirds of the lifetime", async () => {
    const h = await setup();
    const issued = await h.call(h.body);
    const certificate = JSON.parse(issued.body).certificate as string;
    const c = new X509Certificate(certificate);
    const startsAt = Date.parse(c.validFrom);
    const expiresAt = Date.parse(c.validTo);
    h.observe.mockClear();
    expect((await h.call({ nomad_node_id: node, certificate })).status).toBe(
      200,
    );
    expect(h.observe).toHaveBeenCalledWith(
      instance,
      node,
      token,
      new Date(expiresAt),
      new Date(startsAt + ((expiresAt - startsAt) * 2) / 3),
    );
  });
  it("rejects missing authentication, caller-specified roles and incompatible keys", async () => {
    const h = await setup();
    expect((await h.call(h.body, "Bearer invalid")).status).toBe(401);
    expect((await h.call({ ...h.body, role: "server" })).status).toBe(422);
    expect((await h.call({ ...h.body, public_key: "invalid" })).status).toBe(
      422,
    );
    expect(h.issue).not.toHaveBeenCalled();
  });
  it("fails closed on revocation, rate limits and signer outages", async () => {
    const h = await setup();
    h.observe.mockRejectedValueOnce(new CertificateAuthorizationError());
    expect((await h.call(h.body)).status).toBe(403);
    h.issue.mockRejectedValueOnce(new CertificateRateLimitError());
    expect((await h.call(h.body)).status).toBe(429);
    h.issue.mockRejectedValueOnce(new Error("private upstream details"));
    const failed = await h.call(h.body);
    expect(failed.status).toBe(503);
    expect(failed.body).not.toContain("private upstream details");
    expect((await h.call(h.body)).status).toBe(201);
  });
});

describe("GPU certificate monitoring", () => {
  it("exports observed expiry on the first scrape and removes revoked hosts", async () => {
    const observations = vi.fn(async () => [
      {
        instanceId: instance,
        observedExpiresAt: new Date(2_000_000_000_000),
        observedAt: new Date(1_900_000_000_000),
        observedRenewalDueAt: new Date(1_990_000_000_000),
      },
    ]);
    const app = new ApiMetrics({
      hostCertificateCredentials: async () =>
        ({ observations }) as unknown as InstanceCertificateService,
    });
    const scrape = () => app.render();
    const first = await scrape();
    expect(first).toContain(
      `nomad_gpu_certificate_expiry_timestamp_seconds{instance_id="${instance}",service="api"} 2000000000`,
    );
    expect(first).toContain(
      `nomad_gpu_certificate_last_seen_timestamp_seconds{instance_id="${instance}",service="api"} 1900000000`,
    );
    expect(first).toContain(
      `nomad_gpu_certificate_renewal_due_timestamp_seconds{instance_id="${instance}",service="api"} 1990000000`,
    );
    expect(first).toContain(
      'nomad_gpu_certificate_observation_up{service="api"} 1',
    );
    observations.mockRejectedValueOnce(new Error("Database unavailable"));
    const unavailable = await scrape();
    expect(unavailable).toContain(
      'nomad_gpu_certificate_observation_up{service="api"} 0',
    );
    expect(unavailable).toContain("process_cpu_user_seconds_total");
    expect(unavailable).not.toContain(`instance_id="${instance}"`);
    observations.mockResolvedValue([]);
    expect(await scrape()).not.toContain(`instance_id="${instance}"`);
  });
});
