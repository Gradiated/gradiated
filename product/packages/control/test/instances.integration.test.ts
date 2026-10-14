import { randomUUID } from "node:crypto";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  createInstanceService,
  type InstanceService,
} from "../src/instances/service.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
const machine = () => ({
  provider: "runpod",
  providerAccountId: "test-account",
  providerInstanceId: randomUUID(),
  region: "US-TX-1",
  faultDomain: "host-a",
  sku: "8x NVIDIA B300",
});
describe("GPU instance inventory", () => {
  let database: TestDatabase;
  let instances: InstanceService;
  beforeAll(async () => {
    database = await createTestDatabase();
    instances = createInstanceService(database.database);
  });
  afterAll(() => database.dispose());
  it("records provider identity without scheduler credentials or a separate endpoint activation", async () => {
    const record = await instances.register(machine());
    expect(record.retiredAt).toBeNull();
    expect(record).not.toHaveProperty("certificate");
    expect(record).not.toHaveProperty("nomadNodeId");
    expect(record).not.toHaveProperty("servingUrl");
  });
  it("keeps a stable identity and refreshes placement metadata on repeated registration", async () => {
    const input = machine();
    const first = await instances.register(input);
    const second = await instances.register({
      ...input,
      region: "US-NE-1",
      faultDomain: "host-b",
    });
    expect(second).toMatchObject({
      id: first.id,
      region: "US-NE-1",
      faultDomain: "host-b",
    });
  });
  it("scopes identity to the provider account", async () => {
    const input = machine();
    const first = await instances.register(input);
    const second = await instances.register({
      ...input,
      providerAccountId: "other-account",
    });
    expect(second.id).not.toBe(first.id);
  });
  it("retires idempotently and preserves identity on deliberate reenrollment", async () => {
    const input = machine();
    const first = await instances.register(input);
    const retired = await instances.retire(first.id);
    expect(retired.retiredAt).not.toBeNull();
    expect((await instances.retire(first.id)).retiredAt).toEqual(
      retired.retiredAt,
    );
    expect(await instances.register(input)).toMatchObject({
      id: first.id,
      retiredAt: null,
    });
  });
  it("rejects missing hosts and invalid provider identifiers", async () => {
    await expect(instances.retire(randomUUID())).rejects.toThrow(
      "Instance not found",
    );
    await expect(
      instances.register({ ...machine(), provider: "invalid provider" }),
    ).rejects.toThrow();
  });
});
