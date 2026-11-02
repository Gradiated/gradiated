import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createCatalogService } from "../src/catalog/service.js";
import { createInstanceService } from "../src/instances/service.js";
import {
  instances as instanceTable,
  modelDeployments,
} from "../src/db/schema/index.js";
import { createKubernetesDeploymentStore } from "../src/deployments/kubernetes.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { deploymentRelease, modelInput } from "./support/fixtures.js";

describe("Kubernetes deployment ownership", () => {
  let database: TestDatabase;
  beforeAll(async () => {
    database = await createTestDatabase();
  });
  afterAll(() => database.dispose());

  it("uses stable instance identity and SDK qualification with an intrinsically private endpoint", async () => {
    const instances = createInstanceService(database.database);
    const host = await instances.register({
      provider: "runpod",
      providerAccountId: "test",
      providerInstanceId: randomUUID(),
      region: "US-NE-1",
      sku: "RTX PRO 6000",
      faultDomain: "test-host",
    });
    const model = await createCatalogService(database.database).upsertModel(
      modelInput(),
    );
    const pod = {
      id: randomUUID(),
      name: "kev-canary",
      instanceId: host.id,
      modelId: model.id,
      release: deploymentRelease(),
      qualified: false,
      draining: false,
    };
    const store = createKubernetesDeploymentStore(database.database);
    await store.reconcile({
      running: async () => [pod],
      isGone: async () => false,
    });
    const rows = () =>
      database.database
        .select()
        .from(modelDeployments)
        .where(eq(modelDeployments.id, pod.id));
    expect((await rows())[0]).toMatchObject({
      instanceId: host.id,
      status: "unavailable",
    });

    await store.reconcile({
      running: async () => [{ ...pod, qualified: true }],
      isGone: async () => false,
    });
    expect((await rows())[0]).toMatchObject({
      status: "available",
      serviceUrl: `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888/alloc/${pod.id}`,
    });
    for (const qualified of [false, true]) {
      await store.reconcile({
        running: async () => [{ ...pod, qualified, servingEnabled: false }],
        isGone: async () => false,
      });
      expect((await rows())[0]?.status).toBe("unavailable");
    }
    await store.reconcile({
      running: async () => [
        { ...pod, qualified: true, servingEnabled: false, draining: true },
      ],
      isGone: async () => false,
    });
    expect((await rows())[0]?.status).toBe("draining");
    await store.reconcile({
      running: async () => [{ ...pod, qualified: true, servingEnabled: true }],
      isGone: async () => false,
    });
    expect((await rows())[0]?.status).toBe("available");
    const privateModelId = `${model.id}-sglang-canary`;
    const privatePodId = randomUUID();
    await store.reconcile({
      running: async () => [
        { ...pod, modelId: privateModelId, qualified: true },
        { ...pod, id: privatePodId, modelId: privateModelId, qualified: true },
      ],
      isGone: async () => false,
    });
    expect((await rows())[0]).toMatchObject({
      modelId: model.id,
      status: "unavailable",
    });
    expect(
      await database.database
        .select()
        .from(modelDeployments)
        .where(eq(modelDeployments.id, privatePodId)),
    ).toHaveLength(0);
    await store.reconcile({
      running: async () => [{ ...pod, qualified: true, servingEnabled: false }],
      isGone: async () => false,
    });
    expect((await rows())[0]).toMatchObject({
      modelId: model.id,
      status: "unavailable",
    });
    await store.reconcile({
      running: async () => [
        { ...pod, modelId: "missing-model", qualified: true },
      ],
      isGone: async () => false,
    });
    expect((await rows())[0]?.status).toBe("unavailable");
    await store.reconcile({
      running: async () => [
        { ...pod, qualified: true },
        { ...pod, id: randomUUID(), modelId: "missing-model" },
      ],
      isGone: async () => false,
    });
    expect((await rows())[0]?.status).toBe("available");
    await database.database
      .update(instanceTable)
      .set({ retiredAt: new Date() })
      .where(eq(instanceTable.id, host.id));
    await store.reconcile({
      running: async () => [{ ...pod, qualified: true }],
      isGone: async () => false,
    });
    expect((await rows())[0]?.status).toBe("unavailable");
    await store.reconcile({
      running: async () => [],
      isGone: async () => false,
    });
    expect(await rows()).toHaveLength(1);
    expect((await rows())[0]?.status).toBe("unavailable");
    await store.reconcile({
      running: async () => [],
      isGone: async () => true,
    });
    expect(await rows()).toHaveLength(0);
  });
});
