import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient, type ValkeyEnvironment } from "@gradiated/valkey";

import {
  createGlm53FlashModelConfiguration,
  glm53FlashArtifactModelPath,
  glm53FlashModelId,
} from "./glm-5-3-flash-model.js";

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const databaseUrl = required("DATABASE_URL");
const serviceUrls = required("GLM_5_3_FLASH_SERVICE_URLS")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
if (serviceUrls.length !== 2) {
  throw new Error("GLM_5_3_FLASH_SERVICE_URLS must contain two URLs");
}

const valkeyEnvironment: ValkeyEnvironment = {
  VALKEY_URL: required("VALKEY_URL"),
};
if (
  process.env.VALKEY_IAM_CACHE_NAME &&
  process.env.VALKEY_IAM_REGION &&
  process.env.VALKEY_IAM_USER
) {
  valkeyEnvironment.VALKEY_IAM_CACHE_NAME = process.env.VALKEY_IAM_CACHE_NAME;
  valkeyEnvironment.VALKEY_IAM_REGION = process.env.VALKEY_IAM_REGION;
  valkeyEnvironment.VALKEY_IAM_USER = process.env.VALKEY_IAM_USER;
}

const modelRevision = "84c6a6aa9497188e15a635ba793b0f95a79b1033";
const runtimeRevision =
  "vllm-933876c388fb129ad82590660e6506614559cb86-priority-v1";
const deploymentIds = [
  process.env.GLM_5_3_FLASH_DEPLOYMENT_1_ID ??
    "019d5a4a-0000-7000-8000-000000000001",
  process.env.GLM_5_3_FLASH_DEPLOYMENT_2_ID ??
    "019d5a4a-0000-7000-8000-000000000002",
];
const faultDomain =
  process.env.GLM_5_3_FLASH_FAULT_DOMAIN ?? "runpod:glm-5-3-flash-b300-1";
const region = required("GLM_5_3_FLASH_REGION");

const { database, pool } = createControlDatabase(databaseUrl);
const valkey = createValkeyClient(valkeyEnvironment);
await valkey.connect();
try {
  const catalog = createCatalogBillingService(
    database,
    createValkeyServingProjector(valkey),
  );
  await catalog.upsertModel(createGlm53FlashModelConfiguration());
  for (const [index, serviceUrl] of serviceUrls.entries()) {
    await catalog.upsertModelDeployment({
      id: deploymentIds[index]!,
      modelId: glm53FlashModelId,
      status: "available",
      provider: "runpod",
      region,
      faultDomain,
      serviceUrl,
      release: {
        schema_version: 1,
        runtime_revision: runtimeRevision,
        model_path: glm53FlashArtifactModelPath,
        model_revision: modelRevision,
        runtime_model_name: "zai-org/GLM-5.3-Flash",
        tokenizer_path: glm53FlashArtifactModelPath,
        tokenizer_revision: modelRevision,
      },
    });
  }
  console.log(`Configured ${glm53FlashModelId} with two RunPod deployments`);
} finally {
  if (valkey.isOpen) await valkey.quit();
  await pool.end();
}
