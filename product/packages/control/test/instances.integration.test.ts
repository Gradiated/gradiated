import { eq } from "drizzle-orm";
import { createCatalogService } from "../src/catalog/service.js";
import { modelDeployments } from "../src/db/schema/index.js";
import { deploymentInput, modelInput } from "./support/fixtures.js";
import { randomUUID } from "node:crypto";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  createInstanceService,
  type InstanceService,
} from "../src/instances/service.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { createInstanceCertificateStore } from "../src/instances/certificate-store.js";

describe("instances", () => {
  let testDatabase: TestDatabase;
  let instances: InstanceService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    instances = createInstanceService(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  const machine = () => ({
    provider: "runpod",
    providerAccountId: "user_test",
    providerInstanceId: randomUUID(),
    region: "US-NE-1",
    faultDomain: "runpod:machine-a",
    sku: "2x NVIDIA RTX PRO 6000 Blackwell Server Edition",
  });

  it("records a machine before it has joined Nomad", async () => {
    const record = await instances.register(machine());

    expect(record).toMatchObject({ nomadNodeId: null, retiredAt: null });
  });

  it("preserves a private serving endpoint across repeated registration", async () => {
    const input = machine();
    const first = await instances.register(input);
    await instances.bindNomadNode(first.id, randomUUID());
    const servingUrl = `http://gpu-${first.id}.tailscale-inference.svc.cluster.local:8888`;

    await instances.setServingUrl(first.id, servingUrl);

    expect(await instances.register(input)).toMatchObject({
      id: first.id,
      servingUrl,
    });
    expect(await instances.setServingUrl(first.id, null)).toMatchObject({
      servingUrl: null,
    });
  });

  it("refuses private endpoint changes for unbound or retired hosts", async () => {
    const host = await instances.register(machine());
    const servingUrl = `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888`;

    await expect(
      instances.setServingUrl(host.id, servingUrl),
    ).rejects.toThrow();
    await instances.bindNomadNode(host.id, randomUUID());
    await instances.retire(host.id);
    await expect(
      instances.setServingUrl(host.id, servingUrl),
    ).rejects.toThrow();
  });

  it("refuses an endpoint switch qualified against an obsolete node binding", async () => {
    const record = await instances.register(machine());
    const firstNode = randomUUID();
    await instances.bindNomadNode(record.id, firstNode);
    const { host } = await instances.servingState(record.id);
    await instances.bindNomadNode(record.id, randomUUID());

    await expect(
      instances.setServingUrl(
        record.id,
        `http://gpu-${record.id}.tailscale-inference.svc.cluster.local:8888`,
        {
          nomadNodeId: firstNode,
          servingUrl: host.servingUrl,
          allocationIds: [],
        },
      ),
    ).rejects.toThrow();
    expect(
      (await instances.servingState(record.id)).host.servingUrl,
    ).toBeNull();
  });

  it("refuses cutover when available allocations changed after qualification", async () => {
    const registered = await instances.register(machine());
    const nodeId = randomUUID();
    const host = await instances.bindNomadNode(registered.id, nodeId);
    const url = `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888`;
    const qualified = await instances.servingState(host.id);
    const model = await createCatalogService(testDatabase.database).upsertModel(
      modelInput(),
    );
    const allocation = deploymentInput(model.id);
    await testDatabase.database
      .insert(modelDeployments)
      .values({ ...allocation, instanceId: host.id });

    await expect(
      instances.setServingUrl(host.id, url, {
        nomadNodeId: nodeId,
        servingUrl: null,
        allocationIds: qualified.allocationIds,
      }),
    ).rejects.toThrow();
    const updated = await instances.servingState(host.id);
    expect(updated.host.servingUrl).toBeNull();
    await expect(
      instances.setServingUrl(host.id, url, {
        nomadNodeId: nodeId,
        servingUrl: null,
        allocationIds: updated.allocationIds,
      }),
    ).resolves.toMatchObject({ servingUrl: url });

    await testDatabase.database
      .update(modelDeployments)
      .set({ status: "unavailable" })
      .where(eq(modelDeployments.id, allocation.id));
    await expect(
      instances.setServingUrl(host.id, null, {
        nomadNodeId: nodeId,
        servingUrl: url,
        allocationIds: updated.allocationIds,
      }),
    ).rejects.toThrow();
  });

  it("rejects endpoints that do not identify this host's private egress service", async () => {
    const host = await instances.register(machine());
    await instances.bindNomadNode(host.id, randomUUID());

    for (const url of [
      "http://169.254.169.254:8888",
      `http://gpu-${randomUUID()}.tailscale-inference.svc.cluster.local:8888`,
      `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888/alloc/x`,
      `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888?x=y`,
    ]) {
      await expect(instances.setServingUrl(host.id, url)).rejects.toThrow();
    }
  });

  it("retires an instance without losing its identity or allowing certificate enrollment", async () => {
    const input = machine();
    const record = await instances.register(input);
    const nomadNodeId = randomUUID();
    await instances.bindNomadNode(record.id, nomadNodeId);

    const retired = await instances.retire(record.id);
    expect(retired).toMatchObject({ id: record.id, nomadNodeId });
    expect(retired.retiredAt).toBeInstanceOf(Date);
    expect((await instances.retire(record.id)).retiredAt).toEqual(
      retired.retiredAt,
    );

    const certificates = createInstanceCertificateStore(testDatabase.database);
    await expect(
      certificates.enroll({
        instanceId: record.id,
        nomadNodeId,
        tokenHash: "a".repeat(64),
      }),
    ).rejects.toThrow("Unauthorized host");
    expect(await certificates.observations()).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ instanceId: record.id }),
      ]),
    );

    expect((await instances.register(input)).retiredAt).toBeNull();
  });

  it("keeps the instance and its current node when a machine registers again", async () => {
    const input = machine();
    const first = await instances.register(input);
    const nomadNodeId = randomUUID();
    await instances.bindNomadNode(first.id, nomadNodeId);

    const second = await instances.register({
      ...input,
      sku: "1x NVIDIA RTX PRO 6000 Blackwell Server Edition",
    });

    expect(second).toMatchObject({
      id: first.id,
      nomadNodeId,
      sku: "1x NVIDIA RTX PRO 6000 Blackwell Server Edition",
    });
  });

  it("moves an instance to the node it joined as", async () => {
    const record = await instances.register(machine());
    await instances.bindNomadNode(record.id, randomUUID());
    const nomadNodeId = randomUUID();

    const bound = await instances.bindNomadNode(record.id, nomadNodeId);

    expect(bound.nomadNodeId).toBe(nomadNodeId);
  });

  it("refuses a Nomad node that another instance holds", async () => {
    const nomadNodeId = randomUUID();
    const holder = await instances.register(machine());
    const other = await instances.register(machine());
    await instances.bindNomadNode(holder.id, nomadNodeId);

    await expect(
      instances.bindNomadNode(other.id, nomadNodeId),
    ).rejects.toThrow();
  });

  it("refuses to bind an instance that does not exist", async () => {
    await expect(
      instances.bindNomadNode(randomUUID(), randomUUID()),
    ).rejects.toThrow("Instance not found");
  });

  it("scopes machine identity to the provider account", async () => {
    const input = machine();
    const first = await instances.register(input);

    const other = await instances.register({
      ...input,
      providerAccountId: "user_other",
    });

    expect(other.id).not.toBe(first.id);
  });

  it("rejects a provider name that is not a plain identifier", async () => {
    await expect(
      instances.register({ ...machine(), provider: "Run Pod" }),
    ).rejects.toThrow();
  });
});
