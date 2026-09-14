import { randomUUID } from "node:crypto";
import { Pool } from "pg";
import { migrate } from "drizzle-orm/node-postgres/migrator";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createControlDatabase } from "../src/db/client.js";
import { createInstanceService } from "../src/instances/service.js";

// Opt in with a local administrative database URL. Never migrate the supplied DB.
const url = process.env.INSTANCE_TEST_DATABASE_URL;
const suite = url ? describe : describe.skip;
suite("instance PostgreSQL contract", () => {
  const name = `instance_test_${randomUUID().replaceAll("-", "")}`;
  let admin: Pool;
  let client: ReturnType<typeof createControlDatabase>;
  let service: ReturnType<typeof createInstanceService>;
  beforeAll(async () => {
    const parsed = new URL(url!);
    if (!["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname)) {
      throw new Error("Integration tests require local PostgreSQL");
    }
    admin = new Pool({ connectionString: url });
    await admin.query(`CREATE DATABASE "${name}"`);
    parsed.pathname = `/${name}`;
    client = createControlDatabase(parsed.toString());
    service = createInstanceService(client.database);
    await migrate(client.database, {
      migrationsFolder: new URL("../migrations", import.meta.url).pathname,
    });
  });
  afterAll(async () => {
    await client?.pool.end();
    if (admin) {
      await admin.query(`DROP DATABASE IF EXISTS "${name}"`);
      await admin.end();
    }
  });
  const inventory = () => ({
    id: randomUUID(),
    provider: "runpod",
    providerAccountId: "test",
    providerInstanceId: randomUUID(),
    region: null,
    faultDomain: null,
    sku: "4xb300",
  });
  it("stores both GPU and CPU instance SKUs without device inventory", async () => {
    const gpu = await service.register(inventory());
    const cpu = await service.register({ ...inventory(), sku: "cpu-32vcpu" });
    expect(gpu.sku).toBe("4xb300");
    expect(cpu.sku).toBe("cpu-32vcpu");
    expect(gpu.nomadNodeId).toBeNull();
  });
  it("enforces provider identity within each provider account", async () => {
    const input = inventory();
    await service.register(input);
    await expect(
      service.register({ ...input, id: randomUUID() }),
    ).rejects.toThrow();
    await expect(
      service.register({
        ...input,
        id: randomUUID(),
        providerAccountId: "other",
      }),
    ).resolves.toBeDefined();
  });
  it("links each Nomad node to at most one instance and supports unlinking", async () => {
    const a = await service.register(inventory());
    const b = await service.register(inventory());
    const nodeId = randomUUID();
    expect((await service.setNomadNode(a.id, nodeId)).nomadNodeId).toBe(nodeId);
    await expect(service.setNomadNode(b.id, nodeId)).rejects.toThrow();
    expect((await service.setNomadNode(a.id, null)).nomadNodeId).toBeNull();
    expect((await service.setNomadNode(b.id, nodeId)).nomadNodeId).toBe(nodeId);
    await expect(service.setNomadNode(randomUUID(), nodeId)).rejects.toThrow(
      "Instance not found",
    );
  });
});
