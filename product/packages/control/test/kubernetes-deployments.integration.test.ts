import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createCatalogService } from "../src/catalog/service.js";
import { createInstanceService } from "../src/instances/service.js";
import { modelDeployments } from "../src/db/schema/index.js";
import { createKubernetesDeploymentStore } from "../src/deployments/kubernetes.js";
import { createNomadDeploymentStore } from "../src/deployments/nomad.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { deploymentRelease, modelInput } from "./support/fixtures.js";

describe("Kubernetes deployment ownership", () => {
  let database: TestDatabase;
  beforeAll(async () => {
    database = await createTestDatabase();
  });
  afterAll(() => database.dispose());

  it("uses stable instance identity and survives an empty Nomad view", async () => {
    const instances = createInstanceService(database.database);
    const host = await instances.register({
      provider: "runpod",
      providerAccountId: "test",
      providerInstanceId: randomUUID(),
      region: "US-NE-1",
      sku: "RTX PRO 6000",
      faultDomain: "test-host",
    });
    await instances.bindNomadNode(host.id, randomUUID());
    await instances.setServingUrl(
      host.id,
      `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888`,
    );
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
      orchestrator: "kubernetes",
      status: "unavailable",
    });

    await createNomadDeploymentStore(database.database).reconcile({
      running: async () => [],
      isGone: async () => {
        throw new Error("Nomad must not inspect Kubernetes deployments");
      },
    });
    expect(await rows()).toHaveLength(1);
    await store.reconcile({
      running: async () => [{ ...pod, qualified: true }],
      isGone: async () => false,
    });
    expect((await rows())[0]).toMatchObject({
      status: "available",
      serviceUrl: `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888/alloc/${pod.id}`,
    });
    await store.reconcile({
      running: async () => [],
      isGone: async () => false,
    });
    expect(await rows()).toHaveLength(1);
    await store.reconcile({
      running: async () => [],
      isGone: async () => true,
    });
    expect(await rows()).toHaveLength(0);
  });
});
