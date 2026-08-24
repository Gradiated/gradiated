import {
  createCatalogBillingService,
  createControlDatabase,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient, type ValkeyEnvironment } from "@gradiated/valkey";

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

// Public model IDs are case-sensitive. Keep this aligned with the existing
// OpenAI-compatible catalog ID; the Hugging Face repository keeps its own case
// in artifactModelPath below.
const modelId = "google/gemma-4-31b-it";
const artifactModelPath = "google/gemma-4-31B-it";
const modelRevision = "b9ea41a2887d8607f594846523f94c6cc75ac8a4";
const deploymentId =
  process.env.GEMMA4_DEPLOYMENT_ID ?? "019c8ad2-f857-7000-8000-000000000001";
const runtimeRevision =
  process.env.GEMMA4_RUNTIME_REVISION ?? "native-gemma4-h200-v1";

const { database, pool } = createControlDatabase(databaseUrl);
const valkey = createValkeyClient(valkeyEnvironment);
await valkey.connect();
try {
  const catalog = createCatalogBillingService(
    database,
    createValkeyServingProjector(valkey),
  );
  await catalog.upsertModel({
    id: modelId,
    name: "Gemma 4 31B Instruct",
    status: "available",
    properties: {
      description:
        "Google Gemma 4 31B Instruct on Gradiated's native single-H200 runtime.",
      released_at: null,
      hugging_face_id: artifactModelPath,
      quantization: "fp8",
      tokenizer: "Gemma 4",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 8_192, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 80 },
            { type: "cached_prompt", unit: "token", cost: 10 },
          ],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 4_096, unit: "token" },
          default_length: { value: 128, unit: "token" },
          streaming: true,
          // The first production native release is quality-gated for exact greedy decoding.
          // Expand this only after native stochastic sampling passes distributional parity.
          supported_parameters: {
            temperature: { type: "enum", values: [0] },
          },
          pricing: [{ type: "completion", unit: "token", cost: 350 }],
        },
      ],
    },
  });
  await catalog.upsertModelDeployment({
    id: deploymentId,
    modelId,
    status: "available",
    serviceUrl,
    release: {
      schema_version: 1,
      runtime_revision: runtimeRevision,
      model_path: artifactModelPath,
      model_revision: modelRevision,
      tokenizer_path: artifactModelPath,
      tokenizer_revision: modelRevision,
    },
  });
  console.log(
    `Configured ${modelId} deployment ${deploymentId} at ${serviceUrl}`,
  );
} finally {
  if (valkey.isOpen) await valkey.quit();
  await pool.end();
}
