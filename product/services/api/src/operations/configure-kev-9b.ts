import {
  createCatalogBillingService,
  createControlDatabase,
} from "@gradiated/control";

import {
  createKev9bModelConfiguration,
  kev9bArtifactModelPath,
  kev9bBaseModelPath,
  kev9bModelId,
} from "./kev-9b-model.js";

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const databaseUrl = required("DATABASE_URL");
// Both replicas live on one pod behind one authenticated proxy, so they differ
// only by path. Each is its own deployment so the gateway can route around one.
const serviceUrls = required("KEV_9B_SERVICE_URLS")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
if (serviceUrls.length !== 2) {
  throw new Error("KEV_9B_SERVICE_URLS must contain two URLs");
}

const modelRevision = "2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c";
const baseRevision = "68c46c4b3498877f3ef123c856ecfde50c39f404";
const runtimeRevision = "kev-f0ae8fb9-systemone-v1";
const deploymentIds = [
  // Zero based, matching the replica index, the supervisor stanzas and the pod's
  // services.conf. A mismatch here registers ids the reporters never publish.
  process.env.KEV_DEPLOYMENT_0_ID ?? "019d5a4a-0000-7000-8000-000000000101",
  process.env.KEV_DEPLOYMENT_1_ID ?? "019d5a4a-0000-7000-8000-000000000102",
];
const faultDomain =
  process.env.KEV_9B_FAULT_DOMAIN ?? "runpod:kev-9b-rtx6000-1";
const region = required("KEV_9B_REGION");

const { database, pool } = createControlDatabase(databaseUrl);
try {
  const catalog = createCatalogBillingService(database);
  await catalog.upsertModel(createKev9bModelConfiguration());
  for (const [index, serviceUrl] of serviceUrls.entries()) {
    await catalog.upsertModelDeployment({
      id: deploymentIds[index]!,
      modelId: kev9bModelId,
      status: "available",
      provider: "runpod",
      region,
      faultDomain,
      serviceUrl,
      release: {
        schema_version: 1,
        runtime_revision: runtimeRevision,
        // Without this the gateway serves the deployment as an OpenAI chat model
        // and every decision request fails closed.
        protocol: "system_one",
        model_path: kev9bArtifactModelPath,
        model_revision: modelRevision,
        runtime_model_name: kev9bArtifactModelPath,
        tokenizer_path: kev9bBaseModelPath,
        tokenizer_revision: baseRevision,
      },
    });
  }
  console.log(
    `Configured ${kev9bModelId} with ${serviceUrls.length} RunPod deployments`,
  );
} finally {
  await pool.end();
}
