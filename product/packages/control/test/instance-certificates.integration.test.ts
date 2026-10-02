import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { createInstanceService } from "../src/instances/service.js";
import {
  createInstanceCertificateService,
  CertificateAuthorizationError,
  CertificateRateLimitError,
} from "../src/instances/certificates.js";
import { instances } from "../src/db/schema/instances.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("GPU certificate authorization", () => {
  let database: TestDatabase;
  beforeAll(async () => {
    database = await createTestDatabase();
  });
  afterAll(() => database.dispose());
  const enroll = async () => {
    const inventory = createInstanceService(database.database);
    const record = await inventory.register({
      provider: "runpod",
      providerAccountId: "test",
      providerInstanceId: randomUUID(),
      region: null,
      faultDomain: null,
      sku: "synthetic",
    });
    const node = randomUUID();
    await inventory.bindNomadNode(record.id, node);
    const credentials = createInstanceCertificateService(database.database);
    const token = await credentials.enroll(record.id, node);
    return { id: record.id, node, credentials, token, inventory };
  };
  it("authorizes the same enrolled host credential for internal API reads without changing certificate state", async () => {
    const host = await enroll();
    await expect(
      host.credentials.authorize(host.id, host.node, host.token),
    ).resolves.toBeUndefined();
    await expect(
      host.credentials.authorize(host.id, randomUUID(), host.token),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
    await expect(
      host.credentials.authorize(host.id, host.node, "a".repeat(43)),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
    await host.credentials.revoke(host.id);
    await expect(
      host.credentials.authorize(host.id, host.node, host.token),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
  });

  it("enrolls bootstrap credentials before binding while denying issuance until binding", async () => {
    const inventory = createInstanceService(database.database);
    const record = await inventory.register({
      provider: "runpod",
      providerAccountId: "test",
      providerInstanceId: randomUUID(),
      region: null,
      faultDomain: null,
      sku: "synthetic",
    });
    const node = randomUUID();
    const credentials = createInstanceCertificateService(database.database);
    const token = await credentials.enroll(record.id, node);
    await expect(
      credentials.issue(record.id, node, token, async () => "no"),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
    await inventory.bindNomadNode(record.id, node);
    expect(
      await credentials.issue(
        record.id,
        node,
        token,
        async () => "certificate",
      ),
    ).toBe("certificate");
  });
  it("issues only for the enrolled instance, node and token", async () => {
    const h = await enroll();
    const sign = vi.fn(async () => "certificate");
    for (const [id, node, token] of [
      [randomUUID(), h.node, h.token],
      [h.id, randomUUID(), h.token],
      [h.id, h.node, "x".repeat(43)],
    ]) {
      await expect(
        h.credentials.issue(id!, node!, token!, sign),
      ).rejects.toBeInstanceOf(CertificateAuthorizationError);
    }
    expect(sign).not.toHaveBeenCalled();
    expect(await h.credentials.issue(h.id, h.node, h.token, sign)).toBe(
      "certificate",
    );
  });
  it("stores certificate state on the instance and keeps it out of inventory responses", async () => {
    const h = await enroll();
    const expiresAt = new Date(Date.now() + 30 * 86400_000);
    const renewalDueAt = new Date(Date.now() + 20 * 86400_000);
    await h.credentials.observe(h.id, h.node, h.token, expiresAt, renewalDueAt);
    const [record] = await database.database
      .select()
      .from(instances)
      .where(eq(instances.id, h.id));
    expect(record!.certificate).toMatchObject({
      expiresAt: expiresAt.toISOString(),
      renewalDueAt: renewalDueAt.toISOString(),
      nomadNodeId: h.node,
    });
    expect(record!.certificate!.tokenHash).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.stringify(record)).not.toContain(h.token);
    const inventory = await h.inventory.bindNomadNode(h.id, h.node);
    expect(inventory).not.toHaveProperty("certificate");
  });
  it("denies revoked and retired hosts, including heartbeats", async () => {
    const h = await enroll();
    await h.credentials.revoke(h.id);
    await expect(
      h.credentials.issue(h.id, h.node, h.token, async () => "no"),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
    await expect(
      h.credentials.observe(h.id, h.node, h.token, new Date(), new Date()),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
    const retired = await enroll();
    await database.database
      .update(instances)
      .set({ retiredAt: new Date() })
      .where(eq(instances.id, retired.id));
    await expect(
      retired.credentials.issue(
        retired.id,
        retired.node,
        retired.token,
        async () => "no",
      ),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
  });
  it("invalidates a token on replacement and node rebinding", async () => {
    const h = await enroll();
    const replacement = await h.credentials.enroll(h.id, h.node);
    await expect(
      h.credentials.issue(h.id, h.node, h.token, async () => "no"),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
    await h.inventory.bindNomadNode(h.id, randomUUID());
    await expect(
      h.credentials.issue(h.id, h.node, replacement, async () => "no"),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
  });
  it("serializes concurrent issuance and permits retry after signing failure", async () => {
    const h = await enroll();
    await expect(
      h.credentials.issue(h.id, h.node, h.token, async () => {
        throw new Error("KMS unavailable");
      }),
    ).rejects.toThrow("KMS unavailable");
    const outcomes = await Promise.allSettled(
      [1, 2].map(() =>
        h.credentials.issue(h.id, h.node, h.token, async () => "certificate"),
      ),
    );
    expect(outcomes.filter((r) => r.status === "fulfilled")).toHaveLength(1);
    const failure = outcomes.find(
      (r) => r.status === "rejected",
    ) as PromiseRejectedResult;
    expect(failure.reason).toBeInstanceOf(CertificateRateLimitError);
  });
  it("reports installed expiry and hides revoked hosts from monitoring", async () => {
    const h = await enroll();
    const expires = new Date(Date.now() + 30 * 86400_000);
    await h.credentials.observe(h.id, h.node, h.token, expires, new Date());
    expect(await h.credentials.observations()).toContainEqual(
      expect.objectContaining({
        instanceId: h.id,
        observedExpiresAt: expires,
        observedAt: expect.any(Date),
      }),
    );
    await h.credentials.revoke(h.id);
    expect(
      (await h.credentials.observations()).some(
        (row) => row.instanceId === h.id,
      ),
    ).toBe(false);
  });
  it("serializes revocation with an issuance already in progress", async () => {
    const host = await enroll();
    let start!: () => void;
    let finish!: () => void;
    const started = new Promise<void>((resolve) => {
      start = resolve;
    });
    const permitted = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const issuance = host.credentials.issue(
      host.id,
      host.node,
      host.token,
      async () => {
        start();
        await permitted;
        return "certificate";
      },
    );
    await started;
    const revocation = host.credentials.revoke(host.id);
    finish();
    await issuance;
    await revocation;
    await expect(
      host.credentials.issue(
        host.id,
        host.node,
        host.token,
        async () => "denied",
      ),
    ).rejects.toBeInstanceOf(CertificateAuthorizationError);
  });
  it("monitors active bound hosts before credential enrollment and after rebinding", async () => {
    const h = await enroll();
    const newNode = randomUUID();
    await h.inventory.bindNomadNode(h.id, newNode);
    expect(await h.credentials.observations()).toContainEqual({
      instanceId: h.id,
      observedAt: null,
      observedExpiresAt: null,
      observedRenewalDueAt: null,
    });
  });
});
