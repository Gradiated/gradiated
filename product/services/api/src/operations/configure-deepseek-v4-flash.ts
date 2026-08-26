import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient, type ValkeyEnvironment } from "@gradiated/valkey";

import {
  createDeepseekV4FlashModelConfiguration,
  deepseekV4FlashArtifactModelPath,
  deepseekV4FlashModelId,
} from "./deepseek-v4-flash-model.js";

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const databaseUrl = required("DATABASE_URL");
const serviceUrl = required("DEEPSEEK_V4_FLASH_SERVICE_URL");
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

const modelRevision = "7872f01b1d1fe23eabc4c98b48bffcef5a386062";
const deploymentId =
  process.env.DEEPSEEK_V4_FLASH_DEPLOYMENT_ID ??
  "019cc9fa-1d00-7000-8000-000000000001";
const runtimeRevision =
  process.env.DEEPSEEK_V4_FLASH_RUNTIME_REVISION ??
  "vllm-0.27.1-deepseek-v4-flash-b300-v1";

const { database, pool } = createControlDatabase(databaseUrl);
const valkey = createValkeyClient(valkeyEnvironment);
await valkey.connect();
try {
  const catalog = createCatalogBillingService(
    database,
    createValkeyServingProjector(valkey),
  );
  await catalog.upsertModel(createDeepseekV4FlashModelConfiguration());
  await catalog.upsertModelDeployment({
    id: deploymentId,
    modelId: deepseekV4FlashModelId,
    status: "available",
    serviceUrl,
    release: {
      schema_version: 1,
      runtime_revision: runtimeRevision,
      model_path: deepseekV4FlashArtifactModelPath,
      model_revision: modelRevision,
      runtime_model_name: "deepseek-v4-flash",
      tokenizer_path: deepseekV4FlashArtifactModelPath,
      tokenizer_revision: modelRevision,
      tokenizer_mode: "deepseek_v4",
    },
  });
  console.log(
    `Configured ${deepseekV4FlashModelId} deployment ${deploymentId} at ${serviceUrl}`,
  );
} finally {
  if (valkey.isOpen) await valkey.quit();
  await pool.end();
}
