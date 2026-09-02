import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient, type ValkeyEnvironment } from "@gradiated/valkey";

import {
  createGemma4ModelConfiguration,
  gemma4ArtifactModelPath,
  gemma4ModelId,
} from "./gemma4-model.js";

const required = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
};

const databaseUrl = required("DATABASE_URL");
const serviceUrl = required("GEMMA4_SERVICE_URL");
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

const modelRevision = "b9ea41a2887d8607f594846523f94c6cc75ac8a4";
const deploymentId =
  process.env.GEMMA4_DEPLOYMENT_ID ?? "019c8ad2-f857-7000-8000-000000000001";
const runtimeRevision =
  process.env.GEMMA4_RUNTIME_REVISION ?? "native-gemma4-h200-v2";

const { database, pool } = createControlDatabase(databaseUrl);
const valkey = createValkeyClient(valkeyEnvironment);
await valkey.connect();
try {
  const catalog = createCatalogBillingService(
    database,
    createValkeyServingProjector(valkey),
  );
  await catalog.upsertModel(createGemma4ModelConfiguration());
  await catalog.upsertModelDeployment({
    id: deploymentId,
    modelId: gemma4ModelId,
    status: "available",
    provider: process.env.GEMMA4_PROVIDER ?? "local",
    region: process.env.GEMMA4_REGION ?? "local",
    faultDomain: process.env.GEMMA4_FAULT_DOMAIN ?? `local:${deploymentId}`,
    serviceUrl,
    release: {
      schema_version: 1,
      runtime_revision: runtimeRevision,
      model_path: gemma4ArtifactModelPath,
      model_revision: modelRevision,
      tokenizer_path: gemma4ArtifactModelPath,
      tokenizer_revision: modelRevision,
    },
  });
  console.log(
    `Configured ${gemma4ModelId} deployment ${deploymentId} at ${serviceUrl}`,
  );
} finally {
  if (valkey.isOpen) await valkey.quit();
  await pool.end();
}
