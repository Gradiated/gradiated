import { randomUUID } from "node:crypto";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  createInstanceService,
  type InstanceService,
} from "../src/instances/service.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

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
